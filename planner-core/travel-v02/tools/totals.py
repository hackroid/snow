#!/usr/bin/env python3
"""Total-price computation, soft-reference check, grouping and dedupe.

Candidate JSON fields (per quote, never merged across platforms):
  id, source, plan_name, url, property (name or null for omakase),
  property_key (normalized identity or null), omakase (bool),
  base_per_person (JPY or null), pax,
  ticket_included_days (int), ticket_addons_per_person (JPY for the extra
    days this spec needs, or null if needed but unpriced),
  ticket_days_needed (int), meals (text), restrictions (text or null),
  cancel (text), parking (text), queried_at,
  price_unknown_reason (text or null)

Rules encoded (methods/method.md):
  - unknown price is never 0 and never "cheapest"; such quotes go to the
    incomplete zone.
  - a quote is price-complete only when base is known and every needed
    ticket day is either included or priced as an add-on.
  - soft references (NOT filters): 1 night/2 days <= 30000 per person,
    2 nights/3 days <= 40000 per person, ticket included. Over-reference
    quotes stay listed, flagged.
  - grouping is by property identity only; quotes stay separate whenever
    room/meals/ticket/cancel differ. Omakase never merges with a named
    property.
"""
import json

SOFT_REFERENCE = {(1, 2): 30000, (2, 3): 40000}


def missing_reason(c):
    """Why a quote is ticket-incomplete, from the actual uncovered ski days.

    A candidate's own recorded price_unknown_reason wins (it carries the
    product-level fact, e.g. 'no upgrade option on that page'). Otherwise the
    reason names the uncovered day range: tickets run from the arrival day,
    so with `included` days covered, days included+1..needed are missing.
    Never phrase it as a bare day count.
    """
    if c.get("price_unknown_reason"):
        return c["price_unknown_reason"]
    needed = c.get("ticket_days_needed", 0)
    included = c.get("ticket_included_days", 0)
    first, last = included + 1, needed
    span = "第%d个滑雪日" % first if first == last else "第%d–%d个滑雪日" % (first, last)
    return "%s票加购未核价（已含%d天、共需%d天）" % (span, included, needed)


def assess(candidate):
    c = dict(candidate)
    base = c.get("base_per_person")
    needed = c.get("ticket_days_needed", 0)
    included = c.get("ticket_included_days", 0)
    addon = c.get("ticket_addons_per_person")
    missing_days = max(0, needed - included)
    c["missing_ticket_days"] = missing_days
    if base is None and c.get("base_group_total") is not None:
        if missing_days > 0 and addon is None:
            c["per_person_total"] = None
            c["group_total"] = None
            c["complete"] = False
            c["incomplete_reason"] = missing_reason(c)
            return c
        group = c["base_group_total"] + (addon or 0) * c["pax"]
        c["per_person_total"] = group / c["pax"]
        c["group_total"] = group
        c["complete"] = True
        ref = SOFT_REFERENCE.get((c.get("nights"), needed))
        c["over_soft_reference"] = bool(ref is not None and c["per_person_total"] > ref)
        return c
    if base is None:
        c["per_person_total"] = None
        c["group_total"] = None
        c["complete"] = False
        c["incomplete_reason"] = c.get("price_unknown_reason") or "基础价 unknown"
        return c
    if missing_days > 0 and addon is None:
        c["per_person_total"] = None
        c["group_total"] = None
        c["complete"] = False
        c["incomplete_reason"] = missing_reason(c)
        return c
    per_person = base + (addon or 0)
    c["per_person_total"] = per_person
    c["group_total"] = per_person * c["pax"]
    c["complete"] = True
    ref = SOFT_REFERENCE.get((c.get("nights"), needed))
    c["over_soft_reference"] = bool(ref is not None and per_person > ref)
    return c


def group_quotes(candidates):
    """Group quote ids by property identity; omakase and unidentified stay solo."""
    groups = {}
    for cand in candidates:
        key = cand.get("property_key")
        if cand.get("omakase") or not key:
            key = "solo:" + cand["id"]
        groups.setdefault(key, []).append(cand["id"])
    return groups


def sort_for_report(candidates):
    assessed = [assess(c) for c in candidates]
    complete = sorted((c for c in assessed if c["complete"]),
                      key=lambda c: c["per_person_total"])
    incomplete = [c for c in assessed if not c["complete"]]
    return complete, incomplete


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
