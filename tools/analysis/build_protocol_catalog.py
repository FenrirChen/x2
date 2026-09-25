"""PART C: full client protocol census (C2L/L2C) crossed with the Revival server.

Outputs:
  analysis/protocol/protocol_catalog.json
  analysis/protocol/unhandled_high_value.json
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
X2 = REPO.parent
OUT = REPO / "analysis" / "protocol"
OUT.mkdir(parents=True, exist_ok=True)
DUMP = (X2 / "tools/Il2CppDumper-bin/dump.cs").read_text(encoding="utf-8")

# ---------- 1. client enum ERequestTypes ----------
enum_m = re.search(r"public enum ERequestTypes.*?\{(.*?)\n\}", DUMP, re.S)
consts = re.findall(r"public const ERequestTypes ([A-Za-z0-9_]+) = (-?\d+);", enum_m.group(1))
ids = defaultdict(list)
for name, num in consts:
    ids[int(num)].append(name)
c2l = {int(n): names[0][5:] for n, names in ids.items() if any(x.startswith("EC2L_") for x in names)}
l2c = {int(n): names[0][5:] for n, names in ids.items() if any(x.startswith("EL2C_") for x in names)}
print(f"EC2L_*: {len(c2l)}  EL2C_*: {len(l2c)}")

# ---------- 2. protobuf message class fields ----------
def class_fields(clsname):
    m = re.search(
        r"// Namespace: CommandX2\npublic class " + re.escape(clsname) +
        r" : IMessage[^\n]*\n\{(.*?)\n\}\n", DUMP, re.S)
    if not m:
        return None
    return re.findall(r"public [\w<>.\[\], ]+ (\w+); // 0x", m.group(1))

# ---------- 3. send instantiation sites (all net managers) ----------
send_sites = defaultdict(set)
for m in re.finditer(r"\|- ?(\w+NetManager)\.(SendBattle|Send|SendChat)<(\w+)>", DUMP):
    send_sites[m.group(3)].add(f"{m.group(1)}.{m.group(2)}")
print("send-site message classes:", len(send_sites))

# ---------- 4. server registry ----------
server_entries = []
reg_src = (REPO / "src/x2server/protocol/registry.py").read_text(encoding="utf-8")
for m in re.finditer(r'MessageEntry\("(\w+)", (\d+), Direction\.(\w+)\)', reg_src):
    server_entries.append((m.group(1), int(m.group(2)), m.group(3)))
for mod in ("lobby", "chat", "economy"):
    src = (REPO / f"src/x2server/messages/{mod}.py").read_text(encoding="utf-8")
    for m in re.finditer(r'\("(\w+)", (\d+), (\d+)\)', src):
        server_entries.append(("C2L_" + m.group(1), int(m.group(2)), "CLIENT_TO_SERVER"))
        server_entries.append(("L2C_" + m.group(1), int(m.group(3)), "SERVER_TO_CLIENT"))
server_by_name = {}
for name, mid, direction in server_entries:
    server_by_name.setdefault(name, {"message_id": mid, "direction": direction})

registered_handlers = set()
for f in (REPO / "src/x2server").rglob("*.py"):
    for m in re.finditer(r'"(C2L_\w+)"', f.read_text(encoding="utf-8")):
        registered_handlers.add(m.group(1))
print("server registry entries:", len(server_by_name))

DOMAINS = [
    ("Login/Session", ("login", "reconnect", "heartbeat", "servertable", "kick", "token", "controlinfo", "closeconnection")),
    ("Battle Entry", ("fightdata", "preparemainmission", "matchenter", "battleenter", "trainingground", "secsweep", "quitfight", "battleready", "battlestart")),
    ("Battle Runtime", ("fightdrop", "fightkill", "checkfightprofile", "delfightprofile", "updatedropvalue", "frame", "battleover")),
    ("Battle Checkout", ("checkoutmainmission", "checkout", "settlement", "checkoutmission")),
    ("Mission/Chapter", ("mission", "chapter", "story", "starbox")),
    ("DailyDungeon", ("dailydungeon", "weeklydungeon", "dailyandweektask", "otherchapter")),
    ("Hero", ("hero",)),
    ("Skill", ("skill",)),
    ("Artifact", ("artifact", "jewel", "godslot", "godequp")),
    ("Equipment", ("equip", "equib")),
    ("Inventory/Item", ("itemall", "itemupdate", "itemopt", "getitem", "useitem", "sellitem", "itemlock", "currency")),
    ("Task", ("task", "gametask", "treasurebox", "pickbox")),
    ("Shop", ("shop", "goods", "buygoods", "refreshshop")),
    ("Draw", ("draw", "luckdraw", "cardpool", "wish", "prizedraw")),
    ("Mail", ("mail",)),
    ("Friend", ("friend",)),
    ("Club/Guild", ("club", "guild")),
    ("Chat", ("chat",)),
    ("Achievement", ("achievement", "achv", "medal")),
    ("Activity/Event", ("activity", "event", "worldboss", "tower", "endless", "challenge", "monopoly", "moon", "blood", "newyear", "holiday", "battlepass", "elementsynthesis")),
    ("Guide", ("guide", "novice", "buttonclick", "tito")),
    ("Player/Growth", ("player", "rolelevel", "experience", "power", "account")),
    ("Gift/Reward", ("gift", "reward", "receivegift", "sign")),
    ("MiniGame/CardBattle", ("battlebureau", "battlecard", "battleround", "battlescore", "battleshow", "csp2p")),
    ("Alchemy", ("alchemy", "praygod", "building", "build")),
    ("CafeStore", ("cafestore", "cook", "food")),
    ("Explore/Train", ("explore", "train", "match", "cancelmatch", "confirmmatch", "aipoint")),
    ("Social", ("blacknpc", "catfavor", "favor", "bindtel", "cdkey", "cheat", "convert", "dayrefresh", "dismiss", "member", "announcement", "questionnaire", "share")),
    ("System", ("system", "config", "gm", "push", "notice")),
]

def domain_of(name):
    n = name.lower()
    for dom, kws in DOMAINS:
        if any(k in n for k in kws):
            return dom
    return "Unknown"

# ---------- 6. build catalog ----------
catalog = []
for mid, names in sorted(ids.items()):
    is_c2l = any(x.startswith("EC2L_") for x in names)
    is_l2c = any(x.startswith("EL2C_") for x in names)
    if not (is_c2l or is_l2c):
        continue
    base = names[0][5:]
    kind = "C2L" if is_c2l else "L2C"
    cls_fields = class_fields(kind + "_" + base)
    channels = sorted(send_sites.get(kind + "_" + base, []))
    if kind == "C2L":
        client_status = "SEND_SITES_FOUND" if channels else "NO_SEND_POINT_IN_2_4"
        resp = l2c.get(mid)
        resp_status = "DIRECT" if resp == base else ("ADJACENT_ID" if resp else "NO_DIRECT_RESPONSE")
    else:
        has_request_sibling = base in set(c2l.values())
        client_status = "PUSH" if not has_request_sibling else "QUERY_RESPONSE"
        resp = None
        resp_status = client_status
    entry = {
        "message_id": mid,
        "message_name": base,
        "enum_names": names,
        "direction": kind,
        "protobuf_fields": cls_fields,
        "send_channels": channels if kind == "C2L" else None,
        "paired_response": resp if kind == "C2L" else None,
        "response_status": resp_status,
        "client_status": client_status,
        "server_registered": (kind + "_" + base) in server_by_name,
        "server_entry": server_by_name.get(kind + "_" + base),
        "server_handler_seen": (kind + "_" + base) in registered_handlers,
        "business_domain": domain_of(base),
    }
    catalog.append(entry)

# inherit domain for L2C from C2L sibling
dom_by_base = {e["message_name"]: e["business_domain"] for e in catalog if e["direction"] == "C2L"}
for e in catalog:
    if e["business_domain"] == "Unknown" and e["message_name"] in dom_by_base:
        e["business_domain"] = dom_by_base[e["message_name"]]

c2l_entries = [e for e in catalog if e["direction"] == "C2L"]
summary = {
    "generated_by": "tools/analysis/build_protocol_catalog.py",
    "enum_total_ids": len(ids),
    "c2l_count": len(c2l),
    "l2c_count": len(l2c),
    "c2l_with_send_sites": sum(1 for e in c2l_entries if e["send_channels"]),
    "c2l_no_send_point": sum(1 for e in c2l_entries if not e["send_channels"]),
    "server_registered_c2l": sum(1 for e in c2l_entries if e["server_registered"]),
    "l2c_push_count": sum(1 for e in catalog if e["direction"] == "L2C" and e["response_status"] == "PUSH"),
    "domain_counts": dict(Counter(e["business_domain"] for e in catalog)),
}
(OUT / "protocol_catalog.json").write_text(json.dumps(
    {"summary": summary, "catalog": catalog}, ensure_ascii=False), encoding="utf-8")

# ---------- 7. high-value unhandled ----------
static_domains = {
    "Achievement": "achievement/AchievementCondition/medal tables decoded (318+139 rows)",
    "Mail": "mailconfig/mailinfo/privatemail tables decoded",
    "Shop": "shopconfig/shopgoodsgroup decoded; product content still server-side",
    "Task": "40 daily/weekly + taskcondition(1728) + activitytask(314) decoded",
    "Activity/Event": "worldboss*/tower*/activity*/challenge*/endless* tables decoded",
    "Draw": "drawrules/drawparam/card tables decoded",
    "Battle Entry": "3,203 sections + supporting dungeon/tower/worldboss tables decoded",
}
high_value = defaultdict(list)
for e in c2l_entries:
    if e["server_registered"] or e["client_status"] != "SEND_SITES_FOUND":
        continue
    dom = e["business_domain"]
    high_value[dom].append({
        "message_id": e["message_id"], "name": e["message_name"],
        "send_channels": e["send_channels"],
        "static_data_note": static_domains.get(dom),
    })
unhandled = {
    "generated_by": "tools/analysis/build_protocol_catalog.py",
    "note": "C2L requests the 2.4 client actually sends (send instantiation exists) but the "
            "Revival server has no handler; grouped by business domain",
    "domains": {k: sorted(v, key=lambda x: x["message_id"]) for k, v in sorted(high_value.items())},
    "total_unhandled_sent_c2l": sum(len(v) for v in high_value.values()),
}
(OUT / "unhandled_high_value.json").write_text(json.dumps(unhandled, ensure_ascii=False, indent=1),
                                               encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=1))
print("unhandled(sent) by domain:", {k: len(v) for k, v in sorted(high_value.items())})
no_send = sorted(e["message_name"] for e in c2l_entries if not e["send_channels"])
print("NO_SEND_POINT_IN_2_4:", no_send)
