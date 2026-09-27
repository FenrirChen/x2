"""Persistent player mail with transactional attachment claims."""
from collections import Counter
import asyncio
import json
import time

from x2server.messages.mail import MAIL_ATTACHMENT, MAIL_INFO, MAIL_SCHEMAS
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY
from .economy import UnresolvedEconomy


class MailService:
    def __init__(self, store, economy, clock=time.time):
        self.store, self.economy, self.clock = store, economy, clock
        with store.db:
            store.db.execute("""CREATE TABLE IF NOT EXISTS player_mail (
                id INTEGER PRIMARY KEY AUTOINCREMENT, player_id INTEGER NOT NULL,
                sender TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
                state INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL,
                attachments TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0)""")
            store.db.execute("CREATE INDEX IF NOT EXISTS player_mail_owner ON player_mail(player_id,deleted,created_at)")

    def handlers(self):
        return {"C2L_" + name: self.handle for name in (
            "MailData", "ReadMail", "ReceiveAttachment", "ReceiveAllAttachment",
            "DelMail", "DelAllMail")}

    def send(self, player_id, title, body, attachments=None, sender="解神者 Revival"):
        """Queue a server-authored mail; the caller may push ``list_message`` online."""
        self.store.get(player_id)
        if not all(isinstance(value, str) and value and len(value) <= maximum
                   for value, maximum in ((sender, 80), (title, 120), (body, 4000))):
            raise ValueError("invalid mail text")
        rewards = dict(attachments or {})
        for item_id, quantity in rewards.items():
            if type(item_id) is not int or type(quantity) is not int or not 1 <= quantity <= 999999:
                raise ValueError("invalid mail attachment")
            item = self.economy.items.get(item_id)
            if item is None:
                raise ValueError("unknown mail attachment")
            kind = item.get("ItemType", {}).get("value")
            if not (item_id in self.economy.CURRENCIES or item_id == 1237900 or
                    kind in self.economy.STACKABLE_REWARD_TYPES or
                    kind == 16 and item.get("ItemUseScence", {}).get("value") == 1):
                raise ValueError("unsupported mail attachment")
        with self.economy.transaction():
            cursor = self.store.db.execute("""INSERT INTO player_mail
                (player_id,sender,title,body,created_at,attachments) VALUES (?,?,?,?,?,?)""",
                (player_id, sender, title, body, int(self.clock()), json.dumps(rewards, sort_keys=True)))
            return cursor.lastrowid

    async def watch(self, server, interval=1.0):
        """Push new server mail to online players; offline mail is sent at login."""
        last_id = self.store.db.execute("SELECT coalesce(max(id),0) FROM player_mail").fetchone()[0]
        while True:
            await asyncio.sleep(interval)
            rows = self.store.db.execute("SELECT id,player_id FROM player_mail WHERE id>? ORDER BY id",
                                         (last_id,)).fetchall()
            if rows:
                last_id = rows[-1][0]
                for player_id in {row[1] for row in rows}:
                    await server.push_to_player(player_id, self.list_message(player_id))

    def _row(self, player_id, mail_id):
        return self.store.db.execute("SELECT * FROM player_mail WHERE player_id=? AND id=? AND deleted=0",
                                     (player_id, mail_id)).fetchone()

    @staticmethod
    def _encode(row):
        rewards = json.loads(row["attachments"])
        return MAIL_INFO.encode({"id": row["id"], "from": row["sender"],
            "title": row["title"], "body": row["body"], "state": row["state"],
            "time": row["created_at"], "GroupID": 0,
            "attachments": [MAIL_ATTACHMENT.encode({"itemID": int(item), "itemNum": count})
                            for item, count in sorted(rewards.items(), key=lambda pair: int(pair[0]))]})

    def list_values(self, player_id, page_index=0, page_size=20):
        if type(page_index) is not int or page_index < 0 or type(page_size) is not int or not 1 <= page_size <= 100:
            return {"code": 13}
        total = self.store.db.execute("SELECT count(*) FROM player_mail WHERE player_id=? AND deleted=0",
                                      (player_id,)).fetchone()[0]
        # Both zero- and one-based first-page requests are seen in client flows.
        offset = max(page_index - 1, 0) * page_size
        rows = self.store.db.execute("""SELECT * FROM player_mail WHERE player_id=? AND deleted=0
            ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?""", (player_id, page_size, offset)).fetchall()
        return {"code": 10, "total": total, "mails": [self._encode(row) for row in rows]}

    def list_message(self, player_id):
        return OutboundMessage("L2C_MailData", self.list_values(player_id))

    def _claim(self, player_id, ids):
        ids = list(dict.fromkeys(ids))
        if not ids or len(ids) > 100:
            return None
        rows = [self._row(player_id, mail_id) for mail_id in ids]
        if any(row is None for row in rows):
            return None
        rows = [row for row in rows if row["state"] in (0, 1) and json.loads(row["attachments"])]
        if not rows:
            return None
        rewards = Counter()
        for row in rows:
            rewards.update({int(item): count for item, count in json.loads(row["attachments"]).items()})
        with self.economy.transaction():
            self.economy._grant(player_id, "mail:" + ",".join(map(str, sorted(ids))), dict(rewards))
            for row in rows:
                self.store.db.execute("UPDATE player_mail SET state=? WHERE id=? AND player_id=?",
                    (3 if row["state"] == 1 else 2, row["id"], player_id))
        return dict(rewards)

    async def handle(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("mail requested before login")
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        req = MAIL_SCHEMAS[name].decode(packet.body)
        reply = name.replace("C2L_", "L2C_", 1)
        if name == "C2L_MailData":
            return OutboundMessage(reply, self.list_values(player_id,
                req.get("pageIndex", 0), req.get("pageSize", 20) or 20))
        if name == "C2L_ReadMail":
            mail_id = req.get("mailid", 0)
            row = self._row(player_id, mail_id)
            if row:
                with self.economy.transaction():
                    self.store.db.execute("UPDATE player_mail SET state=? WHERE id=? AND player_id=?",
                        (1 if row["state"] == 0 else 3 if row["state"] == 2 else row["state"], mail_id, player_id))
            return OutboundMessage(reply, {"code": 10 if row else 13, "mailid": mail_id})
        if name in ("C2L_ReceiveAttachment", "C2L_ReceiveAllAttachment"):
            ids = ([req.get("mailid", 0)] if name == "C2L_ReceiveAttachment" else
                   req.get("mailids") or [r[0] for r in self.store.db.execute("""SELECT id FROM player_mail
                       WHERE player_id=? AND deleted=0 AND state IN (0,1) AND attachments!='{}'""", (player_id,))])
            try:
                rewards = self._claim(player_id, ids)
            except UnresolvedEconomy:
                rewards = None
            values = {"code": 10 if rewards is not None else 13,
                      "rewardData": self.economy.reward_bytes(rewards) if rewards else b""}
            values.update({"mailid": ids[0] if ids else 0} if name == "C2L_ReceiveAttachment" else
                          {"mailids": ids})
            return OutboundMessage(reply, values, pushes=(*self.economy.pushes(player_id),
                self.list_message(player_id)) if rewards is not None else ())
        if name == "C2L_DelMail":
            mail_id = req.get("mailid", 0)
            row = self._row(player_id, mail_id)
            allowed = bool(row and (row["state"] in (2, 3) or not json.loads(row["attachments"])))
            if allowed:
                with self.economy.transaction():
                    self.store.db.execute("UPDATE player_mail SET deleted=1 WHERE id=? AND player_id=?",
                                          (mail_id, player_id))
            return OutboundMessage(reply, {"code": 10 if allowed else 13, "mailid": mail_id})
        if name == "C2L_DelAllMail":
            with self.economy.transaction():
                self.store.db.execute("""UPDATE player_mail SET deleted=1 WHERE player_id=?
                    AND (state IN (2,3) OR state=1 AND attachments='{}')""", (player_id,))
            return OutboundMessage(reply, {"code": 10}, pushes=(self.list_message(player_id),))
        raise ProtocolError("unknown mail request")
