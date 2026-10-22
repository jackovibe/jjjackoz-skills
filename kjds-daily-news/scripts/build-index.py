#!/usr/bin/env python3
"""期次索引页生成器（v2.8.0 新增）。

扫描项目根目录与 归档/YYYY-MM/ 下的 跨境早报-YYYY-MM-DD.html，
聚合为单文件索引页 跨境早报索引_v1.0.html（玻璃拟态暗色风格，无外部依赖）：
- 按月分组、倒序排列，每期显示 条数/来源数/头条标题
- 顶部搜索框可按关键词/日期过滤（内联 JS，无 CDN）
- 相对链接指向各期文件，本地与静态托管均可直接打开

用法: python build-index.py <项目根> [-o 输出文件]
"""
from __future__ import annotations
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

VERSION = "v1.0"
CHANGELOG = "v1.0（2026-10-20）：首版。期次聚合 + 月分组 + 关键词过滤。"
NAME_RE = re.compile(r"^跨境早报-(\d{4}-\d{2}-\d{2})\.html$")
COUNT_RE = re.compile(r"精选\s*(\d+)\s*条")
SRC_RE = re.compile(r"采用\s*(\d+)\s*个独立来源")
TITLE_RE = re.compile(r'class="card-title"[^>]*>\s*(?:<a[^>]*>)?(.*?)(?:</a>)?\s*<', re.S)

def strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()

def parse_issue(path: Path) -> dict | None:
    m = NAME_RE.match(path.name)
    if not m:
        return None
    try:
        html = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"⚠️ 无法读取 {path}: {e}", file=sys.stderr)
        return None
    count = COUNT_RE.search(html)
    src = SRC_RE.search(html)
    # 头条标题：优先 hero-card 内的第一个 card-title，否则全文第一个
    hero = html.find("hero-card")
    tm = None
    if hero > -1:
        tm = TITLE_RE.search(html, hero)
    if tm is None:
        tm = TITLE_RE.search(html)
    return {
        "date": m.group(1),
        "count": int(count.group(1)) if count else None,
        "sources": int(src.group(1)) if src else None,
        "headline": strip_tags(tm.group(1))[:60] if tm else "",
    }

def collect(root: Path) -> list[dict]:
    issues: dict[str, tuple[Path, dict]] = {}
    candidates: list[Path] = []
    candidates += sorted(root.glob("跨境早报-*.html"))
    archive = root / "归档"
    if archive.is_dir():
        candidates += sorted(archive.glob("*/*.html"))
    for p in candidates:
        info = parse_issue(p)
        if info is None:
            continue
        d = info["date"]
        # 根目录优先（保留最近 2 天），归档同名视为旧副本
        if d not in issues or p.parent == root:
            issues[d] = (p, info)
    return [dict(info, path=p) for d, (p, info) in sorted(issues.items(), reverse=True)]

def month_label(date: str) -> str:
    y, mo = date.split("-")
    return f"{y} 年 {int(mo)} 月"

def build_html(issues: list[dict], out_path: Path) -> str:
    from urllib.parse import quote
    rows: list[str] = []
    last_month = None
    for it in issues:
        mo = it["date"][:7]
        if mo != last_month:
            last_month = mo
            n = sum(1 for x in issues if x["date"][:7] == mo)
            rows.append(f'      <div class="month"><span>{month_label(mo)}</span><em>{n} 期</em></div>')
        try:
            rel = it["path"].resolve().relative_to(out_path.parent.resolve())
        except ValueError:
            rel = Path("file:///") / it["path"].resolve().as_posix()
        href = quote(rel.as_posix())
        kw = f"{it['date']} {it['headline']}"
        count = it["count"] if it["count"] is not None else "—"
        src = it["sources"] if it["sources"] is not None else "—"
        hl = it["headline"] or "（未解析到头条标题）"
        d = it["date"]
        wd = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][datetime.strptime(d, "%Y-%m-%d").weekday()]
        rows.append(
            f'      <a class="issue" href="{href}" data-kw="{kw}">'
            f'<span class="iss-date"><b>{d[5:].replace("-", " / ")}</b><i>{wd}</i></span>'
            f'<span class="iss-main"><span class="iss-head">{hl}</span>'
            f'<span class="iss-meta">{count} 条 · {src} 个来源</span></span>'
            f'<span class="iss-arrow">→</span></a>')
    total = len(issues)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>跨境早报 · 期次索引</title>
