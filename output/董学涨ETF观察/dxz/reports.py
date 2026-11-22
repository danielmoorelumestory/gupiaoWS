"""基金定期报告（年报/中报）自动发现、下载与具名持有人确定性提取。

发现（官方交易所公告列表，免登录）：
- 上交所 ETF：query.sse.com.cn/commonQuery.do sqlId=COMMON_SSE_PL_JJXX_ETFGG_L（上交所“基金公告/ETF
  公告”页 search_fundInformation_2021.js 使用的同一接口），PDF 在 www.sse.com.cn + URL。
- 深交所 ETF：www.szse.cn/api/disc/announcement/annList channelCode=fundinfoNotice_disc，
  PDF 在 disc.static.szse.cn/download + attachPath。
只取标题以“YYYY年年度报告 / YYYY年中期报告”结尾的正文（排除摘要、提示性公告、英文版）。

提取（pypdf 文本层 + 确定性规则，不用 LLM）：
- “期末上市基金前十名持有人”表：逐行 `序号 名称 份额 比例%`，名称可跨行；校验序号、份额>0、
  比例≤100，并用 份额/比例 反推分母，各行分母须一致（±2%），否则整表标记 parse_failed。
- 表头比例口径原样保留（如“占上市总份额比例”）。
- “报告期内单一投资者持有基金份额比例达到或超过20%的情况”：多为匿名“机构”；数字被 PDF 断行，
  去空白后按千分位规则切分并用 期初+申购−赎回=期末 自校验，不通过则不采用。
  若期末份额与同报告具名前十名某行完全相等，只标注“份额精确相等”，仍不当作已证实身份。
- “期末基金份额持有人户数及持有人结构”：机构/个人份额与比例，用 机构份额/机构比例≈个人份额/个人比例
  在候选切分中选唯一一致解；只作“机构合计”线索，不等于汇金合计。
- 未找到前十名表 → status=no_top10_section（2026 年新准则后的报告实测如此），绝不当作持有 0。
"""
from __future__ import annotations

import hashlib
import os
import re
import time

from .common import SourceError, http, norm_date, now_iso, read_json, write_bytes_atomic, write_json_atomic

SSE_ANN_URL = "https://query.sse.com.cn/commonQuery.do"
SSE_ANN_SQLID = "COMMON_SSE_PL_JJXX_ETFGG_L"
SSE_BASE = "https://www.sse.com.cn"
SZSE_ANN_URL = "https://www.szse.cn/api/disc/announcement/annList"
SZSE_BASE = "https://disc.static.szse.cn/download"

TITLE_RE = re.compile(r"(\d{4})年(年度报告|中期报告|半年度报告)\s*$")
_EXCLUDE = ("摘要", "提示性", "英文", "English")


# ------------------------------------------------------------------ 发现

def classify_title(title: str):
    """→ (period_end, kind) 或 None。只接受正文报告。"""
    t = re.sub(r"<[^>]+>", "", str(title or "")).strip()
    if any(x in t for x in _EXCLUDE):
        return None
    m = TITLE_RE.search(t)
    if not m:
        return None
    y = m.group(1)
    if m.group(2) == "年度报告":
        return f"{y}-12-31", "年度报告"
    return f"{y}-06-30", "中期报告"


def discover_sse(sess, code, begin, end, log):
    out, page = [], 1
    while page <= 10:
        r = http(sess, "GET", SSE_ANN_URL, params={
            "isPagination": "true", "sqlId": SSE_ANN_SQLID, "pageHelp.pageSize": "100",
            "pageHelp.pageNo": str(page), "pageHelp.beginPage": str(page), "pageHelp.cacheSize": "1",
            "pageHelp.endPage": str(page), "SECURITY_CODE": code, "BEGIN_DATE": begin,
            "END_DATE": end, "DATE_DESC": "1"}, headers={"Referer": "https://www.sse.com.cn/"})
        j = r.json()
        res = j.get("result") or []
        for v in res:
            if str(v.get("SECURITY_CODE")) != code:
                continue
            out.append({"title": v.get("TITLE"), "announce_date": norm_date(v.get("SSEDATE")),
                        "url": SSE_BASE + str(v.get("URL"))})
        pc = int((j.get("pageHelp") or {}).get("pageCount") or 1)
        if page >= pc or not res:
            break
        page += 1
        time.sleep(0.3)
    return out


