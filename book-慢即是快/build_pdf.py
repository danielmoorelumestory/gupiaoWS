#!/usr/bin/env python3
"""把《正念投资》书稿合并成单个 HTML，供 Chrome 无头打印成 PDF。"""
import re
import html as html_lib
import sys
from pathlib import Path

import markdown

BOOK_DIR = Path(__file__).parent
OUT_HTML = BOOK_DIR / "正念投资.html"

BOOK_TITLE = "正念投资"
BOOK_SUBTITLE = "普通人用规则代替盯盘的投资方法"


def chapter_key(p: Path):
    m = re.match(r"第(\d+)章", p.name)
    if m:
        return (1, int(m.group(1)))
    if p.name.startswith("开篇"):
        return (0, 0)
    m = re.match(r"附录([A-Z])", p.name)
    if m:
        return (2, ord(m.group(1)))
    return (9, 0)


def main():
    # Use the reader's mainline manifest; review notes and work lists are excluded.
    reader = (BOOK_DIR.parent / "BusinessWeb/src/pages/FirstBook.tsx").read_text()
    mainline = reader.split("const EXTRA_FILES =", 1)[0]
    names = re.findall(r"file: '([^']+)'", mainline)
    files = [BOOK_DIR / name for name in names]
    assert len(files) == 53, "Expected opening, 40 chapters, 3 topics and 9 appendices"
    assert all(f.exists() for f in files), "Missing manuscript source"
    if not files:
        sys.exit("没有找到章节文件")

    parts = []
    toc = []
    for index, f in enumerate(files):
        text = f.read_text(encoding="utf-8")
        # 一级标题作为章标题；若无则退回文件名
        m = re.search(r"^# (.+)$", text, re.M)
        title = m.group(1).strip() if m else f.stem
        body_html = markdown.markdown(
            text, extensions=["fenced_code", "tables", "nl2br"]
        )
        parts.append(f'<section class="chapter" id="chapter-{index}">{body_html}</section>')
        toc.append(title)
        print(f"  {f.name} -> {title}")

    toc_html = "".join(
        f'<div class="toc-line"><a href="#chapter-{i}">{html_lib.escape(t)}</a></div>' for i, t in enumerate(toc)
    )

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{BOOK_TITLE}：{BOOK_SUBTITLE}</title>
<style>
  @page {{
    size: A4; margin: 22mm 18mm 20mm 18mm;
    @bottom-center {{ content: counter(page); font-size: 9pt; color: #777; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: "Songti SC", "STSong", "PingFang SC", serif;
    font-size: 11pt; line-height: 1.7; color: #1a1a1a; margin: 0;
  }}
  .cover {{
    height: 240mm; display: flex; flex-direction: column;
    align-items: center; justify-content: center; text-align: center;
  }}
  .cover h1 {{ font-size: 42pt; letter-spacing: 12pt; margin: 0; }}
  .cover p.sub {{ font-size: 15pt; color: #555; margin-top: 18pt; }}
  .toc {{ page-break-after: always; }}
  .toc h2 {{ text-align: center; font-size: 18pt; letter-spacing: 6pt; }}
  .toc-line {{ padding: 2pt 0; font-size: 10pt; line-height: 1.5; }}
  .toc a {{ color: #222; text-decoration: none; }}
  h1, h2, h3 {{ break-after: avoid; }}
  p {{ orphans: 3; widows: 3; }}
  a {{ color: #40556b; overflow-wrap: anywhere; }}
  tr {{ break-inside: avoid; }}
  thead {{ display: table-header-group; }}
  .chapter {{ page-break-before: always; }}
  h1 {{
    font-size: 20pt; text-align: center; letter-spacing: 1pt;
    margin: 0 0 20pt; padding-bottom: 10pt;
    border-bottom: 1.5pt solid #333;
  }}
  h2 {{ font-size: 15pt; margin: 20pt 0 8pt; }}
  h3 {{ font-size: 12.5pt; margin: 14pt 0 6pt; }}
  p {{ margin: 0 0 8pt; text-indent: 2em; }}
  li p {{ text-indent: 0; }}
  ul, ol {{ padding-left: 2em; margin: 4pt 0 10pt; }}
  li {{ margin-bottom: 3pt; }}
  blockquote {{
    margin: 10pt 0; padding: 6pt 14pt; background: #f6f3ec;
    border-left: 3pt solid #a08a5f; color: #444;
  }}
  blockquote p {{ text-indent: 0; }}
  code {{
    font-family: "SF Mono", Menlo, monospace; font-size: 9.5pt;
    background: #f2f2f2; padding: 1pt 4pt; border-radius: 3pt;
  }}
  pre {{
    background: #f7f7f7; padding: 10pt; border-radius: 4pt;
    overflow-wrap: anywhere; white-space: pre-wrap;
  }}
  pre code {{ background: none; padding: 0; }}
  table {{
    border-collapse: collapse; width: 100%; margin: 10pt 0; font-size: 9pt; table-layout: fixed; overflow-wrap: anywhere;
  }}
  th, td {{ border: 0.6pt solid #999; padding: 4pt 5pt; text-align: left; }}
  th {{ background: #eee; }}
  hr {{ border: none; border-top: 0.6pt solid #ccc; margin: 14pt 0; }}
</style>
</head>
<body>
<div class="cover">
  <h1>{BOOK_TITLE}</h1>
  <p class="sub">{BOOK_SUBTITLE}</p>
  <p style="font-size:11pt;color:#777;margin-top:32pt;text-indent:0">第十四轮修订版 · 2026-10-04</p>
  <p style="font-size:10pt;color:#777;text-indent:0">40章 · 3篇主线专题 · 附录A-I</p>
</div>
<div class="toc">
  <h2>目 录</h2>
  {toc_html}
</div>
{''.join(parts)}
</body>
</html>"""
    OUT_HTML.write_text(doc, encoding="utf-8")
    print(f"\n已生成 {OUT_HTML}（{len(files)} 章）")


if __name__ == "__main__":
    main()
