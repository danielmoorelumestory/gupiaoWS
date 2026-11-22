"""持有人识别、2026 无前十名、比例口径、数字切分自校验。合成文本模仿 pypdf 实际断行。"""
import glob
import os

import pytest

from dxz import reports as R

HDR = "易方达沪深 300 交易型开放式指数发起式证券投资基金 2025年中期报告 "


def pages(*texts):
    return R.clean_pages([HDR + "\n" + f"第 {i + 1} 页共 9 页 \n" + t for i, t in enumerate(texts)])


P1 = """8.2  期末上市基金前十名持有人
序号 持有人名称 持有份额（份） 占上市总份额比例
1 中央汇金资产管理有限责任公司 28,538,696,695.00 41.80%
2 中央汇金投资有限责任公司 27,355,388,757.00 40.07%
3 友邦人寿保险有限公司－分红 479,058,760.00 0.70%
4
易方达基金－中央汇金资产管理有限责
任公司－易方达基金－汇金资管单一资
产管理计划
254,000,077.00 0.37%"""
P2 = """5 全国社保基金一零三组合 203,314,703.00 0.30%
6 友邦人寿保险有限公司－传统 176,533,679.00 0.26%
7 北京诚通金控投资有限公司 154,427,250.00 0.23%
8 大家人寿保险股份有限公司－传统产品 152,022,181.00 0.22%
9 中国平安人寿保险股份有限公司－分红－个险分红 142,216,725.00 0.21%
10 大家人寿保险股份有限公司－万能产品 130,022,866.00 0.19%
注：本表统计的上市基金前十名持有人均为场内持有人。
8.3  期末基金管理人的从业人员持有本基金的情况"""


def test_title_filter_and_pick_latest():
    assert R.classify_title("XX基金2025年年度报告") == ("2025-12-31", "年度报告")
    assert R.classify_title("XX基金2026年中期报告") == ("2026-06-30", "中期报告")
    assert R.classify_title("XX基金2025年年度报告摘要") is None
    assert R.classify_title("XX公司旗下基金2024年第4季度报告提示性公告") is None
    picked = R.pick_reports([
        {"title": "A2025年年度报告", "announce_date": "2026-03-31", "url": "u1"},
        {"title": "A2025年年度报告", "announce_date": "2026-04-10", "url": "u2"},
        {"title": "A2025年第4季度报告", "announce_date": "2026-01-22", "url": "u3"}])
    assert [p["url"] for p in picked] == ["u2"]


def test_top10_multiline_names_pages_and_basis():
    t = R.parse_top10(pages(P1, P2))
    assert t["errors"] == []
    assert t["ratio_basis"] == "占上市总份额比例"
    rows = t["rows"]
    assert [r["rank"] for r in rows] == list(range(1, 11))
    assert rows[3]["name"] == "易方达基金－中央汇金资产管理有限责任公司－易方达基金－汇金资管单一资产管理计划"
    assert rows[0]["shares"] == 28538696695.0 and rows[0]["pct"] == 41.80 and rows[0]["page"] == 1
    assert rows[4]["page"] == 2


def test_holder_scopes_not_double_counted():
    t = R.parse_top10(pages(P1, P2))
    s = R.holder_summary(t)
    assert s["narrow_identified"] and s["narrow_labels"] == ["汇金投资", "汇金资管"]
    assert s["narrow_own_lb"] == 28538696695.0 + 27355388757.0          # 自有两主体之和，仅为下限
    assert s["narrow_with_products_lb"] == s["narrow_own_lb"] + 254000077.0
    assert [p["page"] for p in s["products"]] == [1]                       # 委托产品逐行保留原文页码
    assert s["broad_lb"] == 203314703.0                                     # 社保为广义，不并入汇金
    assert R.classify_holder("中央汇金投资有限责任公司")[2] == "narrow"
    assert R.classify_holder("友邦人寿保险有限公司－分红")[0] is None


