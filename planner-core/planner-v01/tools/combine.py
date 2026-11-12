#!/usr/bin/env python3
"""planner-v01 combiner v2: validate a planner batch JSON against its
shared spec, then render the combined lodging+conditions report
(Markdown, and optionally a semantic card-style HTML file).

Hardening (methods/method.md section 3):
- The shared spec itself is validated first: kind, real first-ski date,
  resort, positive-integer nights/adults/rooms/ski_days (bool is not an
  int), tickets_each_day as an explicit bool, currency JPY only.
- Both source sections must carry a complete spec_echo (all four keys
  present with real values), their own resort_id and explicit currency.
  A missing echo key is a hold, never a silent match of two Nones.
- A candidate whose resort differs from the spec refuses the splice.
- Ticket completeness is a triad: ski days, covered people, resort
  scope, and start date; anything unverified marks the candidate
  incomplete instead of defaulting to covered.
- Forecasts are computed from structured source fields (issued +
  coverage_end) against the spec's actual ski dates. A claimed
  status of in_window is never trusted; missing deadlines render as
  pending-verification, true overruns as pending-recheck, and no
  summary value leaks in either case.
- kind labels come only from spec.kind; test stays test, and actual
  renders as a planning draft, never as a confirmed trip or booking.
Display rounding reuses travel-v02's yen_int (half-up).
"""
import argparse
import copy
import datetime
import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TRAVEL_TOOLS = os.path.normpath(os.path.join(HERE, "..", "..", "travel-v02", "tools"))
sys.path.insert(0, TRAVEL_TOOLS)
from report import yen_int  # noqa: E402  (travel-v02 display rounding, shared)

OPP_TOOLS = os.path.normpath(os.path.join(HERE, "..", "..", "opportunities-v01", "tools"))
sys.path.insert(0, OPP_TOOLS)
sys.path.insert(0, HERE)
import admission  # noqa: E402  (opportunities-v01 two-layer ticket gate, shared)
from normalize import _money  # noqa: E402  (planner amount gate, shared)
import date_rules  # noqa: E402  (structured date-rule verdicts, shared)

ECHO_KEYS = ("first_ski_date", "nights", "adults", "rooms")


class Refusal(Exception):
    """Raised when the spec or a splice is invalid; nothing renders."""


