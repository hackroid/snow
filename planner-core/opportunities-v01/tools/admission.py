#!/usr/bin/env python3
"""Ticket admission, two layers (method section 2).

Layer 1 - research readiness: the seven fields are verified
(valid_dates, scope, days_units, eligibility, deadline, sale_status,
source_trust). All True -> "research_ready"; anything else -> "held".
Research-ready only means the DATA is complete. It does NOT mean the
ticket fits any actual trip.

Layer 2 - trip applicability (admit): needs a real context built from
a planner-shaped spec: target resort, ALL ski dates, the purchase
moment as a timezone-aware timestamp, and membership as an explicit
fact PER SYSTEM (context["memberships"] = {"seibu_prince_club": True}).
"Free to join" is not membership, and another system's membership is
not Seibu eligibility. No context -> "held_for_trip_context".

Deadline rules are evaluated as instants, never date strings:
  "none"                    verified: no purchase deadline
  "fixed:YYYY-MM-DD"        purchase (JST) on/before that date
  "fixed:<ISO datetime>"    purchase at/before that instant
  "before_first_use:HH:MM"  purchase at/before HH:MM JST on the day
                            before the first ski date (e.g. Webket's
                            23:00 cutoff - 23:30 the day before FAILS)
A missing or unknown deadline_rule is held, never defaulted to pass.
Blackout dates are checked date by date. A pack (unit "sheet") or a
multi-day pass cannot price a trip here: quantity/sharing/leftover
rules are unsupported, so it stays held - never priced by average.
If the package already includes a ticket -> "alternative_only".
Run with python3 -B and PYTHONDONTWRITEBYTECODE=1."""
from datetime import datetime, time, timedelta, timezone

JST = timezone(timedelta(hours=9))
CHECKS = ("valid_dates", "scope", "days_units", "eligibility",
          "deadline", "sale_status", "source_trust")


def research_status(entry):
    reasons = [k for k in CHECKS if entry.get("checks", {}).get(k) is not True]
    if reasons:
        return {"status": "held", "reasons": reasons}
    return {"status": "research_ready", "reasons": []}


def _parse_purchase(raw):
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def _deadline_ok(entry, purchase, ski_dates):
    rule = entry.get("deadline_rule")
    if rule is None:
        return "deadline_rule_unknown"
    if rule == "none":
        return None
    if rule.startswith("fixed:"):
        spec = rule[len("fixed:"):]
        try:
            if "T" in spec:
                limit = datetime.fromisoformat(spec)
                if limit.tzinfo is None:
                    return "deadline_rule_unknown"
            else:
                y, m, d = (int(x) for x in spec.split("-"))
                limit = datetime(y, m, d, 23, 59, 59, tzinfo=JST)
        except ValueError:
            return "deadline_rule_unknown"
        return None if purchase <= limit else "deadline_passed"
    if rule.startswith("before_first_use:"):
        try:
            hh, mm = (int(x) for x in rule[len("before_first_use:"):].split(":"))
            limit_time = time(hh, mm)
        except ValueError:
            return "deadline_rule_unknown"
        if not ski_dates:
            return "deadline_passed"
        limit = datetime.combine(min(ski_dates) - timedelta(days=1),
                                 limit_time, tzinfo=JST)
        return None if purchase <= limit else "deadline_passed"
    return "deadline_rule_unknown"


def admit(entry, context=None):
    """Trip-level verdict. context keys (planner spec shape):
    resort_id, ski_dates (list of ISO dates), purchase_at (ISO
    datetime WITH timezone), memberships ({system: True}),
    package_includes_ticket."""
    if context and context.get("package_includes_ticket"):
        return {"verdict": "alternative_only",
                "reasons": ["package_includes_ticket"]}
    rs = research_status(entry)
    if rs["status"] != "research_ready":
        return {"verdict": "held", "stage": "research",
                "reasons": rs["reasons"]}
    if not context:
        return {"verdict": "held_for_trip_context",
                "reasons": ["no_context"]}
    reasons = []
    scope = entry.get("scope_resort_ids")
    if not scope:
        reasons.append("missing_field:scope_resort_ids")
    elif context.get("resort_id") not in scope:
        reasons.append("scope_mismatch")
    try:
        ski_dates = [datetime.fromisoformat(d).date()
                     for d in (context.get("ski_dates") or [])]
    except ValueError:
        ski_dates = []
    vf, vt = entry.get("valid_from"), entry.get("valid_to")
    if vf is None or vt is None:
        reasons.append("missing_field:validity")
    elif not ski_dates or any(d.isoformat() < vf or d.isoformat() > vt
                              for d in ski_dates):
        reasons.append("date_out_of_validity")
    blackout = entry.get("blackout_dates")
    if blackout is None:
        reasons.append("missing_field:blackout_dates")
    elif any(d.isoformat() in blackout for d in ski_dates):
        reasons.append("blackout_date")
    purchase = _parse_purchase(context.get("purchase_at"))
    if purchase is None:
        reasons.append("purchase_time_invalid")
    else:
        dl = _deadline_ok(entry, purchase, ski_dates)
        if dl:
            reasons.append(dl)
    system = entry.get("membership_system")
    if system:
        memberships = context.get("memberships") or {}
        if memberships.get(system) is not True:
            reasons.append("membership_unconfirmed:%s" % system)
    if entry.get("unit") != "person_day":
        reasons.append("pack_quantity_unverified")
    if reasons:
        return {"verdict": "held_for_trip_context", "reasons": reasons}
    return {"verdict": "admitted", "reasons": []}