def test_no_huijin_in_top10_is_unknown_not_zero():
    """H1：前十名里没有任何汇金主体（真实 588000 情形）→ 合计为 None（未识别≠0），不是 0.00。"""
    p1 = P1.replace("中央汇金资产管理有限责任公司 28,538", "某保险公司 28,538") \
           .replace("中央汇金投资有限责任公司", "某证券公司") \
           .replace("易方达基金－中央汇金资产管理有限责\n任公司－易方达基金－汇金资管单一资\n产管理计划", "某信托计划")
    s = R.holder_summary(R.parse_top10(pages(p1, P2)))
    assert s["narrow_identified"] is False
    assert s["narrow_own_lb"] is None and s["narrow_with_products_lb"] is None and s["products"] == []


def test_multiple_products_all_kept():
    p2 = P2.replace("5 全国社保基金一零三组合", "5 华夏基金－中央汇金资产管理有限责任公司－华夏基金－汇金资管单一资产管理计划")
    s = R.holder_summary(R.parse_top10(pages(P1, p2)))
    assert len(s["products"]) == 2 and {p["page"] for p in s["products"]} == {1, 2}
    assert s["products_lb"] == 254000077.0 + 203314703.0


def test_truncated_table_rejected():
    """H2：只解析到部分行且无其它错误时，也必须拒绝（截断）。"""
    t = R.parse_top10(pages(P1 + "\n注：截断"))
    assert any("疑似截断" in e for e in t["errors"])


def test_inconsistent_denominator_flags_parse_failed():
    bad = P1.replace("40.07%", "4.07%")
    t = R.parse_top10(pages(bad, P2))
    assert t["errors"]


def test_no_top10_section_is_unknown_not_zero(tmp_path):
    lines = pages("8.1  期末基金份额持有人户数及持有人结构\n8.2  期末基金管理人的从业人员持有本基金的情况")
    assert R.parse_top10(lines) is None
    assert R.holder_summary(None) is None


def test_toc_line_not_taken_as_section():
    lines = pages("8.2  期末上市基金前十名持有人 .......................... 56")
    assert R.parse_top10(lines) is None


def test_split_numbers_self_check():
    assert R.split_numbers("19,607,7 70,466.0 0 8,930,92 6,229.00 0.00 28,538,6 96,695.0 0", 4) == [
        19607770466.0, 8930926229.0, 0.0, 28538696695.0]
    assert R.split_numbers("1,000.00 -", 2) == [1000.0, 0.0]
    assert R.split_numbers("1,000.00 2", 2) is None


def test_big20_anonymous_rows():
    txt = """11.1  报告期内单一投资者持有基金份额比例达到或超过 20%的情况
投资者类别
持有份
额
份额占
比
机构
1 2025年 01月 01 日 ~2025年 06月 30日 19,607,7 70,466.0 0 8,930,92 6,229.00 0.00 28,538,6 96,695.0 0 41.71 %
2 2025年 01月 01 日 ~2025年 06月 30日 27,355,3 88,757.0 0 0.00 0.00 27,355,3 88,757.0 0 39.98 %
产品特有风险"""
    b = R.parse_big20(pages(txt))
    assert [r["label"] for r in b["rows"]] == ["机构", "机构"]
    assert all(r["valid"] for r in b["rows"])
    assert b["rows"][1]["end"] == 27355388757.0 and b["rows"][1]["end_pct"] == 39.98


