#!/usr/bin/env python3
"""早报 HTML 渲染器 —— 吃结构化 JSON，出符合 validator 的结构。

为什么要这个脚本（v2.10.0）：
以前每期由模型对着 308 行 html-spec.md 手写 HTML，再由 validator 的 23 项结构检查
事后拦截。结构错误本该不可能发生，而不是靠写完再查。改成模板渲染后：
- 计数（Header 条数 / 分区 count / 来源 pill）由数据算出，不会对不上
- 分区顺序、class 名、fold-impact/fold-act 两段由模板固定，不会漏
- 审计的定档行由同一份数据生成，AUDIT_ZONE_MISMATCH / P0_RATIO 结构性不可能出错
- validator 从此只查「内容对不对」，不再兜「结构写没写对」

用法：
  python scripts/render-report.py candidates.json                  # 出 HTML
  python scripts/render-report.py candidates.json --audit 早报审计   # 同时出审计 md
  python scripts/render-report.py --example > candidates.json      # 出一份空白骨架

输入 JSON 结构见 --example 输出，字段说明见 references/html-spec.md 第 0 节。
"""
import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
CSS_PATH = HERE.parent / "assets" / "report.css"

SECTIONS = [
    ("cat-policy", "sec-policy", "①", "平台政策与费用", "nd-policy"),
    ("cat-reg", "sec-reg", "②", "合规与监管", "nd-reg"),
    ("cat-logistics", "sec-logistics", "③", "物流与供应链", "nd-logistics"),
    ("cat-market", "sec-market", "④", "行业与市场", "nd-market"),
    ("cat-community", "sec-community", "⑤", "卖家社区", "nd-community"),
]
WEEKDAY_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
TIER_CLASS = {"T0": "src-t0", "T1": "src-t1", "T2": "src-t2", "T3": "src-t2"}
P0_MAX_RATIO = 0.4


