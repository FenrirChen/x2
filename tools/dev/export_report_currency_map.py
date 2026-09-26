"""Export the E_ReportCurrency proxy-item map for the server.

Official Item rows with FunctionEff=E_ReportCurrency(14) are battle-internal
currency proxies: EffData=[currencyBucket, perUnitValue]. They must never be
granted as bag items; the settlement converts them into the account currency.

Account currency resolution (canonical, table-derived — not a hardcoded formula):
the account Item whose ItemType==E_Currency and EffData==[bucket].
Proxies whose bucket has no such account Item are excluded here and must be
treated as unresolved by the server (never guessed).

Source: analysis/drop_archaeology/full_tables/item.json (official 2.4, read-only).
Output: src/x2server/data/report_currency_map.json
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FULL = ROOT.parent / "analysis/drop_archaeology/full_tables"
OUT = ROOT / "src/x2server/data/report_currency_map.json"


def main():
    items = json.loads((FULL / "item.json").read_text(encoding="utf-8"))["records"]
    account = {}
    for row in items:
        if row.get("ItemType", {}).get("value") == 16:  # E_Currency
            eff = row.get("EffData") or []
            if len(eff) == 1:
                account.setdefault(eff[0], row["ItemID"])
    mapping = {}
    skipped = []
    for row in items:
        if row.get("FunctionEff", {}).get("value") != 14:  # E_ReportCurrency
            continue
        eff = row.get("EffData") or []
        bucket = eff[0] if len(eff) >= 1 else None
        per_unit = eff[1] if len(eff) >= 2 else None
        account_id = account.get(bucket)
        if bucket is None or per_unit is None or account_id is None:
            skipped.append(row["ItemID"])
            continue
        mapping[str(row["ItemID"])] = {
            "bucket": bucket, "per_unit": per_unit, "account_item_id": account_id,
        }
    data = {
        "source": "analysis/drop_archaeology/full_tables/item.json FunctionEff=E_ReportCurrency(14); "
                  "account currency = the E_Currency Item whose EffData==[bucket]",
        "items": mapping,
        "unresolvable": skipped,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT}: {len(mapping)} proxies, unresolvable={skipped}")


if __name__ == "__main__":
    main()