def discover_szse(sess, code, begin, end, log):
    out, page = [], 1
    while page <= 10:
        r = http(sess, "POST", SZSE_ANN_URL, json={
            "seDate": [begin, end], "stock": [code], "channelCode": ["fundinfoNotice_disc"],
            "pageSize": 50, "pageNum": page},
            headers={"Referer": "https://www.szse.cn/disclosure/fund/notice/index.html"})
        j = r.json()
        data = j.get("data") or []
        for v in data:
            if code not in (v.get("secCode") or [code]):
                continue
            out.append({"title": v.get("title"), "announce_date": norm_date(v.get("publishTime")),
                        "url": SZSE_BASE + str(v.get("attachPath"))})
        total = int(j.get("announceCount") or 0)
        if page * 50 >= total or not data:
            break
        page += 1
        time.sleep(0.3)
    return out


def pick_reports(anns):
    """同一 period_end 取最新公告（更正/更新版覆盖旧版）。"""
    best = {}
    for a in anns:
        c = classify_title(a.get("title"))
        if not c or not a.get("announce_date"):
            continue
        pe, kind = c
        item = {**a, "period_end": pe, "kind": kind}
        if pe not in best or a["announce_date"] > best[pe]["announce_date"]:
            best[pe] = item
    return [best[k] for k in sorted(best)]


# ------------------------------------------------------------------ 文本清理

_HDR = re.compile(r"(年度报告|中期报告|半年度报告)\s*$")
_PAGE = re.compile(r"^\s*第\s*\d+\s*页\s*共\s*\d+\s*页\s*$")
_TOC = re.compile(r"\.{6,}|…{3,}")


def clean_pages(texts):
    """[(page_no, line)]，去掉页眉（基金名+报告名）与页脚页码。"""
    out = []
    for i, t in enumerate(texts):
        lines = (t or "").splitlines()
        nonempty = [k for k, ln in enumerate(lines) if ln.strip()]
        edge = set(nonempty[:3] + nonempty[-3:])
        for j, ln in enumerate(lines):
            s = ln.strip()
            if not s:
                continue
            if _PAGE.match(s):
                continue
            # 页眉/页脚处单独的页码（如“42”）；表格序号最多 11，故只删 ≥12 的纯数字边缘行
            if j in edge and s.isdigit() and 12 <= int(s) <= len(texts) + 5:
                continue
            if j <= 1 and _HDR.search(s) and len(s) < 80:
                continue
            out.append((i + 1, s))
    return out


def _find(lines, pat, start=0):
    for k in range(start, len(lines)):
        if re.search(pat, lines[k][1]) and not _TOC.search(lines[k][1]):
            return k
    return None


def norm_name(s: str) -> str:
    s = re.sub(r"\s+", "", s or "")
    return s.replace("-", "－").replace("—", "－").replace("–", "－")


# ------------------------------------------------------------------ 前十名持有人

# 章节编号可能缺失（如 159845 2026 中报文本层无“9.2”），故编号可选但必须行首
TOP10_HEAD = r"^(\d+(\.\d+)+\s*)?期末上市基金前十名持有人"
_SECTION_END = (r"^注[:：]", r"^\d+(\.\d+)+\s*期末基金管理人", r"^§", r"^\d+(\.\d+)+\s*期末")
# 比例列有的带“%”，有的表头写“（%）”而数值不带；比例后必须紧跟行尾，防止把名称里的数字当比例
_ROW = re.compile(r"(?:^|\n)(\d{1,2})[ \n]+(.*?)\s*(\d{1,3}(?:,\d{3})*\.\d{2})\s+(\d{1,3}(?:\.\d+)?)\s*%?[ \t]*(?=\n|$)", re.S)