def test_structure_picks_unique_consistent_split():
    txt = """8.1  期末基金份额持有人户数及持有人结构
持有人户数 户均持有 机构投资者 个人投资者 中国建设银行股份有限公司－某某交易型开放式指数证券投资基金联接基金
持有份额 占总份额比例 持有份额 占总份额比例 持有份额 占总份额比例
108,328
631,644.3
3
66,228,603,
753.00
96.79%
2,196,163,7
23.00
3.21%
4,592,607,6
19.00
6.71%
注：已包含场外持有人。机构投资者“持有份额”和“占总份额比例”数据中已包含该基金的联接
基金“持有份额”和“占总份额比例”数据。
8.2 期末上市基金前十名持有人"""
    s = R.parse_structure(pages(txt))
    assert s["valid"] and s["inst_shares"] == 66228603753.0 and s["indiv_shares"] == 2196163723.0
    assert s["feeder_shares"] == 4592607619.0 and s["feeder_in_inst_stated"]
    assert s["inst_upper"] == 66228603753.0 - 4592607619.0
    # 原文未注明“机构含联接” → 不扣除，保守用完整机构合计
    s2 = R.parse_structure(pages(txt.split("注：")[0] + "注：已包含场外持有人。"))
    assert s2["inst_upper"] == 66228603753.0 and "未扣联接" in s2["inst_upper_basis"]


RAW = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw", "reports")


@pytest.mark.skipif(not glob.glob(os.path.join(RAW, "510310", "510310_20250830_*.pdf")), reason="需先运行 run.py update 下载原文")
def test_real_pdf_510310_2025h1_and_2026h1():
    f25 = glob.glob(os.path.join(RAW, "510310", "510310_20250830_*.pdf"))[0]
    ex = R.extract(f25)
    assert ex["status"] == "named_top10"
    r1 = ex["top10"]["rows"][0]
    assert (r1["name"], r1["shares"], r1["pct"], r1["page"]) == ("中央汇金资产管理有限责任公司", 28538696695.0, 41.80, 56)
    f26 = glob.glob(os.path.join(RAW, "510310", "510310_20260831_*.pdf"))
    if f26:
        ex26 = R.extract(f26[0])
        assert ex26["status"] == "no_top10_section" and ex26["huijin_mentions"] == 0


def test_percentless_column_page_number_and_trailing_name():
    p1 = """8.2 期末上市基金前十名持有人
序号 持有人名称 持有份额（份） 占上市总份额比例（%）
1 中央汇金投资有限责 任公司 19,543,686,916.00 47.39
2 银华基金－中国人寿保险 股份有限公司－传统险－ 253,264,600.00 0.55"""
    p2 = """42
银华基金国寿股份均衡股
票传统可供出售单一资产
管理计划
3 肇弘义 213,000,000.00 0.46
注：前十名持有人为除本基金的联接基金之外的前十名持有人。"""
    raw = R.clean_pages([HDR + "\n" + p1 + "\n第 41 页共 61 页", HDR + "\n" + p2] + [""] * 40)
    t = R.parse_top10(raw)
    assert t["ratio_basis"] == "占上市总份额比例（%）"
    assert [r["rank"] for r in t["rows"]] == [1, 2, 3]
    assert t["rows"][0]["name"] == "中央汇金投资有限责任公司" and t["rows"][0]["pct"] == 47.39
    assert t["rows"][1]["name"].endswith("传统险－银华基金国寿股份均衡股票传统可供出售单一资产管理计划")
    assert t["note"].startswith("注：前十名持有人为除本基金的联接基金之外")


def test_structure_feeder_separate_layout_not_deducted():
    """机构+个人+联接=100% 版式：联接单列不在机构内，上限=完整机构合计，不再扣除。"""
    txt = """8.1  期末基金份额持有人户数及持有人结构
持有人户数 户均持有 机构投资者 个人投资者 中国工商银行股份有限公司－某某交易型开放式指数证券投资基金联接基金
持有份额 占总份额比例 持有份额 占总份额比例 持有份额 占总份额比例
1,000
100,000.00
80,000.00
80.00%
18,000.00
18.00%
2,000.00
2.00%
8.2 期末上市基金前十名持有人"""
    s = R.parse_structure(pages(txt))
    assert s["valid"] and s["layout"] == "feeder_separate"
    assert s["inst_shares"] == 80000.0 and s["feeder_shares"] == 2000.0 and s["total_shares"] == 100000.0
    assert s["inst_upper"] == 80000.0 and "无需扣除" in s["inst_upper_basis"]
