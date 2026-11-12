#!/usr/bin/env python3
"""Render a batch's candidates as a Markdown table and a real HTML table.

If a `<batch>-supplement.json` sits next to the batch file, its per-candidate
fields (e.g. equipment) are merged in for display only; the batch JSON itself
is evidence and is never rewritten here.
"""
import argparse
import html
import json
import math
import os
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from totals import sort_for_report  # noqa: E402

HEADERS = ["#", "方案（来源）", "每人/整组已知小计（住宿＋所需票）", "基础价＋票加购",
           "住宿", "餐食", "装备", "停车/步行", "限制/取消", "链接", "备注"]
INC_HEADERS = ["方案（来源）", "住宿", "餐食", "装备", "链接", "不完整原因"]
CALIBER_NOTE = ("口径：小计仅含已核的住宿与所需雪票，不是完整出游消费；餐食含否看餐食列；"
                "维护费、停车费、另付餐费等未核金额另列于各行字段、不计入小计；"
                "可退押金是临时支付，不计入小计。散订每人价为整组均分后四舍五入，以整组为准。")


def _link_label(url):
    if "tramaru" in url or "ski-ichiba" in url:
        return "Skiichiba产品"
    if "orion" in url:
        return "Orion产品"
    if "agoda" in url:
        return "Agoda产品"
    return "产品"


def yen_int(x):
    """Display rounding for per-person yen: half-up (26698.5 -> 26699).

    Python's round() is banker's rounding and must not be used here. The
    stored/computed value keeps full precision; only the display is rounded,
    and the group total stays authoritative.
    """
    return int(math.floor(x + 0.5))


def _row(c):
    per = c["per_person_total"]
    grp = c["group_total"]
    price = "unknown" if per is None else "¥{:,} / ¥{:,}".format(yen_int(per), yen_int(grp))
    base_v = c.get("base_per_person")
    if base_v is None and c.get("base_group_total") is not None:
        base = "¥{:,}（整单）".format(c["base_group_total"])
    else:
        base = "unknown" if base_v is None else "¥{:,}".format(base_v)
    addon = c.get("ticket_addons_per_person")
    addon_s = "—" if not c["missing_ticket_days"] else (
        "unknown" if addon is None else "+¥{:,}".format(addon))
    flags = []
    if c.get("note"):
        flags.append(c["note"])
    if c.get("over_soft_reference"):
        flags.append("超软参考")
    if c.get("restrictions"):
        flags.append("限制:" + c["restrictions"])
    if not c["complete"]:
        flags.append("不完整:" + c.get("incomplete_reason", ""))
    urls = [c["url"]] + list(c.get("extra_urls") or [])
    return {
        "plan": c["plan_name"], "source": c["source"], "price": price,
        "base": base, "addon": addon_s,
        "stay": c.get("property") or ("宿おまかせ" if c.get("omakase") else "unknown"),
        "meals": c.get("meals", "unknown"),
        "equip": c.get("equipment") or "unknown",
        "parking": c.get("parking", "unknown"),
        "cancel": c.get("cancel", "unknown"), "url": c["url"], "urls": urls,
        "flags": "；".join(flags),
    }


def _cells(r, idx=None):
    return [str(idx) if idx is not None else "", "{}（{}）".format(r["plan"], r["source"]),
            r["price"], "{} / {}".format(r["base"], r["addon"]), r["stay"],
            r["meals"], r["equip"], r["parking"], r["cancel"], r["urls"], r["flags"]]


def _md_links(urls):
    return " ".join("[{}]({})".format(_link_label(u), u) for u in urls)


def _html_links(urls):
    parts = []
    for u in urls:
        parts.append("<a href='{}'>{}</a><div class='u'>{}</div>".format(
            html.escape(u, quote=True), html.escape(_link_label(u)), html.escape(u)))
    return "".join(parts)