def parse_top10(lines):
    k = _find(lines, TOP10_HEAD)
    if k is None:
        return None
    block = []
    for j in range(k + 1, min(k + 80, len(lines))):
        s = lines[j][1]
        if any(re.search(p, s) for p in _SECTION_END) and j > k + 1:
            break
        block.append(lines[j])
    head_idx = next((i for i, (_, s) in enumerate(block) if "持有人名称" in s), None)
    basis = None
    if head_idx is not None:
        head = block[head_idx][1]
        skip = 1
        # 表头可能折行：“占上市总份额” + 下一行“比例”/“比 例”
        if head_idx + 1 < len(block) and not re.match(r"^\d", block[head_idx + 1][1]) \
                and len(block[head_idx + 1][1]) <= 8:
            head += block[head_idx + 1][1]
            skip = 2
        m = re.search(r"占[^\s]*?(?:比\s*例|份额)(?:[（(]%[)）])?(?=\s|$)", head)
        basis = re.sub(r"\s+", "", m.group(0)) if m else head
        body = block[head_idx + skip:]
    else:
        body = block
    text, offs = "", []
    for p, s in body:
        offs.append((len(text), p))
        text += s + "\n"
    note = None
    nk = next((j for j in range(k + 1, min(k + 80, len(lines))) if re.match(r"^注[:：]", lines[j][1])), None)
    if nk is not None:
        note = lines[nk][1]
    rows, errs = [], []
    src = "\n" + text
    last_end = 0
    for m in _ROW.finditer(src):
        gap = src[last_end:m.start()].strip()
        if gap and rows:
            # 单元格垂直居中时，名称后半截出现在数字之后、下一序号之前：并回上一行
            rows[-1]["name"] = norm_name(rows[-1]["name"] + gap)
            rows[-1]["raw"] += " " + re.sub(r"\s+", " ", gap)
        last_end = m.end()
        seq, name, sh, pct = int(m.group(1)), norm_name(m.group(2)), float(m.group(3).replace(",", "")), float(m.group(4))
        pos = m.start(3) - 1
        page = next((p for o, p in reversed(offs) if o <= pos), offs[0][1] if offs else lines[k][0])
        rows.append({"rank": seq, "name": name, "shares": sh, "pct": pct, "page": page,
                     "raw": re.sub(r"\s+", " ", m.group(0)).strip()})
    tail = src[last_end:].strip()
    if tail and rows:
        if re.search(r"\d{1,3}(?:,\d{3})*\.\d{2}", tail):
            errs.append(f"表尾有未能解析的数字行，可能漏行：{tail[:40]}")
        else:
            rows[-1]["name"] = norm_name(rows[-1]["name"] + tail)
    # 校验
    if not rows:
        errs.append("前十名表存在但未解析出行")
    top = [r for r in rows if r["rank"] <= 10]
    if rows and len(top) < MIN_TOP10_ROWS:
        errs.append(f"前十名表只解析到 {len(top)} 行（<{MIN_TOP10_ROWS}），疑似截断，拒绝采用")
    if any(a["shares"] < b["shares"] for a, b in zip(top, top[1:])):
        errs.append("前十名份额未按降序排列，可能错行")
    for i, r in enumerate(rows):
        if r["rank"] != i + 1:
            errs.append(f"序号不连续：第{i + 1}行为 {r['rank']}")
            break
        if r["shares"] <= 0 or r["pct"] > 100 or not r["name"]:
            errs.append(f"行 {r['rank']} 数值/名称无效")
    dens = [r["shares"] / (r["pct"] / 100) for r in rows if r["pct"] >= 1]
    implied = None
    if dens:
        implied = sorted(dens)[len(dens) // 2]
        if any(abs(d / implied - 1) > 0.02 for d in dens):
            errs.append("各行 份额/比例 反推分母不一致，可能错行")
    return {"head_page": lines[k][0], "heading": lines[k][1], "ratio_basis": basis, "note": note,
            "rows": rows, "implied_denominator": implied, "errors": errs}


# ------------------------------------------------------------------ ≥20% 单一投资者

BIG20_HEAD = r"单一投资者持有基金份额比例达到或超过\s*20%\s*的情况"
_NUM = re.compile(r"\d{1,3}(?:,\d{3})*\.\d{2}|-")


def split_numbers(s: str, n: int):
    """去空白数字串 → 恰好 n 个千分位两位小数数字（'-' 记 0）；失败 None。"""
    s = re.sub(r"\s+", "", s)
    out, i = [], 0
    while i < len(s) and len(out) < n:
        m = _NUM.match(s, i)
        if not m:
            return None
        tok = m.group(0)
        out.append(0.0 if tok == "-" else float(tok.replace(",", "")))
        i = m.end()
    return out if len(out) == n and i == len(s) else None


_BIGROW = re.compile(r"(\d{1,2})\s+(\d{4}\s*年.*?日\s*[~～至-]+\s*\d{4}\s*年.*?日)\s+(.*?)\s+(\d{1,3}\.\d{2})\s*%", re.S)


def parse_big20(lines):
    k = _find(lines, BIG20_HEAD)
    if k is None:
        return None
    seg, pages = [], []
    for j in range(k + 1, min(k + 60, len(lines))):
        s = lines[j][1]
        if s.startswith("产品特有风险") or s.startswith("§"):
            break
        seg.append(s)
        pages.append(lines[j][0])
    text = "\n".join(seg)
    body_start = text.find("份额占")
    body = text[body_start:] if body_start >= 0 else text
    body = re.sub(r"^份额占\s*比?\s*", "", body)
    rows, errs = [], []
    last = 0
    for m in _BIGROW.finditer(body):
        label = norm_name(body[last:m.start()]) or (rows[-1]["label"] if rows else None)
        last = m.end()
        nums = split_numbers(m.group(3), 4)
        rec = {"seq": int(m.group(1)), "label": label, "period": re.sub(r"\s+", "", m.group(2)),
               "end_pct": float(m.group(4)), "page": pages[0] if pages else lines[k][0],
               "raw": re.sub(r"\s+", " ", m.group(0)).strip()}
        if nums is None:
            rec["valid"] = False
            errs.append(f"≥20% 第{rec['seq']}行数字无法唯一切分")
        else:
            b, sub, red, e = nums
            rec.update({"begin": b, "sub": sub, "red": red, "end": e,
                        "valid": abs(b + sub - red - e) <= 1})
            if not rec["valid"]:
                errs.append(f"≥20% 第{rec['seq']}行 期初+申购−赎回≠期末，未采用")
        rows.append(rec)
    none_text = "未出现" in text or "不存在" in text
    return {"head_page": lines[k][0], "rows": rows, "errors": errs, "stated_none": none_text and not rows}


# ------------------------------------------------------------------ 持有人结构

STRUCT_HEAD = r"^(\d+(\.\d+)+\s*)?期末基金份额持有人户数及持有人结构"
_GROUPED = re.compile(r"\d{1,3}(?:,\d{3})*\.\d{2}$")


def _suffix_candidates(s: str):
    """数字串的所有合法千分位后缀解析，如 '…644.3366,228,603,753.00'。"""
    out = []
    for i in range(len(s)):
        t = s[i:]
        if _GROUPED.fullmatch(t) and not (t[0] == "0" and len(t.split(",")[0]) > 1):
            out.append(float(t.replace(",", "")))
    return out


def parse_structure(lines):
    k = _find(lines, STRUCT_HEAD)
    if k is None:
        return None
    seg, note = [], ""
    for j in range(k + 1, min(k + 60, len(lines))):
        s = lines[j][1]
        if s.startswith("注"):
            for jj in range(j, min(j + 4, len(lines))):
                if jj > j and re.match(r"^\d+(\.\d+)+\s|^§", lines[jj][1]):
                    break
                note += lines[jj][1]
            break
        if re.search(TOP10_HEAD, s) or re.search(r"\d+(\.\d+)+\s*期末基金管理人", s):
            break
        seg.append(s)
    flat = re.sub(r"\s+", "", "".join(seg))
    note = re.sub(r"\s+", "", note)
    # 比例紧跟在“xx.dd”份额之后，用定宽后顾避免把份额末尾的 0 吞进比例
    pcts = list(re.finditer(r"(?<=\.\d{2})(\d{1,3}\.\d{2})%", flat))
    if len(pcts) < 2:
        return {"page": lines[k][0], "valid": False, "reason": "未找到机构/个人比例"}
    p1, p2 = float(pcts[0].group(1)), float(pcts[1].group(1))
    pre = re.search(r"[\d,.]+$", flat[:pcts[0].start()])
    mid = flat[pcts[0].end():pcts[1].start()]
    if not pre or not _GROUPED.fullmatch(mid):
        return {"page": lines[k][0], "valid": False, "reason": "数字切分失败"}
    indiv = float(mid.replace(",", ""))
    res = {"page": lines[k][0], "inst_pct": p1, "indiv_pct": p2, "indiv_shares": indiv, "valid": False}
    # 两种版式：①机构+个人=100%（联接基金若有，作为“其中”列，可能已含在机构内）；
    # ②机构+个人+联接=100%（联接基金单列，不含在机构内）。其它情况不采用。
    feeder_sep = 0.0
    if abs(p1 + p2 - 100) <= 0.05:
        res["layout"] = "inst_indiv_100"
    elif len(pcts) >= 3 and abs(p1 + p2 + float(pcts[2].group(1)) - 100) <= 0.05 \
            and _GROUPED.fullmatch(flat[pcts[1].end():pcts[2].start()]):
        res["layout"] = "feeder_separate"
        feeder_sep = float(flat[pcts[1].end():pcts[2].start()].replace(",", ""))
    else:
        res["reason"] = "机构+个人(+联接)比例≠100%"
        return res
    if p2 > 0:
        total = indiv / (p2 / 100)
        cands = [c for c in _suffix_candidates(pre.group(0)) if abs(c / total - p1 / 100) <= 0.002 + 0.006 * p1 / 100]
        exact = [c for c in cands if abs((c + indiv + feeder_sep) * p1 / 100 - c) <= max(1.0, c * 0.0001)]
        pick = sorted(set(exact or cands))  # 前导 0 的切分（如 080,000.00）与 80,000.00 同值，按值去重
        if len(pick) == 1:
            res.update({"inst_shares": pick[0], "total_shares": pick[0] + indiv + feeder_sep, "valid": True})
        else:
            res["reason"] = f"机构份额候选 {len(pick)} 个，无法唯一确定"
    else:
        cands = _suffix_candidates(pre.group(0))
        res["reason"] = "个人比例为 0，无法交叉校验机构份额"
    res["note"] = note or None
    header = flat[:pcts[0].start()] if pcts else flat
    res["feeder_column"] = "联接" in header
    if res.get("layout") == "feeder_separate" and res.get("valid"):
        res["feeder_shares"] = feeder_sep
        res["feeder_pct"] = float(pcts[2].group(1))
    elif len(pcts) >= 3 and res.get("valid") and res["feeder_column"]:
        mid2 = flat[pcts[1].end():pcts[2].start()]
        if _GROUPED.fullmatch(mid2):
            res["feeder_shares"] = float(mid2.replace(",", ""))
            res["feeder_pct"] = float(pcts[2].group(1))
    # 机构合计上限线索（H1）：只有原文注明“机构…已包含该基金的联接基金”、且联接份额≤机构份额时才扣除；
    # 否则保守地用完整机构合计。无联接列 ≠ 无联接基金。
    if res.get("valid"):
        res["feeder_in_inst_stated"] = bool(re.search(r"机构投资者.{0,40}已包含.{0,80}联接基金", note or ""))
        fs = res.get("feeder_shares")
        if res.get("layout") == "feeder_separate":
            res["inst_upper"] = res["inst_shares"]
            res["inst_upper_basis"] = "完整机构合计（表中联接基金单列且三项合计 100%，联接不在机构内，无需扣除）"
        elif fs is not None and res["feeder_in_inst_stated"] and 0 <= fs <= res["inst_shares"]:
            res["inst_upper"] = res["inst_shares"] - fs
            res["inst_upper_basis"] = "机构合计扣除联接基金（原文注明机构数据已含联接基金，且联接份额≤机构份额）"
        else:
            res["inst_upper"] = res["inst_shares"]
            why = ("原文未注明机构数据含联接基金" if fs is not None else
                   "表中无联接基金列（不代表没有联接基金）")
            res["inst_upper_basis"] = f"完整机构合计（未扣联接：{why}）"
    return res


# ------------------------------------------------------------------ 持有人识别

def classify_holder(name: str):
    """→ (category, label, scope)。scope: narrow=狭义汇金体系；broad=广义国家队（不与狭义混算）；
    info=国有资本平台等仅提示；None=其他。"""
    n = norm_name(name)
    if n == "中央汇金投资有限责任公司":
        return "huijin_inv", "汇金投资", "narrow"
    if n == "中央汇金资产管理有限责任公司":
        return "huijin_am", "汇金资管", "narrow"
    if "中央汇金" in n or "汇金资管" in n:
        return "huijin_product", "汇金资管委托产品", "narrow_product"
    if "中国证券金融股份有限公司" in n:
        return "csf", "证金公司", "broad"
    if "全国社保基金" in n or "全国社会保障基金" in n:
        return "ssf", "社保基金", "broad"
    if "基本养老保险基金" in n:
        return "pension", "基本养老保险基金", "broad"
    if "梧桐树投资平台" in n:
        return "wutong", "梧桐树投资平台", "broad"
    if any(k in n for k in ("中国国新", "国新投资", "诚通金控", "中国诚通")):
        return "soe_capital", "国有资本运营平台", "info"
    return None, None, None


def holder_summary(top10):
    """具名前十名中识别出的主体汇总。

    数据契约（H1）：
    - narrow_identified：是否在前十名里识别到汇金投资/汇金资管（自有）。为 False 时 narrow_own_lb=None，
      含义是“前十名未识别到（未知，≠0）”，绝不写 0。
    - narrow_own_lb：前十名中已识别汇金自有份额之和，只是“已披露下限”，不是汇金体系完整持仓
      （未进前十的主体、场外份额都不在内）。
    - products：汇金资管委托产品逐行列表（各自原文全称与页码）；narrow_with_products_lb 同理为下限。
    - broad_lb：广义口径（社保/养老金/证金/梧桐树）已识别下限，不与汇金合计。
    """
    if not top10 or top10.get("errors"):
        return None
    own, prods, broad, ents = [], [], [], []
    for r in top10["rows"]:
        cat, label, scope = classify_holder(r["name"])
        r["category"], r["label"], r["scope"] = cat, label, scope
        if not scope:
            continue
        e = {"name": r["name"], "label": label, "scope": scope, "rank": r["rank"],
             "shares": r["shares"], "pct": r["pct"], "page": r["page"]}
        ents.append(e)
        {"narrow": own, "narrow_product": prods, "broad": broad}.get(scope, []).append(e)
    lb = lambda xs: round(sum(x["shares"] for x in xs), 2) if xs else None  # noqa: E731
    return {
        "narrow_identified": bool(own),
        "narrow_labels": sorted({e["label"] for e in own}),
        "narrow_own_lb": lb(own),
        "products": prods,
        "products_lb": lb(prods),
        "narrow_with_products_lb": lb(own + prods),
        "broad_lb": lb(broad),
        "entities": ents,
        "scope_note": "仅为前十名中已识别主体份额之和（已披露下限），未进前十/场外/匿名均未知",
    }


# ------------------------------------------------------------------ 下载与提取

def pdf_texts(path):
    import pypdf
    r = pypdf.PdfReader(path)
    return [p.extract_text() or "" for p in r.pages]


MIN_TOP10_ROWS = 10
_KIND_TXT = {"年度报告": "年度报告", "中期报告": "中期报告"}


def readability(texts):
    cjk = sum(len(re.findall(r"[\u4e00-\u9fa5]", t)) for t in texts)
    return {"pages": len(texts), "cjk_chars": cjk,
            "readable": len(texts) >= 5 and cjk >= 300 * min(len(texts), 20)}


def extract(path, expect: dict | None = None):
    """expect: {"period_end","kind"}，用于核验报告身份（首页须出现“YYYY年年度/中期报告”）。

    status：
    - named_top10：前十名表解析且通过行数/分母校验；
    - no_top10_section：正文可读、身份核验通过、持有人信息章节与持有人结构表均已找到，唯独没有前十名表；
    - parse_failed：前十名表存在但校验未通过（含截断）；
    - unreadable：文本层不足（扫描版/空文本），一切未知；
    - unverified：可读但身份或持有人章节核验不过，不能断言“未列示”。
    """
    texts = pdf_texts(path)
    rd = readability(texts)
    lines = clean_pages(texts)
    head_txt = "\n".join(texts[:3])
    ident_ok = True
    if expect:
        want = f"{expect['period_end'][:4]}年{expect['kind']}"
        ident_ok = want in re.sub(r"\s+", "", head_txt)
    holder_sec = _find(lines, r"^(§\s*)?(\d+\s*)?基金份额持有人信息\s*$") is not None  # 目录行带点线和页码，不匹配
    top10 = parse_top10(lines) if rd["readable"] else None
    big20 = parse_big20(lines) if rd["readable"] else None
    struct = parse_structure(lines) if rd["readable"] else None
    if not rd["readable"]:
        status, why = "unreadable", f"文本层不足（{rd['cjk_chars']} 个汉字 / {rd['pages']} 页），疑似扫描版"
    elif not ident_ok:
        status, why = "unverified", "首页未出现预期报告期与类型，报告身份未核验"
    elif top10 is not None:
        status, why = ("parse_failed", "；".join(top10["errors"])) if top10["errors"] else ("named_top10", None)
    elif holder_sec and struct is not None:
        status, why = "no_top10_section", "正文可读、身份已核验、持有人信息章节与持有人结构表存在，但无前十名持有人表"
    else:
        status, why = "unverified", "未找到持有人信息章节或持有人结构表，不能断言未列示"
    summ = holder_summary(top10) if status == "named_top10" else None
    if big20 and top10 and status == "named_top10":
        by_sh = {r["shares"]: r["name"] for r in top10["rows"]}
        for b in big20["rows"]:
            if b.get("valid") and b.get("end") in by_sh:
                b["exact_share_match"] = by_sh[b["end"]]
    huijin_mentions = sum(t.count("中央汇金") for t in texts)
    mm = re.search(r"基金管理人\s*[：:]?\s*\n?\s*([\u4e00-\u9fa5（）()]{2,30}?(?:基金管理股份有限公司|基金管理有限公司|资产管理有限公司))",
                   "\n".join(texts[:12]))
    manager = re.sub(r"\s+", "", mm.group(1)) if mm else None
    return {"pages": len(texts), "readability": rd, "identity_ok": ident_ok, "holder_section": holder_sec,
            "manager": manager, "status": status, "status_reason": why, "top10": top10, "big20": big20,
            "structure": struct, "summary": summ, "huijin_mentions": huijin_mentions}


def download(sess, url, dest_dir, log):
    os.makedirs(dest_dir, exist_ok=True)
    fn = re.sub(r"[^A-Za-z0-9_.-]", "_", url.rsplit("/", 1)[-1])
    path = os.path.join(dest_dir, fn)
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return path
    r = http(sess, "GET", url, headers={"Referer": SSE_BASE + "/" if "sse.com.cn" in url
                                        else "https://www.szse.cn/"}, timeout=60)
    if not r.content.startswith(b"%PDF"):
        raise SourceError(f"下载内容不是 PDF：{url}")
    write_bytes_atomic(path, r.content)
    time.sleep(0.5)
    return path


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


EXTRACTOR_VERSION = 11


GOOD = ("named_top10", "no_top10_section")


def merge_reports(old: list, new: list, discovered_ok: bool, now: str):
    """按 period_end 合并（H2）。返回 (merged, issues)。

    - 新记录有效（GOOD）→ 采用新记录；
    - 新记录无效而旧记录有效 → 保留旧记录，标 reused_cache=True 并记下本次错误与旧抓取时间；
    - 本次发现列表里缺少的旧报告期 → 保留旧记录并标 missing_in_discovery；
    - 发现失败/为空 → 全部沿用旧缓存。
    """
    issues = []
    om = {r["period_end"]: r for r in old or [] if isinstance(r, dict) and r.get("period_end")}
    nm = {r["period_end"]: r for r in new or []}
    if not discovered_ok or not nm:
        for r in om.values():
            r.setdefault("cache_note", f"{now} 发现失败/为空，沿用 {r.get('fetched_at')} 的缓存")
        if om:
            issues.append(f"发现失败/为空，沿用 {len(om)} 条旧缓存")
        return [om[k] for k in sorted(om)], issues
    out = {}
    for pe in sorted(set(om) | set(nm)):
        o, n = om.get(pe), nm.get(pe)
        if n is None:
            o = {**o, "missing_in_discovery": now}
            issues.append(f"{pe} 不在本次发现列表，保留旧记录（{o.get('fetched_at')}）")
            out[pe] = o
        elif n.get("status") in GOOD or not (o and o.get("status") in GOOD):
            out[pe] = n
            if n.get("status") not in GOOD:
                issues.append(f"{pe} {n.get('status')}：{n.get('status_reason') or n.get('error')}")
        else:
            out[pe] = {**o, "reused_cache": True, "last_attempt": now,
                       "last_error": n.get("status_reason") or n.get("error") or n.get("status")}
            issues.append(f"{pe} 本次 {n.get('status')}，保留 {o.get('fetched_at')} 的有效记录")
    return [out[k] for k in sorted(out)], issues


def collect(sess, codes, begin, end, raw_dir, cache_dir, log, min_period="2024-06-30"):
    """全池：发现→下载→提取→与旧缓存按报告期合并。返回 (reports, issues{code:[...]})。"""
    out, all_issues = [], {}
    for code in codes:
        cpath = os.path.join(cache_dir, "reports", f"{code}.json")
        old = read_json(cpath) or []
        ok = True
        try:
            anns = (discover_sse if code[0] in "56" else discover_szse)(sess, code, begin, end, log)
        except (SourceError, ValueError) as e:
            log.append(f"公告发现 {code} 失败：{e}")
            anns, ok = [], False
        reps = [r for r in pick_reports(anns) if r["period_end"] >= min_period]
        got = []
        for rep in reps:
            rec = {"code": code, **rep, "fetched_at": now_iso()}
            try:
                path = download(sess, rep["url"], os.path.join(raw_dir, "reports", code), log)
                sh = sha256(path)
                ck = os.path.join(cache_dir, "extract", f"{sh}.json")
                ex = read_json(ck)
                if not ex or ex.get("_v") != EXTRACTOR_VERSION:
                    ex = extract(path, {"period_end": rep["period_end"], "kind": rep["kind"]})
                    ex["_v"] = EXTRACTOR_VERSION
                    write_json_atomic(ck, ex)
                rec.update({"sha256": sh, "local_pdf": os.path.relpath(path, os.path.dirname(raw_dir)),
                            **{k: v for k, v in ex.items() if k != "_v"}})
            except Exception as e:  # noqa: BLE001
                rec.update({"status": "download_or_extract_failed", "error": f"{type(e).__name__}: {e}"})
                log.append(f"报告 {code} {rep['period_end']} 失败：{e}")
            got.append(rec)
        merged, issues = merge_reports(old, got, ok, now_iso())
        if issues:
            all_issues[code] = issues
            log.extend(f"报告 {code}：{x}" for x in issues)
        if merged:
            write_json_atomic(cpath, merged)
        out.extend(merged)
    return out, all_issues