<style>
:root {{
  --bg-primary:#0c0c16; --card-bg:rgba(255,255,255,.04); --card-border:rgba(255,255,255,.09);
  --text-primary:#eef0ff; --text-secondary:rgba(255,255,255,.62); --text-muted:rgba(255,255,255,.36);
  --accent:#a78bfa; --indigo:#6366f1;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;
  background:var(--bg-primary); color:var(--text-primary); min-height:100vh; padding:28px 16px 40px;
  background-image:radial-gradient(ellipse 60% 40% at 50% -10%,rgba(99,102,241,.18),transparent);
}}
.wrap {{ max-width:760px; margin:0 auto; }}
h1 {{ font-size:24px; font-weight:800; letter-spacing:1px;
  background:linear-gradient(135deg,#f0f0ff,#a78bfa); -webkit-background-clip:text; background-clip:text; color:transparent; }}
.sub {{ color:var(--text-secondary); font-size:13px; margin:6px 0 18px; }}
.search {{ width:100%; padding:11px 14px; border-radius:12px; border:1px solid var(--card-border);
  background:var(--card-bg); color:var(--text-primary); font-size:14px; outline:none; margin-bottom:20px; }}
.search:focus {{ border-color:var(--accent); }}
.month {{ display:flex; align-items:baseline; gap:10px; margin:22px 2px 10px; color:var(--accent);
  font-weight:700; font-size:14px; letter-spacing:1px; }}
.month em {{ font-style:normal; color:var(--text-muted); font-size:12px; font-weight:400; }}
.issue {{ display:flex; align-items:center; gap:12px; text-decoration:none; color:var(--text-primary);
  background:var(--card-bg); border:1px solid var(--card-border); border-radius:12px;
  padding:12px 14px; margin-bottom:8px; transition:background .15s,border-color .15s,transform .15s; }}
.issue:hover {{ background:rgba(255,255,255,.075); border-color:rgba(255,255,255,.16); transform:translateY(-1px); }}
.iss-date {{ flex:0 0 84px; text-align:center; font-family:ui-monospace,Consolas,monospace; }}
.iss-date b {{ display:block; font-size:14px; color:var(--accent); }}
.iss-date i {{ font-style:normal; font-size:11px; color:var(--text-muted); }}
.iss-main {{ flex:1; min-width:0; }}
.iss-head {{ display:block; font-size:13.5px; line-height:1.45; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.iss-meta {{ font-size:11.5px; color:var(--text-secondary); }}
.iss-arrow {{ color:var(--text-muted); }}
.none {{ color:var(--text-secondary); font-size:13px; padding:16px; text-align:center; }}
footer {{ margin-top:26px; font-size:11.5px; color:var(--text-muted); line-height:1.7; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>跨境早报 · 期次索引</h1>
  <p class="sub">共 {total} 期 · 点击任意期次打开当期早报</p>
  <input class="search" id="q" type="search" placeholder="搜索日期、关键词…（过滤期次）" aria-label="过滤期次">
  <div id="list">
{chr(10).join(rows) if rows else '      <div class="none">未找到任何期次</div>'}
  </div>
  <footer>
    跨境早报期次索引 {VERSION} · 生成于 {now}（Asia/Shanghai）<br>
    {CHANGELOG}
  </footer>
</div>
<script>
document.addEventListener('DOMContentLoaded', function() {{
  var q = document.getElementById('q');
  var items = Array.prototype.slice.call(document.querySelectorAll('.issue'));
  var months = Array.prototype.slice.call(document.querySelectorAll('.month'));
  q.addEventListener('input', function() {{
    var v = q.value.trim().toLowerCase();
    items.forEach(function(el) {{
      var hay = (el.getAttribute('data-kw') || '').toLowerCase();
      el.style.display = (!v || hay.indexOf(v) > -1) ? '' : 'none';
    }});
    months.forEach(function(el) {{ el.style.display = v ? 'none' : ''; }});
  }});
}}, {{ once: true }});
</script>
</body>
</html>"""

def main() -> None:
    ap = argparse.ArgumentParser(description="生成跨境早报期次索引页")
    ap.add_argument("root", help="项目根目录（含 跨境早报-*.html 与 归档/）")
    ap.add_argument("-o", "--output", default=None, help="输出文件（默认 <root>/跨境早报索引_v1.0.html）")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"项目根不存在: {root}", file=sys.stderr); sys.exit(1)
    out = Path(args.output).resolve() if args.output else root / f"跨境早报索引_{VERSION}.html"
    issues = collect(root)
    if not issues:
        print("未找到任何 跨境早报-YYYY-MM-DD.html 期次文件", file=sys.stderr); sys.exit(1)
    out.write_text(build_html(issues, out), encoding="utf-8")
    print(f"✅ 索引页已生成: {out}")
    print(f"   共 {len(issues)} 期（最近一期 {issues[0]['date']}，最早 {issues[-1]['date']}）")

if __name__ == "__main__":
    main()
