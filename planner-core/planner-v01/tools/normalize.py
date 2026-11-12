#!/usr/bin/env python3
"""planner quote normalizer (method section 6): turn raw per-source
quote records into combiner-ready candidates on one caliber.

- Required per quote: platform, property_group, name, url,
  quote_read_at, pricing_basis ("per_person" | "room"), resort_id.
- per_person basis: known subtotal per person = base_per_person +
  ticket_addon_per_person; group = per-person x adults.
- room basis: group = room_price_total + ticket_addon_per_person x
  adults; per-person is display-only (the combiner rounds half-up).
- If tickets are required and their cost is neither included nor a
  known add-on, the known subtotal stays None (never a partial sum
  dressed as a subtotal, never 0).
- If a raw quote claims its own subtotals, they must match the
  computed ones within 1 yen per person; a mismatch refuses the
  quote. Missing/invalid required fields refuse the quote.
- Lodging area is not the ski target: a quote carries its ticket
  validation in its ticket_* fields for the route actually priced
  (ticket_route). An off-area property priced with a verified
  target-resort ticket (self-drive route) is complete on that
  route; a cross-resort ticket is only required when that route
  is the one being priced.
Refusals are collected per quote; good quotes still normalize.
"""
import argparse
import json
import math
import sys

REQUIRED = ("platform", "property_group", "name", "url", "quote_read_at",
            "pricing_basis", "resort_id")


class QuoteRefusal(Exception):
    pass


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _money(v):
    return _num(v) and math.isfinite(v) and v >= 0


def normalize_quote(spec, q):
    for k in REQUIRED:
        if not q.get(k):
            raise QuoteRefusal("missing required field %s" % k)
    adults = spec["adults"]
    need_ticket = bool(spec["tickets_each_day"])
    if "ticket_included_in_base" in q \
            and not isinstance(q["ticket_included_in_base"], bool):
        raise QuoteRefusal("ticket_included_in_base must be a boolean "
                           "(got %r)" % (q["ticket_included_in_base"],))
    included = q.get("ticket_included_in_base") is True
    addon = q.get("ticket_addon_per_person")
    if addon is not None and not _money(addon):
        raise QuoteRefusal("ticket_addon_per_person not a finite "
                           "non-negative number")
    source = q.get("ticket_source")
    if source is not None:
        if source not in ("included", "package_addon", "external"):
            raise QuoteRefusal("ticket_source %r is not one of "
                               "included/package_addon/external" % (source,))
        if included and source != "included":
            raise QuoteRefusal("ticket_included_in_base=True contradicts "
                               "ticket_source %r" % (source,))
        if source == "included" and not included:
            raise QuoteRefusal("ticket_source 'included' without "
                               "ticket_included_in_base=True")
    ticket_cost_known = (not need_ticket) or addon is not None or included
    addon_eff = addon if addon is not None else 0
    basis = q["pricing_basis"]
    pp = group = None
    if basis == "per_person":
        base = q.get("base_per_person")
        if not _money(base):
            raise QuoteRefusal("per_person basis without a finite "
                               "non-negative base_per_person")
        if ticket_cost_known:
            pp = base + addon_eff
            group = pp * adults
    elif basis == "room":
        room_total = q.get("room_price_total")
        if not _money(room_total):
            raise QuoteRefusal("room basis without a finite "
                               "non-negative room_price_total")
        if ticket_cost_known:
            group = room_total + addon_eff * adults
            pp = group / adults
    else:
        raise QuoteRefusal("unknown pricing_basis %r" % basis)
    claimed_pp, claimed_g = q.get("claimed_per_person_subtotal"), q.get("claimed_group_subtotal")
    for cv in (claimed_pp, claimed_g):
        if cv is not None and not _money(cv):
            raise QuoteRefusal("claimed subtotal not a finite non-negative number")
    if claimed_pp is not None and pp is not None and abs(claimed_pp - pp) > 1:
        raise QuoteRefusal("claimed per-person subtotal %r != computed %r" % (claimed_pp, pp))
    if claimed_g is not None and group is not None and abs(claimed_g - group) > adults:
        raise QuoteRefusal("claimed group subtotal %r != computed %r" % (claimed_g, group))
    out = dict(q)
    out["per_person_known_subtotal"] = pp
    out["group_known_subtotal"] = group
    out.pop("claimed_per_person_subtotal", None)
    out.pop("claimed_group_subtotal", None)
    return out


def normalize_batch(spec, quotes):
    good, refused = [], []
    for q in quotes:
        try:
            good.append(normalize_quote(spec, q))
        except QuoteRefusal as e:
            refused.append({"name": q.get("name"), "platform": q.get("platform"),
                            "reason": str(e)})
    return good, refused


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec_json")
    ap.add_argument("quotes_json")
    a = ap.parse_args()
    spec = json.load(open(a.spec_json, encoding="utf-8"))
    quotes = json.load(open(a.quotes_json, encoding="utf-8"))
    good, refused = normalize_batch(spec, quotes)
    print(json.dumps({"candidates": good, "refused": refused},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