def esc(s: str) -> str:
    """只转义属性值；正文允许作者内嵌 <b> 等标签。"""
    return (s or "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def load_css() -> str:
    if not CSS_PATH.exists():
        sys.exit(f"缺少样式文件: {CSS_PATH}")
    return CSS_PATH.read_text(encoding="utf-8")


def all_cards(data: dict) -> list:
    out = []
    for key, _, _, _, _ in SECTIONS:
        for c in data.get("sections", {}).get(key, {}).get("cards", []) or []:
            out.append((key, c))
    return out


def render_card(card: dict, zone_sym: str) -> str:
    hero = " hero-card" if card.get("hero") else ""
    url = esc(card["url"])
    meta = [f'      <span class="card-date">{esc(card["date"])}</span>',
            f'      <span class="card-source {TIER_CLASS.get(card.get("src_tier", "T1"), "src-t1")}">{esc(card["source"])}</span>']
    if card.get("tag"):
        meta.append(f'      <span class="badge badge-info">{esc(card["tag"])}</span>')
    if card.get("deadline"):
        meta.append(f'      <span class="dl dl-high">{esc(card["deadline"])}</span>')
    # 版面只标「头条」，档位（P0/P1/P2/社区）留在审计里 —— 读者不需要知道内部档位名
    tier_badge = '<div class="hero-flag">头条</div>' if hero else ""
    return f"""  <div class="card{hero}">
    {tier_badge}<div class="card-title"><a href="{url}">{card['title']}</a></div>
    <div class="card-meta">
{chr(10).join(meta)}
    </div>
    <div class="card-summary">{card.get('summary', '')}</div>
    <details class="fold" open>
      <summary>对卖家的意义</summary>
      <div class="fold-body">
        <p class="fold-impact"><b>影响：</b>{card.get('impact', '')}</p>
        <p class="fold-act"><b>建议动作：</b>{card.get('action', '')}</p>
      </div>
    </details>
    <a class="card-link" href="{url}">→ 原文链接</a>
  </div>"""


def render_section(key: str, sec_id: str, sym: str, name: str, dot: str, cards: list) -> str:
    body = ("\n".join(render_card(c, sym) for c in cards) if cards
            else '  <div class="empty">⚪ 今日暂无 ' + name + ' 更新</div>')
    return f"""<div class="section {key}" id="{sec_id}">
  <div class="section-header">
    <span class="dot"></span>
    <span>{name}</span>
    <span class="count">{len(cards)} 条</span>
  </div>

{body}
</div>"""


def render_header(data: dict, cards: list) -> str:
    d = date.fromisoformat(data["date"])
    window = data.get("window", ["", ""])
    sources = []
    for _, c in cards:
        if c["source"] not in sources:
            sources.append(c["source"])
    tiers = {c.get("src_tier", "T1") for _, c in cards}
    tier_foot = " · ".join(
        f"{t} {'官方' if t == 'T0' else '行业' if t == 'T1' else '社区'} {sum(1 for _, c in cards if c.get('src_tier', 'T1') == t)}"
        for t in ("T0", "T1", "T2") if t in tiers)
    zones = sum(1 for k, *_ in SECTIONS if data.get("sections", {}).get(k, {}).get("cards"))
    mins = max(3, round(len(cards) * 0.62))
    cd = sorted(data.get("countdown", []) or [], key=lambda x: x["date"])
    nearest = cd[0] if cd else None
    nearest_txt = "无" if not nearest else f"T-{(date.fromisoformat(nearest['date']) - d).days}"
    nearest_foot = "本期无 45 天内截止项" if not nearest else f"{esc(nearest['name'])}（{nearest['date'][5:]}）"

    cd_html = []
    for it in cd:
        days = (date.fromisoformat(it["date"]) - d).days
        lvl = it.get("level") or ("high" if days <= 7 else "mid" if days <= 30 else "low")
        cd_html.append(f"""    <div class="countdown-item cd-{lvl}">
      <span class="cd-tag">T-{days}</span>
      <span class="cd-name">{esc(it['name'])}（{it['date'][5:]}）</span>
    </div>""")
    pills = "\n".join(
        f'    <span class="source-pill {TIER_CLASS.get(next((c.get("src_tier", "T1") for _, c in cards if c["source"] == s), "T1"), "src-t1")}">{esc(s)}</span>'
        for s in sources)
    return f"""<header class="header">
  <div class="header-date">{WEEKDAY_EN[d.weekday()]} · {d.strftime('%Y.%m.%d')}</div>
  <h1 class="header-title">跨境电商每日早报</h1>
  <div class="header-sub">精选 <b>{len(cards)}</b> 条<span class="sep">·</span>采用 <b>{len(sources)}</b> 个独立来源<span class="sep">·</span>窗口 {esc(window[0][:10])} ~ {esc(window[1][:10])}</div>

  <div class="kpi-strip">
    <div class="kpi">
      <div class="kpi-label">本期资讯</div>
      <div class="kpi-value">{len(cards)}</div>
      <div class="kpi-foot">分布在 {zones} 个主题分区</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">独立来源</div>
      <div class="kpi-value">{len(sources)}</div>
      <div class="kpi-foot">{tier_foot}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">阅读时长</div>
      <div class="kpi-value">约 {mins} 分</div>
      <div class="kpi-foot">展开「对卖家的意义」约 {round(mins * 2.2)} 分</div>
    </div>
    <div class="kpi kpi-alert">
      <div class="kpi-label">最近截止</div>
      <div class="kpi-value">{nearest_txt}</div>
      <div class="kpi-foot">{nearest_foot}</div>
    </div>
  </div>

  <div class="countdown-wrap">
{chr(10).join(cd_html) if cd_html else '    <div class="countdown-item cd-low"><span class="cd-tag">—</span><span class="cd-name">本期无倒计时节点</span></div>'}
  </div>
  <div class="legend">
    <span><i class="lg-high"></i>≤7 天 · 本周处理</span>
    <span><i class="lg-mid"></i>8–30 天 · 需排期</span>
    <span><i class="lg-low"></i>&gt;30 天 · 观察</span>
  </div>

  <div class="source-bar">
{pills}
  </div>
</header>"""


def render(data: dict) -> str:
    cards = all_cards(data)
    nav = "\n".join(
        f'  <button class="nav-item" data-target="{sid}"><i class="nav-dot {dot}"></i>{name}<b>{len(data.get("sections", {}).get(key, {}).get("cards", []) or [])}</b></button>'
        for key, sid, sym, name, dot in SECTIONS)
    body = []
    for key, sid, sym, name, dot in SECTIONS:
        body.append(f"<!-- ===== {sym} {name} ===== -->")
        body.append(render_section(key, sid, sym, name, dot, data.get("sections", {}).get(key, {}).get("cards", []) or []))
    trends = "\n\n".join(f"""  <div class="trend-item">
    <div class="trend-head"><span class="trend-dot"></span><b>{t['head']}</b><span class="trend-tag">{esc(t.get('tag', ''))}</span></div>
    <p>{t.get('text', '')}</p>
  </div>""" for t in data.get("trends", []) or [])
    tl = "\n".join(f"""  <div class="tl-item{(' tl-' + t['level']) if t.get('level') else ''}">
    <span class="tl-date">{t['date']}</span>
    <div class="tl-body"><b>{t['title']}</b>：{t.get('note', '')} <a href="{esc(t['url'])}">{esc(t.get('link_text', '来源'))}</a></div>
  </div>""" for t in data.get("timeline", []) or [])
    if not tl:
        tl = '  <div class="tl-item"><span class="tl-date">—</span><div class="tl-body">本期无临近节点。</div></div>'
    window = data.get("window", ["", ""])
    scope = data.get("scope_note") or f"仅收录 {window[0]} — {window[1]}（Asia/Shanghai）发布或明确更新的资讯；旧政策只进入「临近节点提醒」时间线并标注原始日期。"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>跨境电商每日早报 · {data['date']}</title>
<style>
{load_css()}
</style>
</head>
<body>
<div id="pbar"></div>

{render_header(data, cards)}

<div class="nav-bar">
{nav}
</div>

<div class="scope-note"><b>本期口径：</b>{scope}</div>

{chr(10).join(body)}

<div class="trends-section">
  <div class="trends-title">今日趋势总结</div>

{trends}
</div>

<div class="timeline-section">
  <div class="section-header"><span class="dot"></span><span>临近节点提醒</span></div>
{tl}
</div>

<footer>本期资讯生成于 {data['generated_at']}（Asia/Shanghai） · v2.10.0</footer>

<button id="toTop" aria-label="回到顶部">↑</button>

<script>
(function(){{
  var pbar=document.getElementById('pbar');
  var toTop=document.getElementById('toTop');
  function onScroll(){{
    var h=document.documentElement.scrollHeight-window.innerHeight;
    if(pbar) pbar.style.width=(h>0?(window.scrollY/h)*100:0)+'%';
    if(window.scrollY>480){{toTop.classList.add('show');}}else{{toTop.classList.remove('show');}}
  }}
  window.addEventListener('scroll',onScroll,{{passive:true}});
  toTop.addEventListener('click',function(){{window.scrollTo({{top:0,behavior:'smooth'}});}});
  var items=document.querySelectorAll('.nav-item');
  for(var i=0;i<items.length;i++){{
    items[i].addEventListener('click',function(){{
      var t=document.getElementById(this.getAttribute('data-target'));
      if(t){{t.scrollIntoView({{behavior:'smooth',block:'start'}});}}
    }});
  }}
}})();
</script>
</body>
</html>
"""


def render_audit(data: dict) -> str:
    """审计由同一份数据生成 —— 定档行/分区分布/P0 计数结构性不可能与报告不符。"""
    cards = all_cards(data)
    total = len(cards)
    p0 = sum(1 for _, c in cards if c.get("tier") == "P0")
    limit = max(1, int(total * P0_MAX_RATIO))
    lines = [f"# 早报审计 · {data['date']}", "",
             "## 一、运行概况", "",
             f"- 运行日期：{data['date']}（窗口 {data.get('window', ['', ''])[0]} ~ {data.get('window', ['', ''])[1]}）",
             f"- 候选总数：{data.get('stats', {}).get('candidates', '—')}",
             f"- shortlist：{data.get('stats', {}).get('shortlist', '—')}",
             f"- 验证通过：{total + data.get('stats', {}).get('rejected_in_verify', 0)}",
             f"- 最终采用：**{total}**",
             f"- P0 定档：{p0} / 上限 {limit}（卡片数 {total} × 40%，最少 1 条）", "",
             "## 二、最终采用（定档行，validator 逐行解析）", ""]
    for key, sid, sym, name, dot in SECTIONS:
        for c in data.get("sections", {}).get(key, {}).get("cards", []) or []:
            tier = c.get("tier") or ("社区" if key == "cat-community" else "P1")
            note = c.get("audit_note") or c.get("sort_note") or "—"
            lines.append(f"[{tier}] {sym} {c['title']} | {note}")
    lines += ["", "## 三、淘汰记录（表格，不参与计数）", "",
              "| 候选 | 代码 | 说明 |", "|------|------|------|"]
    for r in data.get("rejected", []) or []:
        lines.append(f"| {r['title']} | `{r['code']}` | {r.get('reason', '')} |")
    if not data.get("rejected"):
        lines.append("| — | — | 本期无淘汰 |")
    lines += ["", f"最终报告：{data['date']} · {total} 条", ""]
    return "\n".join(lines)


def example() -> dict:
    return {
        "date": "2026-10-21",
        "generated_at": "2026-10-21 07:50",
        "window": ["2026-10-20 00:00", "2026-10-21 07:50"],
        "scope_note": "",
        "stats": {"candidates": 0, "shortlist": 0, "rejected_in_verify": 0},
        "countdown": [{"date": "2026-10-27", "name": "示例节点名称", "level": "high"}],
        "trends": [{"head": "一句话结论", "tag": "标签", "text": "支撑结论的事实，可含 <b>强调</b>。"}],
        "timeline": [{"date": "2026-11-01", "title": "节点事项", "note": "一句话说明", "url": "https://example.com/a", "link_text": "来源", "level": "warn"}],
        "sections": {
            "cat-policy": {"cards": [{
                "tier": "P0", "hero": True, "title": "卡片标题", "url": "https://www.marketplacepulse.com/articles/x",
                "date": "2026-10-20", "source": "Marketplace Pulse", "src_tier": "T1",
                "tag": "后台功能", "deadline": "", "summary": "只写原文事实。",
                "impact": "对卖家意味着什么。", "action": "明天要改什么。", "audit_note": "排序:当日/影响全站"}]},
            "cat-reg": {"cards": []},
            "cat-logistics": {"cards": []},
            "cat-market": {"cards": []},
            "cat-community": {"cards": []},
        },
        "rejected": [{"title": "被淘汰的候选", "code": "A9", "reason": "非发布载体"}],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="?", help="candidates.json 路径")
    ap.add_argument("--out", help="输出 HTML 路径（默认为 跨境早报-<date>.html）")
    ap.add_argument("--audit", help="同时输出审计 md 到该目录（如 早报审计）")
    ap.add_argument("--example", action="store_true", help="打印空白骨架 JSON")
    ap.add_argument("--check-only", action="store_true", help="只做数据自检，不写文件")
    args = ap.parse_args()

    if args.example:
        print(json.dumps(example(), ensure_ascii=False, indent=2))
        return
    if not args.data:
        ap.error("需要 candidates.json；用 --example 生成骨架")

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    cards = all_cards(data)

    errs = []
    if not cards:
        errs.append("没有任何卡片")
    if len(cards) < 7:
        errs.append(f"卡片 {len(cards)} 条，低于版面最低 7 条")
    seen = {}
    for key, c in cards:
        for f in ("title", "url", "date", "source", "summary", "impact", "action"):
            if not c.get(f):
                errs.append(f"卡片缺字段 {f}: {c.get('title', '?')[:30]}")
        if c["url"] in seen:
            errs.append(f"URL 重复: {c['url']}")
        seen[c["url"]] = 1
        if c["date"] > data["date"]:
            errs.append(f"卡片日期晚于生成日: {c['date']} > {data['date']}")
    p0 = sum(1 for _, c in cards if c.get("tier") == "P0")
    limit = max(1, int(len(cards) * P0_MAX_RATIO))
    if p0 > limit:
        errs.append(f"P0 {p0} 条超过上限 {limit} 条，须先降档再渲染")
    if errs:
        print("❌ 数据自检未通过：")
        for e in errs:
            print("   -", e)
        sys.exit(1)

    html = render(data)
    out = Path(args.out or f"跨境早报-{data['date']}.html")
    out.write_text(html, encoding="utf-8")
    print(f"✅ HTML 已生成: {out}（{out.stat().st_size:,} 字节，{len(cards)} 卡）")
    if args.audit:
        ad = Path(args.audit)
        ad.mkdir(parents=True, exist_ok=True)
        ap_ = ad / f"{data['date']}.md"
        ap_.write_text(render_audit(data), encoding="utf-8")
        print(f"✅ 审计已生成: {ap_}")
    if not args.check_only:
        print(f"   下一步: python scripts/validate-report.py {out}")


if __name__ == "__main__":
    main()
