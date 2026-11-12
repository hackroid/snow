# -*- coding: utf-8 -*-
"""Minimal date-rule helpers for batch assembly (stdlib only).

Two recurring judgements that must never be eyeballed:
1. Parking-style fee rules: explicit dates / date ranges first, then a
   weekday default, else the rule's verified free default. A rule is
   only usable when it is COMPLETE: all three charge lists present
   (an empty list means "verified none of this kind", a missing key
   means unverified -> pending), a valid fee, and an explicit
   default_free_verified flag. Anything incomplete -> pending, never
   a guessed 0.
2. Early-bird style deadlines: compare the purchase moment against the
   deadline, never the ski date, in the timezone the rule declares.
   Supported: 'none', 'fixed:YYYY-MM-DD' (day granularity only -- the
   boundary day's time-of-day semantics stay unverified). Datetime
   forms and 'before_first_use:HH:MM' are NOT evaluated here and
   return unknown rather than a guess. Bad or naive purchase moments
   return unknown, never crash.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

_LIST_KEYS = ("charged_dates", "charged_ranges", "charged_weekdays")


def parking_fee(rule, day):
    """rule: {fee, charged_weekdays (Mon=0..Sun=6), charged_dates,
    charged_ranges [(from, to)], default_free_verified,
    source, source_time}. Returns {fee, basis}; fee None = pending."""
    if not rule:
        return {"fee": None, "basis": "规则缺失，待核"}
    fee = rule.get("fee")
    if (not isinstance(fee, (int, float)) or isinstance(fee, bool)
            or fee < 0 or fee != fee or fee in (float("inf"), float("-inf"))):
        return {"fee": None, "basis": "规则 fee 缺失/非法（须有限非负数），待核"}
    for k in _LIST_KEYS:
        if k not in rule:
            return {"fee": None,
                    "basis": "规则不完整：%s 未提供（省略≠已核无此类），待核" % k}
    for k in _LIST_KEYS:
        v = rule[k]
        if not isinstance(v, list):
            return {"fee": None, "basis": "规则 %s 非清单（null/错类型），待核" % k}
    import re as _re
    _ISO = _re.compile(r"^\d{4}-\d{2}-\d{2}$")
    charged_date_objs = []
    for x in rule["charged_dates"]:
        if not isinstance(x, str) or not _ISO.match(x):
            return {"fee": None,
                    "basis": "规则 charged_dates 成员非严格 YYYY-MM-DD：%r，待核" % (x,)}
        try:
            charged_date_objs.append(date.fromisoformat(x))
        except ValueError:
            return {"fee": None, "basis": "规则 charged_dates 成员不可解析：%s，待核" % x}
    charged_range_objs = []
    for pair in rule["charged_ranges"]:
        if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                or not all(isinstance(x, str) and _ISO.match(x) for x in pair)):
            return {"fee": None, "basis": "规则 charged_ranges 成员非 [起, 止] 严格日期对，待核"}
        try:
            a, b = date.fromisoformat(pair[0]), date.fromisoformat(pair[1])
        except ValueError:
            return {"fee": None, "basis": "规则 charged_ranges 日期不可解析，待核"}
        if a > b:
            return {"fee": None, "basis": "规则 charged_ranges 起止倒置，待核"}
        charged_range_objs.append((a, b))
    for x in rule["charged_weekdays"]:
        if not isinstance(x, int) or isinstance(x, bool) or not 0 <= x <= 6:
            return {"fee": None, "basis": "规则 charged_weekdays 成员非 0-6 整数，待核"}
    src = rule.get("source", "")
    iso = day.isoformat()
    if day in charged_date_objs:
        return {"fee": fee, "basis": "%s 在明列收费日（%s）" % (iso, src)}
    for a, b in charged_range_objs:
        if a <= day <= b:
            return {"fee": fee,
                    "basis": "%s 在明列收费区间 %s–%s（%s）"
                            % (iso, a.isoformat(), b.isoformat(), src)}
    if day.weekday() in rule["charged_weekdays"]:
        return {"fee": fee, "basis": "%s 为收费星期（%s）" % (iso, src)}
    if rule.get("default_free_verified") is True:
        return {"fee": 0,
                "basis": "%s 未命中收费清单，按规则已核默认免费（%s）" % (iso, src)}
    return {"fee": None,
            "basis": "%s 未命中收费清单，但默认免费未核（default_free_verified 缺失），待核" % iso}


def deadline_status(entry, purchase_at):
    """entry: {deadline_rule, deadline_tz (optional IANA name)}.
    Returns {status, basis}: before_deadline / after_deadline /
    boundary_day_unverified / not_applicable / unknown."""
    if not isinstance(entry, dict):
        return {"status": "unknown", "basis": "截止条目非对象，待核"}
    rule = entry.get("deadline_rule")
    if rule is not None and not isinstance(rule, str):
        return {"status": "unknown", "basis": "截止规则非字符串，待核"}
    if rule == "none":
        return {"status": "not_applicable", "basis": "无截止规则"}
    if not rule or rule == "unknown":
        return {"status": "unknown", "basis": "截止规则未知"}
    if purchase_at is None:
        return {"status": "unknown", "basis": "购买时刻缺失"}
    try:
        p = datetime.fromisoformat(purchase_at)
    except (ValueError, TypeError):
        return {"status": "unknown", "basis": "购买时刻不可解析，待核"}
    if p.tzinfo is None:
        return {"status": "unknown", "basis": "购买时刻无时区，待核"}
    if rule.startswith("fixed:"):
        raw = rule[len("fixed:"):]
        try:
            d = date.fromisoformat(raw)
        except ValueError:
            return {"status": "unknown",
                    "basis": "截止形态未支持（仅支持 fixed:YYYY-MM-DD 按日粒度）：%s" % raw}
        tzname = entry.get("deadline_tz")
        if tzname:
            try:
                pd = p.astimezone(ZoneInfo(tzname)).date()
            except Exception:
                return {"status": "unknown", "basis": "规则时区不可用：%s" % tzname}
            tznote = "规则时区 %s" % tzname
        else:
            pd = p.date()
            tznote = "购买时刻自身时区（规则未声明时区）"
        if pd < d:
            return {"status": "before_deadline",
                    "basis": "购买日 %s 早于截止日 %s（按日粒度，%s）"
                             % (pd.isoformat(), raw, tznote)}
        if pd > d:
            return {"status": "after_deadline",
                    "basis": "购买日 %s 晚于截止日 %s（按日粒度，%s）"
                             % (pd.isoformat(), raw, tznote)}
        return {"status": "boundary_day_unverified",
                "basis": "购买日在截止日 %s 当日；截止时分语义未核，待核（%s）"
                         % (raw, tznote)}
    return {"status": "unknown", "basis": "截止规则形态未支持：%s" % rule}
