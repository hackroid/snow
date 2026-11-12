# -*- coding: utf-8 -*-
"""Reusable batch fee/deadline check (the actual calling path).

Usage:
  python3 fee_check.py --spec <spec.json> --rules <rules.json> \
      --purchase-at <ISO datetime with timezone>
Reads the spec's ski dates (first_ski_date + ski_days), applies the
structured parking rule per day and each ticket deadline rule at the
purchase moment, and prints JSON verdicts plus ready-to-paste
human-readable lines. Rules live with the batch (source + source_time
kept in the rules file); nothing here invents a fee or a cutoff."""
import argparse, json, sys
from datetime import date, timedelta
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from date_rules import parking_fee, deadline_status


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--rules", required=True)
    ap.add_argument("--purchase-at", required=True)
    a = ap.parse_args()
    spec = json.load(open(a.spec, encoding="utf-8"))
    rules = json.load(open(a.rules, encoding="utf-8"))
    first = date.fromisoformat(spec["first_ski_date"])
    days = [first + timedelta(days=i) for i in range(spec["ski_days"])]
    out = {"spec": {"resort_id": spec.get("resort_id"),
                    "first_ski_date": spec["first_ski_date"],
                    "ski_days": spec["ski_days"],
                    "adults": spec.get("adults")},
           "purchase_at": a.purchase_at, "parking": [], "deadlines": []}
    lines = []
    pr = rules.get("parking")
    for d in days:
        v = parking_fee(pr, d)
        out["parking"].append({"date": d.isoformat(), **v})
        lines.append("停车 %s：%s" % (d.isoformat(),
                       ("¥%s/车" % v["fee"]) if v["fee"] is not None else "待核")
                     + "（%s）" % v["basis"])
    for t in rules.get("ticket_deadlines", []):
        v = deadline_status(t, a.purchase_at)
        out["deadlines"].append({"id": t.get("id"), **v})
        lines.append("截止 %s：%s（%s）" % (t.get("id"), v["status"], v["basis"]))
    out["lines"] = lines
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