def render_markdown(batch):
    complete, incomplete = sort_for_report(batch["candidates"])
    lines = ["# {} 查询表".format(batch["title"]), "",
             "规格：{}（查询时刻见各行；改条件旧价失效）".format(batch["spec_text"]), "",
             CALIBER_NOTE, ""]
    lines.append("| " + " | ".join(HEADERS) + " |")
    lines.append("|" + "---|" * len(HEADERS))
    for i, c in enumerate(complete, 1):
        r = _row(c)
        cells = _cells(r, i)
        cells[9] = _md_links(r["urls"])
        lines.append("| " + " | ".join(cells) + " |")
    if incomplete:
        lines += ["", "## 缺价/不完整区（不参与比价排序）", "",
                  "| " + " | ".join(INC_HEADERS) + " |",
                  "|" + "---|" * len(INC_HEADERS)]
        for c in incomplete:
            r = _row(c)
            lines.append("| {}（{}） | {} | {} | {} | {} | {} |".format(
                r["plan"], r["source"], r["stay"], r["meals"], r["equip"],
                _md_links(r["urls"]), c.get("incomplete_reason", "")))
    return "\n".join(lines) + "\n"


def _table_html(headers, rows, link_col):
    out = ["<div class='wrap'><table><thead><tr>"]
    out += ["<th>{}</th>".format(html.escape(h)) for h in headers]
    out.append("</tr></thead><tbody>")
    for cells in rows:
        out.append("<tr>")
        for j, cell in enumerate(cells):
            if j == link_col:
                out.append("<td>{}</td>".format(_html_links(cell)))
            else:
                out.append("<td>{}</td>".format(html.escape(cell)))
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def render_html(batch):
    complete, incomplete = sort_for_report(batch["candidates"])
    rows = [_cells(_row(c), i) for i, c in enumerate(complete, 1)]
    parts = ["<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'>",
             "<meta name='viewport' content='width=device-width, initial-scale=1'>",
             "<title>{}</title><style>".format(html.escape(batch["title"])),
             "body{font-family:-apple-system,'Hiragino Sans','Noto Sans JP',sans-serif;"
             "margin:16px;color:#222}h1{font-size:20px}h2{font-size:16px;margin-top:24px}",
             "p.spec{color:#555;font-size:13px}.wrap{overflow-x:auto}",
             "table{border-collapse:collapse;min-width:900px;width:100%;font-size:13px}",
             "th,td{border:1px solid #ccc;padding:6px 8px;text-align:left;vertical-align:top}",
             "th{background:#f2f5f9;white-space:nowrap}tr:nth-child(even){background:#fafafa}",
             "td .u{font-size:11px;color:#666;word-break:break-all}",
             "p.note{color:#555;font-size:13px}",
             "@media (max-width:640px){body{margin:8px}table{font-size:12px;min-width:760px}"
             "th,td{padding:5px 6px}h1{font-size:17px}}",
             "</style></head><body>",
             "<h1>{}</h1>".format(html.escape(batch["title"])),
             "<p class='spec'>规格：{}</p>".format(html.escape(batch["spec_text"])),
             "<p class='note'>{}</p>".format(html.escape(CALIBER_NOTE)),
             _table_html(HEADERS, rows, 9)]
    if incomplete:
        inc_rows = []
        for c in incomplete:
            r = _row(c)
            inc_rows.append(["{}（{}）".format(r["plan"], r["source"]), r["stay"],
                             r["meals"], r["equip"], r["urls"],
                             c.get("incomplete_reason", "")])
        parts.append("<h2>缺价/不完整区（不参与比价排序）</h2>")
        parts.append(_table_html(INC_HEADERS, inc_rows, 4))
    parts.append("</body></html>")
    return "".join(parts)


def load_batch(path):
    with open(path, encoding="utf-8") as fh:
        batch = json.load(fh)
    supp_path = path.replace(".json", "-supplement.json")
    if os.path.exists(supp_path):
        with open(supp_path, encoding="utf-8") as fh:
            supp = json.load(fh)
        by_id = {cand["id"]: cand for cand in batch["candidates"]}
        for cid, text in supp.get("equipment", {}).items():
            if cid in by_id:
                by_id[cid]["equipment"] = text
        for cid, text in supp.get("access", {}).items():
            if cid in by_id:
                by_id[cid]["parking"] = text  # display override, evidence untouched
        for cid, urls in supp.get("extra_urls", {}).items():
            if cid in by_id:
                by_id[cid]["extra_urls"] = urls
        for cid, text in supp.get("note", {}).items():
            if cid in by_id:
                by_id[cid]["note"] = text
    return batch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("batch")
    ap.add_argument("--html", dest="html_path")
    args = ap.parse_args()
    batch = load_batch(args.batch)
    print(render_markdown(batch))
    if args.html_path:
        with open(args.html_path, "w", encoding="utf-8") as fh:
            fh.write(render_html(batch))
    return 0


if __name__ == "__main__":
    sys.exit(main())