def _pos_int(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 1


def _parse_date(v, what):
    if not isinstance(v, str):
        raise Refusal("%s must be an ISO date string, got %r" % (what, v))
    try:
        return datetime.date.fromisoformat(v)
    except ValueError:
        raise Refusal("%s is not a valid date: %r" % (what, v))


def validate_spec(spec):
    if not isinstance(spec, dict) or not spec:
        raise Refusal("spec missing")
    if spec.get("kind") not in ("test", "actual"):
        raise Refusal("spec.kind must be 'test' or 'actual', got %r" % spec.get("kind"))
    _parse_date(spec.get("first_ski_date"), "spec.first_ski_date")
    if not isinstance(spec.get("resort_id"), str) or not spec["resort_id"]:
        raise Refusal("spec.resort_id missing")
    for key in ("nights", "adults", "rooms", "ski_days"):
        if not _pos_int(spec.get(key)):
            raise Refusal("spec.%s must be an explicit positive integer, got %r"
                          % (key, spec.get(key)))
    if not isinstance(spec.get("tickets_each_day"), bool):
        raise Refusal("spec.tickets_each_day must be an explicit boolean, got %r"
                      % spec.get("tickets_each_day"))
    if spec.get("currency") != "JPY":
        raise Refusal("spec.currency must be JPY at this stage, got %r" % spec.get("currency"))
    ex = spec.get("ticket_exempt_people")
    if ex is not None:
        if not (isinstance(ex, int) and not isinstance(ex, bool)
                and 0 <= ex <= spec["adults"]):
            raise Refusal("spec.ticket_exempt_people must be a non-bool integer "
                          "in 0..adults, got %r" % ex)
        if ex > 0 and not spec.get("ticket_holders_note"):
            raise Refusal("spec.ticket_exempt_people=%d has no stated basis "
                          "(ticket_holders_note missing); exemption cannot "
                          "silently erase the ticket need" % ex)
        if 0 < ex < spec["adults"]:
            raise Refusal("mixed ticket exemption (%d of %d exempt) is not "
                          "implemented in this version: per-person pricing is "
                          "required, hold instead of pretending support"
                          % (ex, spec["adults"]))
    return spec


def _echo_check(name, echo, spec):
    if not isinstance(echo, dict):
        raise Refusal("%s spec_echo missing (source not normalized; hold)" % name)
    for key in ECHO_KEYS:
        if echo.get(key) is None:
            raise Refusal("%s spec_echo.%s missing (source not verified; hold)" % (name, key))
        if echo.get(key) != spec.get(key):
            raise Refusal("%s spec_echo.%s=%r != spec.%s=%r"
                          % (name, key, echo.get(key), key, spec.get(key)))


def _require_text_list(batch, field):
    """Top-level text-list contract: missing / recheck / choice_directions,
    when the key is present, must be a list of non-empty strings. Absent
    key = empty (optional). An explicit null/str/dict/number, or any
    non-string or blank member, is refused with the field position --
    never silently coerced (a bare str would render character by
    character) and never swallowed into empty."""
    if field not in batch:
        return
    v = batch[field]
    if not isinstance(v, list):
        raise Refusal("%s must be a list of non-empty strings, got %s"
                      % (field, type(v).__name__))
    for i, item in enumerate(v):
        if not isinstance(item, str) or not item.strip():
            raise Refusal("%s[%d] must be a non-empty string, got %r"
                          % (field, i, item))


def compute_date_facts(batch):
    """Recompute this run's date verdicts from the batch's structured
    date_rules (never from free text, never from an input-carried
    date_facts -- prepare discards those). Parking is judged per ski
    date (explicit dates/ranges before the weekday default, inside
    date_rules); ticket deadlines are judged at this run's
    purchase_context.purchase_at in the rule's declared timezone.
    A deadline verdict is NOT ticket admissibility: screening decides
    that separately. No rules -> no facts -> nothing rendered."""
    rules = batch.get("date_rules")
    if rules is None:
        return
    if not isinstance(rules, dict):
        raise Refusal("date_rules must be an object")
    spec = validate_spec(batch.get("spec"))
    first = datetime.date.fromisoformat(spec["first_ski_date"])
    days = [first + datetime.timedelta(days=i)
            for i in range(spec["ski_days"])]
    facts = {"ski_dates": [d.isoformat() for d in days]}
    pr = rules.get("parking")
    if pr is not None:
        if not isinstance(pr, dict):
            raise Refusal("date_rules.parking must be an object")
        facts["parking"] = [dict(date=d.isoformat(),
                                 **date_rules.parking_fee(pr, d))
                            for d in days]
        facts["parking_source"] = pr.get("source")
        facts["parking_source_time"] = pr.get("source_time")
    dls = rules.get("ticket_deadlines")
    if dls is not None:
        if not isinstance(dls, list):
            raise Refusal("date_rules.ticket_deadlines must be a list")
        pa = (batch.get("purchase_context") or {}).get("purchase_at")
        facts["purchase_at"] = pa
        facts["deadlines"] = [
            dict(id=(t.get("id") if isinstance(t, dict) else None),
                 **date_rules.deadline_status(
                     t if isinstance(t, dict) else {}, pa))
            for t in dls]
    batch["date_facts"] = facts


_DATE_STATUS_ZH = {"before_deadline": "未到截止",
                   "after_deadline": "已过截止",
                   "boundary_day_unverified": "截止日当日·时分待核",
                   "not_applicable": "无截止规则",
                   "unknown": "未知/待核"}


def _date_facts_lines(batch):
    f = batch.get("date_facts")
    if not f:
        return []
    out = ["停车与截止由结构化规则经 date_rules 计算（规则来源：%s；源时刻：%s；"
           "购买时刻：%s）" % (f.get("parking_source") or "见规则输入",
                             f.get("parking_source_time") or "见规则输入",
                             f.get("purchase_at") or "未提供")]
    for p in f.get("parking", []):
        fee = "待核" if p["fee"] is None else "¥{:,}/车".format(yen_int(p["fee"]))
        out.append("停车 %s：%s（%s）" % (p["date"], fee, p["basis"]))
    for d in f.get("deadlines", []):
        out.append("截止 %s：%s（%s）"
                   % (d.get("id"), _DATE_STATUS_ZH.get(d["status"], d["status"]),
                      d["basis"]))
    out.append("注：截止判定只比较购买时刻与截止日，不代表票可购或可用；"
               "票的结论以票筛选为准。")
    return out


def validate(batch):
    spec = validate_spec(batch.get("spec"))
    for _f in ("missing", "recheck", "choice_directions"):
        _require_text_list(batch, _f)
    for name in ("lodging", "conditions"):
        sec = batch.get(name)
        if not isinstance(sec, dict):
            raise Refusal("%s section missing" % name)
        _echo_check(name, sec.get("spec_echo"), spec)
        if sec.get("resort_id") != spec["resort_id"]:
            raise Refusal("%s resort_id %r != spec resort_id %r"
                          % (name, sec.get("resort_id"), spec["resort_id"]))
        if sec.get("currency") != spec["currency"]:
            raise Refusal("%s currency %r != spec currency %r"
                          % (name, sec.get("currency"), spec["currency"]))
        if sec.get("kind") is not None and sec.get("kind") != spec["kind"]:
            raise Refusal("%s kind %r conflicts with spec.kind %r"
                          % (name, sec.get("kind"), spec["kind"]))
    for c in batch["lodging"].get("candidates", []):
        if c.get("resort_id") != spec["resort_id"]:
            raise Refusal("candidate %r resort_id %r != spec resort_id %r (off-resort splice)"
                          % (c.get("name"), c.get("resort_id"), spec["resort_id"]))
    apply_ticket_screening(batch)
    compute_date_facts(batch)
    return spec


def money(v):
    return "unknown" if v is None else "¥{:,}".format(yen_int(v))


def candidate_status(spec, c):
    """Ticket triad: days, people, resort scope, start date.
    Returns a reason string when incomplete, else None."""
    if not spec["tickets_each_day"]:
        return None
    need_people = spec["adults"] - (spec.get("ticket_exempt_people") or 0)
    if need_people == 0:
        return None  # all exempt with a stated basis (validated in spec)
    reasons = []
    need_days = spec["ski_days"]
    covered = c.get("ticket_days_covered")
    if covered is None or covered < need_days:
        reasons.append("票天数不足/未验证（覆盖 %s 天，需要 %d 天）"
                       % ("unknown" if covered is None else covered, need_days))
    covers_people = c.get("ticket_covers_people")
    if covers_people is None or covers_people < need_people:
        reasons.append("票覆盖人数不足/未验证（覆盖 %s 人，需要 %d 人）"
                       % ("unknown" if covers_people is None else covers_people, need_people))
    scope = c.get("ticket_scope_resort_ids")
    if not scope or spec["resort_id"] not in scope:
        reasons.append("票适用范围未覆盖目标雪场/未验证（范围 %s，目标 %s）"
                       % ("unknown" if not scope else "/".join(scope), spec["resort_id"]))
    if c.get("ticket_start_date") != spec["first_ski_date"]:
        reasons.append("票起始日未覆盖首滑日/未验证（起始 %s，首滑日 %s）"
                       % (c.get("ticket_start_date") or "unknown", spec["first_ski_date"]))
    return "；".join(reasons) if reasons else None


def _ski_dates(spec):
    first = _parse_date(spec["first_ski_date"], "spec.first_ski_date")
    return [(first + datetime.timedelta(days=i)).isoformat()
            for i in range(spec["ski_days"])]


def _valid_days(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 1


def _offer_effective(spec, offer, verdict):
    """Per-person cost of an admitted offer covering ALL ski days, or
    None. Amount/type gates are the planner's own (normalize._money,
    non-bool positive-int days, repeatable only when explicitly True):
    a negative price never becomes the cheapest, and a string "false"
    is never truthy-repeatable."""
    if verdict != "admitted":
        return None
    days, price = offer.get("days_covered"), offer.get("price_per_person")
    if not _valid_days(days) or not _money(price):
        return None
    if days >= spec["ski_days"]:
        result = price
    elif offer.get("repeatable") is True and days == 1:
        result = price * spec["ski_days"]
    else:
        return None
    return result if _money(result) else None


def _recompute_subtotals(spec, c):
    """Same formulas as normalize.py, behind the same amount gate;
    only called after screening has set a verified ticket addon on a
    candidate that had none. A base or addon failing _money leaves the
    subtotals None instead of producing a number."""
    addon = c.get("ticket_addon_per_person")
    if addon is not None and not _money(addon):
        c["per_person_known_subtotal"] = None
        c["group_known_subtotal"] = None
        return
    if c.get("pricing_basis") == "room":
        room = c.get("room_price_total")
        if room is None or not _money(room) or addon is None:
            c["per_person_known_subtotal"] = None
            c["group_known_subtotal"] = None
            return
        group = room + addon * spec["adults"]
        pp = group / spec["adults"]
        if not (_money(group) and _money(pp)):
            c["per_person_known_subtotal"] = None
            c["group_known_subtotal"] = None
            return
        c["group_known_subtotal"] = group
        c["per_person_known_subtotal"] = pp
    else:
        base = c.get("base_per_person")
        if base is None or not _money(base) or addon is None:
            c["per_person_known_subtotal"] = None
            c["group_known_subtotal"] = None
            return
        pp = base + addon
        group = pp * spec["adults"]
        if not (_money(group) and _money(pp)):
            c["per_person_known_subtotal"] = None
            c["group_known_subtotal"] = None
            return
        c["per_person_known_subtotal"] = pp
        c["group_known_subtotal"] = group


def _reset_derived(spec, c):
    """Recompute a candidate's ticket state from its unchanged base
    price and its explicit ticket_source (prepare step, screening runs
    and actual quotes). ticket_source separates provenance from the
    pricing basis - room is not bare room, per_person is not package:
      "included"      base price already contains the ticket (source
                      evidence: ticket_included_in_base): the own
                      ticket path stands on either basis, never
                      stripped, never deducted, even when all-exempt.
      "package_addon" the package's own add-on ticket: stands, unless
                      it is a prior screening selection in disguise
                      (ticket_selected_offer set), which is stripped
                      and re-screened as external.
      "external"      ticket is bought outside / absent: any recorded
                      addon is an earlier round's attachment, never
                      package evidence - strip it and rebuild from
                      the base price (all-exempt: base-only subtotal,
                      only the external cost is removed).
    A candidate carrying ticket fields but no valid ticket_source
    refuses: provenance is not guessed from the pricing basis. A base
    price missing or failing the amount gate likewise refuses."""
    need_people = spec["adults"] - (spec.get("ticket_exempt_people") or 0)
    basis = c.get("pricing_basis")
    if basis == "room":
        if not _money(c.get("room_price_total")):
            raise Refusal("candidate %r has no valid room-price base; "
                          "derived subtotals cannot be recomputed, "
                          "refusing to treat it as a new quote" % c.get("name"))
    elif basis == "per_person":
        if not _money(c.get("base_per_person")):
            raise Refusal("candidate %r has no valid per-person base; "
                          "refusing to treat it as a new quote" % c.get("name"))
    else:
        raise Refusal("candidate %r pricing_basis %r cannot be "
                      "recomputed from a base price" % (c.get("name"), basis))
    src = c.get("ticket_source")
    included_flag = c.get("ticket_included_in_base") is True
    if included_flag and src != "included":
        raise Refusal("candidate %r ticket_included_in_base=True "
                      "contradicts ticket_source %r" % (c.get("name"), src))
    if src == "included" and not included_flag:
        raise Refusal("candidate %r ticket_source 'included' without "
                      "ticket_included_in_base=True" % c.get("name"))
    has_ticket_fields = (c.get("ticket_addon_per_person") is not None
                         or c.get("ticket_days_covered") is not None
                         or included_flag
                         or c.get("ticket_selected_offer"))
    if src not in ("included", "package_addon", "external"):
        if has_ticket_fields:
            raise Refusal("candidate %r carries ticket fields but no "
                          "verified ticket_source; refusing to guess "
                          "provenance for a new quote" % c.get("name"))
        src = "external"  # no own ticket recorded at all
    if src == "included":
        return
    if src == "package_addon" and not c.get("ticket_selected_offer"):
        return
    for k in ("ticket_addon_per_person", "ticket_days_covered",
              "ticket_covers_people", "ticket_scope_resort_ids",
              "ticket_start_date", "ticket_selected_offer"):
        c[k] = None
    if need_people == 0 or not spec["tickets_each_day"]:
        if basis == "room":
            room = c.get("room_price_total")
            group, pp = room, room / spec["adults"]
        else:
            base = c.get("base_per_person")
            pp, group = base, base * spec["adults"]
        if _money(group) and _money(pp):
            c["group_known_subtotal"] = group
            c["per_person_known_subtotal"] = pp
        else:
            c["per_person_known_subtotal"] = None
            c["group_known_subtotal"] = None
    else:
        c["per_person_known_subtotal"] = None
        c["group_known_subtotal"] = None


def prepare(batch):
    """Public entry preparation (method section 6). Works on a deep
    copy - the caller's dict is never mutated. An input-carried
    _screening_applied marker or prior ticket_screening records are
    discarded, never trusted: screening always reruns on this run's
    spec/purchase_context, so re-preparing the same object after
    changing dates, purchase moment or memberships recomputes.
    kind=actual requires this run's ticket_offers AND purchase_context
    (missing -> Refusal; an explicitly empty offer list means no
    add-on is available and unverified DIY ticket prices do not
    survive the base reset). kind=test without ticket_offers is
    historical display only: stored subtotals render unchanged under
    an explicit not-verified-this-round label."""
    b = copy.deepcopy(batch)
    b.pop("_screening_applied", None)
    b.pop("ticket_screening", None)
    b.pop("date_facts", None)
    spec = validate_spec(b.get("spec"))
    if spec["kind"] == "actual" and ("ticket_offers" not in b or "purchase_context" not in b):
        raise Refusal("actual quote requires this run's ticket_offers and "
                      "purchase_context inputs (missing input refuses; an "
                      "explicitly empty offer list is allowed)")
    if "ticket_offers" in b or spec["kind"] == "actual":
        for c in b["lodging"].get("candidates", []):
            _reset_derived(spec, c)
    elif spec["kind"] == "test":
        b["historical_display"] = True
    validate(b)
    return b


def apply_ticket_screening(batch):
    """Optional stage (method section 6): when the batch carries
    ticket_offers + purchase_context from THIS run's input, screen the
    offers per candidate with opportunities' admission. Spec, purchase
    moment and memberships come from the batch input of this run,
    never injected by a demo. A candidate whose own ticket path is
    already fully verified keeps it (offers become alternative_only,
    never deducted). A partial own ticket (e.g. 1 of 2 days) keeps its
    gap: offers are screened for the record but never fill it, and the
    candidate is never skipped on a bare included-flag. A candidate
    with no own ticket path gets the cheapest admitted fully-covering
    offer; held offers never enter any subtotal."""
    offers = batch.get("ticket_offers")
    if offers is None or batch.get("_screening_applied"):
        return
    batch["_screening_applied"] = True
    spec = batch["spec"]
    pctx = batch.get("purchase_context") or {}
    base_ctx = {"resort_id": spec["resort_id"], "ski_dates": _ski_dates(spec),
                "purchase_at": pctx.get("purchase_at"),
                "memberships": pctx.get("memberships") or {}}
    need_people = spec["adults"] - (spec.get("ticket_exempt_people") or 0)
    records = []
    for c in batch["lodging"].get("candidates", []):
        own_gap = candidate_status(spec, c) if spec["tickets_each_day"] else None
        own_days = c.get("ticket_days_covered") or 0
        rec = {"candidate": c["name"], "own_ticket_gap": own_gap, "offers": []}
        if own_gap is None:
            for o in offers:
                v = admission.admit(o, {**base_ctx, "package_includes_ticket": True})
                rec["offers"].append({"offer": o.get("name"),
                                      "research": admission.research_status(o)["status"],
                                      "verdict": v["verdict"], "reasons": v["reasons"],
                                      "applied": False})
        elif own_days >= 1:
            for o in offers:
                v = admission.admit(o, base_ctx)
                rec["offers"].append({"offer": o.get("name"),
                                      "research": admission.research_status(o)["status"],
                                      "verdict": v["verdict"], "reasons": v["reasons"],
                                      "applied": False,
                                      "note": "套餐票部分覆盖，缺口保留；优惠票不填充（组合使用未核）"})
        else:
            best = None
            for o in offers:
                v = admission.admit(o, base_ctx)
                eff = _offer_effective(spec, o, v["verdict"])
                rec["offers"].append({"offer": o.get("name"),
                                      "research": admission.research_status(o)["status"],
                                      "verdict": v["verdict"], "reasons": v["reasons"],
                                      "effective_per_person": eff, "applied": False})
                if eff is not None and (best is None or eff < best[1]):
                    best = (o, eff)
            if best is not None:
                o, eff = best
                base_ok = _money(c.get("room_price_total")) \
                    if c.get("pricing_basis") == "room" else _money(c.get("base_per_person"))
                if not base_ok:
                    rec["note"] = "基底金额未过金额门，未选用任何优惠票"
                    best = None
            if best is not None:
                o, eff = best
                c["ticket_addon_per_person"] = eff
                c["ticket_days_covered"] = spec["ski_days"]
                c["ticket_covers_people"] = need_people
                c["ticket_scope_resort_ids"] = o.get("scope_resort_ids")
                c["ticket_start_date"] = spec["first_ski_date"]
                c["ticket_selected_offer"] = o.get("name")
                _recompute_subtotals(spec, c)
                for r in rec["offers"]:
                    if r["offer"] == o.get("name"):
                        r["applied"] = True
        records.append(rec)
    batch["ticket_screening"] = {"purchase_context": pctx, "records": records}


def screening_lines(batch):
    ts = batch.get("ticket_screening")
    if not ts:
        return []
    lines = ["## 票筛选（本轮输入的优惠票经 admission 两层核验）",
             "- 购买时刻（本轮输入）：%s；会员体系事实（本轮输入）：%s"
             % (ts["purchase_context"].get("purchase_at", "未给"),
                ts["purchase_context"].get("memberships") or "未给/未知")]
    for rec in ts["records"]:
        own = "自有票已全覆盖" if rec["own_ticket_gap"] is None \
            else "自有票缺口：%s" % rec["own_ticket_gap"]
        lines.append("- %s（%s）" % (rec["candidate"], own))
        if rec.get("note"):
            lines.append("  - %s" % rec["note"])
        for o in rec["offers"]:
            extra = ""
            if o.get("effective_per_person") is not None:
                extra = "；覆盖全程人均 %s" % money(o["effective_per_person"])
            if o.get("applied"):
                extra += "；**已选用计入小计**"
            if o.get("note"):
                extra += "；%s" % o["note"]
            lines.append("  - %s：资料 %s / 行程 %s%s%s"
                         % (o["offer"], o["research"], o["verdict"],
                            ("（%s）" % "、".join(o["reasons"])) if o["reasons"] else "",
                            extra))
    return lines


def screening_html(batch):
    ts = batch.get("ticket_screening")
    if not ts:
        return ""
    items = []
    for rec in ts["records"]:
        own = "自有票已全覆盖" if rec["own_ticket_gap"] is None \
            else "自有票缺口：%s" % rec["own_ticket_gap"]
        sub = []
        if rec.get("note"):
            sub.append("<li>%s</li>" % _esc(rec["note"]))
        for o in rec["offers"]:
            extra = ""
            if o.get("effective_per_person") is not None:
                extra += "；覆盖全程人均 %s" % money(o["effective_per_person"])
            if o.get("applied"):
                extra += "；已选用计入小计"
            if o.get("note"):
                extra += "；%s" % o["note"]
            sub.append("<li>%s：资料 %s / 行程 %s%s%s</li>" % (
                _esc(o["offer"]), _esc(o["research"]), _esc(o["verdict"]),
                _esc(("（%s）" % "、".join(o["reasons"])) if o["reasons"] else ""),
                _esc(extra)))
        items.append("<li>%s（%s）<ul>%s</ul></li>"
                     % (_esc(rec["candidate"]), _esc(own), "".join(sub)))
    return ("<section><details><summary>票筛选详细日志（本轮输入的优惠票经 admission 两层核验）</summary>"
            "<p>购买时刻（本轮输入）：%s；会员体系事实（本轮输入）：%s</p>"
            "<ul>%s</ul></details></section>"
            % (_esc(ts["purchase_context"].get("purchase_at", "未给")),
               _esc(ts["purchase_context"].get("memberships") or "未给/未知"),
               "".join(items)))


def _parse_dt(v):
    """ISO datetime with a timezone, or None (naive/unparseable rejected)."""
    if not isinstance(v, str):
        return None
    try:
        dt = datetime.datetime.fromisoformat(v)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


# JMA forecasts publish three times daily (05/11/17 JST); an issue time
# more than 24h before this batch's real read time has missed several
# cycles and is treated as a stale cache, per conditions-v01 freshness.
FORECAST_MAX_AGE = datetime.timedelta(hours=24)


def forecast_line(cond, spec):
    """Compute the forecast display from structured source fields only.
    A claimed status is ignored. The issue time must parse with a
    timezone, be neither in the future nor stale against this batch's
    real read time (conditions read_at), and the applicability range
    must be complete. Any gap renders pending-verification with no
    summary values; a true overrun renders pending-recheck."""
    fc = cond.get("forecast", {})
    first = _parse_date(spec["first_ski_date"], "spec.first_ski_date")
    last = first + datetime.timedelta(days=spec["ski_days"] - 1)
    issued_raw = fc.get("issued")
    start_raw, end_raw = fc.get("applies_from"), fc.get("coverage_end")
    if not issued_raw or not start_raw or not end_raw:
        return ("天气预报：待核（来源未给结构化发布时间/完整适用起止），不渲染预测值")
    issued_dt = _parse_dt(issued_raw)
    if issued_dt is None:
        return ("天气预报：待核（来源发布时间不可解析/无时区：%r），不渲染预测值"
                % issued_raw)
    read_dt = _parse_dt(cond.get("read_at"))
    if read_dt is None:
        return "天气预报：待核（本批读取时刻缺失/不可解析，无法判断新鲜度），不渲染预测值"
    age = read_dt - issued_dt
    if age.total_seconds() < 0:
        return "天气预报：待核（来源发布时间晚于本批读取时刻，时间异常），不渲染预测值"
    if age > FORECAST_MAX_AGE:
        return ("天气预报：待核（来源发布时间距本批读取时刻已超 24 小时，"
                "按 JMA 一日三发节奏已过期），不渲染预测值")
    try:
        start = datetime.date.fromisoformat(start_raw)
        end = datetime.date.fromisoformat(end_raw)
    except (TypeError, ValueError):
        return "天气预报：待核（来源适用起止不可解析），不渲染预测值"
    if start > end:
        return "天气预报：待核（来源适用起止倒置），不渲染预测值"
    if first < start or last > end:
        return ("天气预报：超预报范围（来源适用 %s 至 %s），无法预测，待临近复核（复核点：%s）"
                % (start_raw, end_raw, fc.get("recheck_at", "进入 JMA 一周预报覆盖后")))
    summary = fc.get("summary")
    if not summary:
        return "天气预报：窗口内但来源未给内容，记 unknown"
    return ("天气预报（来源发布 %s，适用 %s 至 %s）：%s"
            % (issued_raw, start_raw, end_raw, summary))


def kind_banner(spec):
    if spec["kind"] == "test":
        return "测试样例，非实际行程"
    return "实际规划草稿（非确认行程，不构成预订）"


def _route_lines(batch, spec, gname):
    """Concise driving-route observation lines for one property group,
    from the batch's top-level route_observations (travel method
    section 8). Routes are observations keyed by property group, kept
    apart from the quotes: they never touch prices, subtotals, or
    quote read times. Returns [] when the batch carries no observation
    for the group."""
    r = (batch.get("route_observations") or {}).get(gname)
    if not r:
        return []
    if r.get("status") == "observed":
        out = ["到%s：约 %s km / 约 %s（Google Maps 驾车，观察 %s；%s；终点 %s）"
               % (spec["resort_name"], r.get("km"), r.get("duration_text"),
                  r.get("observed_at"), r.get("time_setting"),
                  r.get("destination_label"))]
        if r.get("notices"):
            out.append("路线提示：%s" % r["notices"])
        return out
    return ["到%s：unknown（%s）"
            % (spec["resort_name"], r.get("note", "路线未取得"))]


def _lodging_comparable(spec, c):
    """Lodging-only comparable amount: the candidate's own price basis
    totalled for the whole party, plus verified mandatory on-site fees
    (lodging_mandatory_fees_total, a party/stay total). Independent of
    ticket status, so lodging quotes stay comparable while tickets are
    held. None when the base price itself is unknown. An ABSENT fees
    field contributes 0 (existence of fees stays a notes matter); a
    present but invalid fee (incl. explicit None) is never swallowed
    into 0 -- the comparable is held as None. The computed total must
    itself pass the money gate, else None."""
    if "lodging_mandatory_fees_total" in c:
        fees = c["lodging_mandatory_fees_total"]
        if not _money(fees):
            return None
    else:
        fees = 0
    if c.get("pricing_basis") == "room":
        room = c.get("room_price_total")
        if not _money(room):
            return None
        total = room + fees
    else:
        base = c.get("base_per_person")
        if not _money(base):
            return None
        total = base * spec["adults"] + fees
    return total if _money(total) else None


def ordered_groups(spec, candidates):
    """Group by property_group (method section 6). Groups with a
    complete, known-subtotal quote come first, ordered by their best
    group subtotal; groups without one follow, ordered by their best
    lodging-comparable amount (price basis + verified mandatory fees,
    unconditional caliber). Within a group, complete known quotes sort
    by subtotal, the rest by lodging-comparable amount. Unknown amounts
    never sort as cheapest."""
    groups, order = {}, []
    for c in candidates:
        g = c.get("property_group") or c["name"]
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append(c)

    def best(g):
        vals = [c["group_known_subtotal"] for c in groups[g]
                if candidate_status(spec, c) is None
                and c.get("group_known_subtotal") is not None]
        return min(vals) if vals else None

    def _group_key(g):
        b = best(g)
        if b is not None:
            return (0, b)
        vals = [_lodging_comparable(spec, c) for c in groups[g]]
        vals = [v for v in vals if v is not None]
        return (1, min(vals) if vals else float("inf"))

    order.sort(key=_group_key)
    result = []
    for g in order:
        cs = groups[g]
        good = sorted([c for c in cs if candidate_status(spec, c) is None
                       and c.get("group_known_subtotal") is not None],
                      key=lambda c: c["group_known_subtotal"])
        good_ids = {id(c) for c in good}
        rest = [c for c in cs if id(c) not in good_ids]
        rest.sort(key=lambda c: (_lodging_comparable(spec, c) is None,
                                 _lodging_comparable(spec, c) or 0))
        result.append((g, good + rest))
    return result


def cheapest_complete(spec, candidates):
    vals = [(c["group_known_subtotal"], c) for c in candidates
            if candidate_status(spec, c) is None
            and c.get("group_known_subtotal") is not None]
    return min(vals, key=lambda t: t[0])[1] if vals else None


def _ticket_price_line(c):
    """Price-basis line for a candidate. An included ticket is part of
    the chosen plan itself, never an 'addon unknown'."""
    days = c.get("ticket_days_covered", "unknown")
    if c.get("pricing_basis") == "room":
        head = "间价 %s" % money(c.get("room_price_total"))
        addon = " ＋ 票加购 %s/人（票覆盖 %s 天）" % (
            money(c.get("ticket_addon_per_person")), days)
    else:
        head = "基础价 %s" % money(c.get("base_per_person"))
        addon = " ＋ 票加购 %s（票覆盖 %s 天）" % (
            money(c.get("ticket_addon_per_person")), days)
    if c.get("ticket_included_in_base") is True:
        return "%s（所选方案已含 %s 日票）" % (head, days)
    return head + addon


def _render_md(batch):
    spec = validate(batch)
    lod, cond = batch["lodging"], batch["conditions"]
    lines = []
    lines.append("# 组合结果 — %s %s【%s】"
                 % (spec["resort_name"], spec["first_ski_date"], kind_banner(spec)))
    if batch.get("historical_display"):
        lines.append("（历史展示：票价与小计为原批次当轮来源，本轮未核，不作为当前报价）")
    lines.append("")
    lines.append("## 摘要")
    lines.append("- 规格：%s 出发、%d 泊 %d 个滑雪日、成人 %d 名、%d 房、每日需票：%s"
                 % (spec["first_ski_date"], spec["nights"], spec["ski_days"],
                    spec["adults"], spec["rooms"],
                    "是" if spec["tickets_each_day"] else "否"))
    lines.append("- 住宿覆盖：%s" % lod["coverage"])
    lines.append("- 住宿来源：%s（读取 %s）" % (lod["source_batch"], lod.get("read_at", "unknown")))
    lines.append("- 条件来源：%s（读取 %s）" % (cond["source_card"], cond.get("read_at", "unknown")))
    cheap = cheapest_complete(spec, lod["candidates"])
    if cheap is not None:
        lines.append("- 最低已知小计（完整候选）：%s，整组 %s（仅住宿＋所需票，未含另列费用）"
                     % (cheap["name"], money(cheap["group_known_subtotal"])))
    for c in lod["candidates"]:
        if c.get("ticket_selected_offer"):
            lines.append("- 选票结论：%s 选用 %s（%s/人）"
                         % (c["name"], c["ticket_selected_offer"],
                            money(c.get("ticket_addon_per_person"))))
    dirs = batch.get("choice_directions") or []
    if dirs:
        lines.append("")
        lines.append("## 选择方向（本轮观测）")
        for dtext in dirs:
            lines.append("- %s" % dtext)
    lines.append("")
    lines.append("## 住宿候选（按物件分组，完整且小计已知者按整组小计升序）")
    lines.append("- 主价与排序口径（用户口径）：主价＝不抵扣任何积分的房价＋已核必付费用；积分回馈/即时抵扣/既有积分支付仅作备注，不参与主价、总价与排序。完整小计优先；无完整小计的组按住宿可比较额升序。")
    for gname, quotes in ordered_groups(spec, lod["candidates"]):
        lines.append("### 物件：%s" % gname)
        _alert = (batch.get("route_observations") or {}).get(gname, {}).get("alert")
        if _alert:
            lines.append("- ⚠ %s" % _alert)
        for rl in _route_lines(batch, spec, gname):
            lines.append("- %s" % rl)
        _src = (batch.get("route_observations") or {}).get(gname, {}).get("source_url")
        if _src:
            lines.append("- 路线来源：[查看驾车路线](%s)" % _src)
        for c in quotes:
            inc = candidate_status(spec, c)
            lines.append("#### %s（%s）%s" % (c["name"], c.get("platform", ""), "【不完整】" if inc else ""))
            lines.append("- 每人/整组已知小计（住宿＋所需票）：%s / %s"
                         % (money(c.get("per_person_known_subtotal")), money(c.get("group_known_subtotal"))))
            lines.append("- %s" % _ticket_price_line(c))
            comp = _lodging_comparable(spec, c)
            if comp is not None and c.get("group_known_subtotal") is None:
                lines.append("- 住宿可比较额（房价＋已核强制费）：%s" % money(comp))
            if c.get("instant_payable_total") is not None:
                fees = c.get("lodging_mandatory_fees_total")
                fees = fees if _money(fees) else 0
                lines.append("- 积分备注（不入主价/总价/排序）：ポイント即時割引——本次预约预计积分 %s 即时抵扣后房价 %s（＋已核强制费后 %s）；%s"
                             % (money(c.get("instant_discount_amount")),
                                money(c["instant_payable_total"]),
                                money(c["instant_payable_total"] + fees),
                                c.get("instant_conditions", "付款条件/资格待核")))
            lines.append("- 餐食：%s" % c.get("meals", "unknown"))
            lines.append("- 装备：%s" % c.get("equipment", "unknown"))
            lines.append("- 距离/停车：%s" % c.get("access_parking", "unknown"))
            lines.append("- 限制/取消：%s" % c.get("restrictions_cancel", "unknown"))
            if c.get("extra_fees_note") is not None:
                lines.append("- 另列费用（不入小计）：%s" % c["extra_fees_note"])
            if inc:
                lines.append("- 不完整原因：%s" % inc)
            lines.append("- 报价读取：%s" % c.get("quote_read_at", "unknown"))
            lines.append("- 产品链接：%s" % c.get("url", "unknown"))
    if lod.get("search_url"):
        lines.append("- 原搜索入口：%s" % lod["search_url"])
    sl = screening_lines(batch)
    if sl:
        lines.append("")
        lines.extend(sl)
    lines.append("")
    lines.append("## 条件卡（%s，%s）" % (spec["resort_name"], spec["first_ski_date"]))
    lines.append("- 计划层：%s" % cond.get("plan", "unknown"))
    lines.append("- 实际开放：%s" % cond.get("actual_open", "unknown"))
    lines.append("- %s" % forecast_line(cond, spec))
    lines.append("- 警报：%s" % cond.get("warnings", "unknown"))
    lines.append("- 积雪（官网山顶/山麓）：%s" % cond.get("snow_official", "unknown"))
    lines.append("- 积雪（AMeDAS 平地，与山上分列）：%s" % cond.get("snow_amedas", "unknown"))
    lines.append("- Livecam：%s" % cond.get("livecam", "unknown"))
    lines.append("")
    _df = _date_facts_lines(batch)
    if _df:
        lines.append("")
        lines.append("## 日期判定（代码计算）")
        for _l in _df:
            lines.append("- %s" % _l)
    lines.append("## 缺项与复核时点")
    for m in batch.get("missing", []):
        lines.append("- 缺项：%s" % m)
    for r in batch.get("recheck", []):
        lines.append("- 复核：%s" % r)
    lines.append("")
    lines.append("覆盖声明：%s" % lod["coverage"])
    return "\n".join(lines) + "\n"


def _esc(v):
    return html.escape(str(v))


def _render_html(batch):
    spec = validate(batch)
    lod, cond = batch["lodging"], batch["conditions"]
    banner = kind_banner(spec)
    parts = []
    parts.append("<!doctype html><meta charset='utf-8'>"
                 "<meta name='viewport' content='width=device-width,initial-scale=1'>")
    parts.append("<title>组合结果 %s %s【%s】</title>"
                 % (_esc(spec["resort_name"]), _esc(spec["first_ski_date"]), _esc(banner)))
    parts.append("<style>body{font-family:sans-serif;max-width:720px;margin:0 auto;padding:12px}"
                 "section{border:1px solid #bbb;border-radius:8px;padding:10px;margin:10px 0}"
                 ".banner{font-weight:bold;font-size:1.15em}"
                 ".url{word-break:break-all;font-size:12px;color:#555}"
                 "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;"
                 "padding:4px;font-size:13px;text-align:left}</style>")
    parts.append("<header><p class='banner'>【%s】</p><h1>组合结果 — %s %s</h1>"
                 "<p>规格：%s 出发、%d 泊 %d 个滑雪日、成人 %d 名、%d 房、每日需票：%s</p>"
                 "<p>住宿覆盖：%s</p>"
                 "<p>住宿来源：%s（读取 %s）<br>条件来源：%s（读取 %s）</p></header>"
                 % (_esc(banner), _esc(spec["resort_name"]), _esc(spec["first_ski_date"]),
                    _esc(spec["first_ski_date"]), spec["nights"], spec["ski_days"],
                    spec["adults"], spec["rooms"],
                    "是" if spec["tickets_each_day"] else "否",
                    _esc(lod["coverage"]),
                    _esc(lod["source_batch"]), _esc(lod.get("read_at", "unknown")),
                    _esc(cond["source_card"]), _esc(cond.get("read_at", "unknown"))))
    if batch.get("historical_display"):
        parts.append("<section><p>历史展示：票价与小计为原批次当轮来源，本轮未核，不作为当前报价。</p></section>")
    cheap = cheapest_complete(spec, lod["candidates"])
    if cheap is not None:
        parts.append("<section><p>最低已知小计（完整候选）：%s，整组 <strong>%s</strong>"
                     "（仅住宿＋所需票，未含另列费用）</p></section>"
                     % (_esc(cheap["name"]), money(cheap["group_known_subtotal"])))
    selected = [(c["name"], c.get("ticket_selected_offer"),
                 c.get("ticket_addon_per_person"))
                for c in lod["candidates"] if c.get("ticket_selected_offer")]
    if selected:
        parts.append("<section><p>选票结论：%s</p></section>" % "；".join(
            "%s 选用 %s（%s/人）" % (_esc(n), _esc(o), money(p))
            for n, o, p in selected))
    dirs = batch.get("choice_directions") or []
    if dirs:
        parts.append("<section><h2>选择方向（本轮观测）</h2>%s</section>"
                     % "".join("<p>%s</p>" % _esc(x) for x in dirs))
    parts.append("<p>主价与排序口径（用户口径）：主价＝不抵扣任何积分的房价＋已核必付费用；积分回馈/即时抵扣/既有积分支付仅作备注，不参与主价、总价与排序。完整小计优先；无完整小计的组按住宿可比较额升序。</p>")
    for gname, quotes in ordered_groups(spec, lod["candidates"]):
        parts.append("<h2>物件：%s</h2>" % _esc(gname))
        _alert = (batch.get("route_observations") or {}).get(gname, {}).get("alert")
        if _alert:
            parts.append("<p><strong>⚠ %s</strong></p>" % _esc(_alert))
        for rl in _route_lines(batch, spec, gname):
            parts.append("<p>%s</p>" % _esc(rl))
        _src = (batch.get("route_observations") or {}).get(gname, {}).get("source_url")
        if _src:
            parts.append("<p>路线来源：<a href='%s'>查看驾车路线</a></p>" % _esc(_src))
        for c in quotes:
            inc = candidate_status(spec, c)
            basis_line = _esc(_ticket_price_line(c))
            parts.append("<section><h3>%s（%s）%s</h3>"
                         "<p>每人/整组已知小计（住宿＋所需票）：<strong>%s / %s</strong></p>"
                         "<p>%s</p>"
                         "<p>餐食：%s</p><p>装备：%s</p><p>距离/停车：%s</p><p>限制/取消：%s</p>"
                         % (_esc(c["name"]), _esc(c.get("platform", "")),
                            "【不完整】" if inc else "",
                            money(c.get("per_person_known_subtotal")),
                            money(c.get("group_known_subtotal")),
                            basis_line,
                            _esc(c.get("meals", "unknown")), _esc(c.get("equipment", "unknown")),
                            _esc(c.get("access_parking", "unknown")),
                            _esc(c.get("restrictions_cancel", "unknown"))))
            comp = _lodging_comparable(spec, c)
            if comp is not None and c.get("group_known_subtotal") is None:
                parts.append("<p>住宿可比较额（房价＋已核强制费）：<strong>%s</strong></p>"
                             % money(comp))
            if c.get("instant_payable_total") is not None:
                fees = c.get("lodging_mandatory_fees_total")
                fees = fees if _money(fees) else 0
                parts.append("<p>积分备注（不入主价/总价/排序）：ポイント即時割引——本次预约预计积分 %s 即时抵扣后房价 %s（＋已核强制费后 %s）；%s</p>"
                             % (money(c.get("instant_discount_amount")),
                                money(c["instant_payable_total"]),
                                money(c["instant_payable_total"] + fees),
                                _esc(c.get("instant_conditions", "付款条件/资格待核"))))
            if c.get("extra_fees_note") is not None:
                parts.append("<p>另列费用（不入小计）：%s</p>" % _esc(c["extra_fees_note"]))
            if inc:
                parts.append("<p>不完整原因：%s</p>" % _esc(inc))
            parts.append("<p>报价读取：%s</p>" % _esc(c.get("quote_read_at", "unknown")))
            url = c.get("url")
            if url:
                parts.append("<p>产品链接：<a href='%s'>打开产品页</a><br>"
                             "<span class='url'>%s</span></p>" % (_esc(url), _esc(url)))
            parts.append("</section>")
    if lod.get("search_url"):
        u = lod["search_url"]
        parts.append("<section><p>原搜索入口：<a href='%s'>打开搜索</a><br>"
                     "<span class='url'>%s</span></p></section>" % (_esc(u), _esc(u)))
    sh = screening_html(batch)
    if sh:
        parts.append(sh)
    parts.append("<section><h2>条件卡（%s，%s）</h2>"
                 "<p>计划层：%s</p><p>实际开放：%s</p><p>%s</p><p>警报：%s</p>"
                 "<p>积雪（官网山顶/山麓）：%s</p><p>积雪（AMeDAS 平地，与山上分列）：%s</p>"
                 "<p>Livecam：%s</p></section>"
                 % (_esc(spec["resort_name"]), _esc(spec["first_ski_date"]),
                    _esc(cond.get("plan", "unknown")), _esc(cond.get("actual_open", "unknown")),
                    _esc(forecast_line(cond, spec)), _esc(cond.get("warnings", "unknown")),
                    _esc(cond.get("snow_official", "unknown")),
                    _esc(cond.get("snow_amedas", "unknown")),
                    _esc(cond.get("livecam", "unknown"))))
    _df = _date_facts_lines(batch)
    if _df:
        parts.append("<section><h2>日期判定（代码计算）</h2>")
        for _l in _df:
            parts.append("<p>%s</p>" % _esc(_l))
        parts.append("</section>")
    parts.append("<section><h2>缺项与复核时点</h2>")
    for m in batch.get("missing", []):
        parts.append("<p>缺项：%s</p>" % _esc(m))
    for r in batch.get("recheck", []):
        parts.append("<p>复核：%s</p>" % _esc(r))
    parts.append("<p>覆盖声明：%s</p></section>" % _esc(lod["coverage"]))
    rows = []
    for _g, quotes in ordered_groups(spec, lod["candidates"]):
        for c in quotes:
            inc = candidate_status(spec, c)
            url = c.get("url", "")
            rows.append("<tr><td>%s%s</td><td>%s / %s</td><td>%s</td><td>%s</td>"
                        "<td><a href='%s'>产品页</a></td></tr>"
                        % (_esc(c["name"]), "【不完整】" if inc else "",
                           money(c.get("per_person_known_subtotal")),
                           money(c.get("group_known_subtotal")),
                           _esc(c.get("meals", "unknown")),
                           _esc(c.get("restrictions_cancel", "unknown")), _esc(url)))
    parts.append("<details><summary>完整宽表（候选明细）</summary><table>"
                 "<tr><th>方案</th><th>每人/整组已知小计</th><th>餐食</th>"
                 "<th>限制/取消</th><th>链接</th></tr>%s</table></details>"
                 % "".join(rows))
    return "".join(parts)


def render_md(batch):
    """Public render: always prepares first - an input-carried
    screening marker or prior records are never trusted. main()
    shares one prepared batch through the internal renders instead
    of preparing twice."""
    return _render_md(prepare(batch))


def render_html(batch):
    return _render_html(prepare(batch))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("batch")
    ap.add_argument("--md")
    ap.add_argument("--html")
    ap.add_argument("--json")
    a = ap.parse_args()
    with open(a.batch, encoding="utf-8") as f:
        batch = json.load(f)
    try:
        prepared = prepare(batch)
        md = _render_md(prepared)
    except Refusal as e:
        print("REFUSED: %s" % e)
        return 2
    if a.md:
        with open(a.md, "w", encoding="utf-8") as f:
            f.write(md)
    if a.html:
        with open(a.html, "w", encoding="utf-8") as f:
            f.write(_render_html(prepared))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(prepared, f, ensure_ascii=False, indent=1)
    if not a.md and not a.html:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
