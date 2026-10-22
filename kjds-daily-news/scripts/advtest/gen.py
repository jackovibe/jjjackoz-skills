#!/usr/bin/env python3
"""对抗性测试样本生成器 —— 用于攻击 validate-report.py 的护栏。
输出到 ./out/*.html，由 run_adv.py 逐一喂给验证器。
每个样本故意植入一种「想蒙混过关」的缺陷。
"""
import os
import re

OUT = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(OUT, exist_ok=True)

# 基础卡片模板（默认合规）
CARD_TMPL = """      <div class="card">
        <div class="card-number">{num}</div>
        <div class="card-meta">
          <span class="card-date">2026-07-17</span>
          <span class="card-source{sclass}">{source}</span>
        </div>
        <div class="card-title"><a href="{url}">{title}</a></div>
        <div class="card-summary">{summary}</div>
        <details class="fold" open><summary>对卖家的意义</summary><div class="fold-body"><p class="fold-impact"><b>影响：</b>对相关卖家存在潜在合规与费用影响。</p><p class="fold-act"><b>建议动作：</b>关注官方后续公告并核对后台设置。</p></div></details>
        <div class="card-link"><a href="{url}">→ 原文链接</a></div>
      </div>"""

def card(num, source, url, title="测试标题", summary="测试摘要", sclass=""):
    return CARD_TMPL.format(num=num, source=source, url=url, title=title,
                            summary=summary, sclass=sclass)

# 真实报告结构：class 在 <a> 上（<a class="card-title" href>），而非 <div class="card-title"><a>
CARD_TMPL_REAL = """      <div class="card">
        <div class="card-number">{num}</div>
        <div class="card-meta">
          <span class="card-date">2026-07-17</span>
          <span class="card-source{sclass}">{source}</span>
        </div>
        <a class="card-title" href="{url}">{title}</a>
        <div class="card-summary">{summary}</div>
        <details class="fold" open><summary>对卖家的意义</summary><div class="fold-body"><p class="fold-impact"><b>影响：</b>对相关卖家存在潜在合规与费用影响。</p><p class="fold-act"><b>建议动作：</b>关注官方后续公告并核对后台设置。</p></div></details>
        <div class="card-link"><a href="{url}">→ 原文链接</a></div>
      </div>"""

def card_real(num, source, url, title="测试标题", summary="测试摘要", sclass=""):
    return CARD_TMPL_REAL.format(num=num, source=source, url=url, title=title,
                                 summary=summary, sclass=sclass)

def good_cards_real():
    out = []
    for n, s, u, t in NEWS:
        out.append(card_real(n, s, u, t))
    for n, s, u, t, sc in ZHW:
        out.append(card_real(n, s, u, t, sclass=sc))
    return "\n".join(out)

def build(cards, header_count, source_count, extra_head="", extra_body=""):
    # Current production layout always renders five fixed sections.  Keep the
    # generated samples structurally realistic so each mutation tests its own
    # intended invariant rather than failing on an obsolete layout.
    card_blocks = [x for x in re.split(r'(?=      <div class="card">)', cards) if '<div class="card">' in x]
    buckets = [card_blocks[:2], card_blocks[2:3], card_blocks[3:4], card_blocks[4:5], card_blocks[5:]]
    cats = ["cat-policy", "cat-reg", "cat-logistics", "cat-market", "cat-community"]
    names = ["平台政策与费用", "合规与监管", "物流与供应链", "行业与市场", "卖家社区"]
    sections = []
    for cat, name, bucket in zip(cats, names, buckets):
        body = "\n".join(bucket) if bucket else '      <div class="empty">⚪ 今日暂无更新</div>'
        sections.append(f'  <section class="section {cat}">\n    <div class="section-header"><span>{name}</span><span class="count">{len(bucket)} 条</span></div>\n    {body}\n  </section>')
    cards_markup = "\n".join(sections)
    source_names = []
    for b in card_blocks:
        m = re.search(r'<span class="card-source[^>]*">([^<]*)</span>', b)
        if m and m.group(1).strip() not in source_names:
            source_names.append(m.group(1).strip())
    pills = "\n".join(f'        <span class="source-pill active">{s}</span>' for s in source_names)
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>跨境电商每日早报</title>
<style>body{{background:#111}}</style>
</head>
<body>
  <header>
    <h1>跨境电商每日早报</h1>
    <p>精选 {header_count} 条 · 采用 {source_count} 个独立来源</p>
    {extra_head}
  </header>
  <div class="channels-bar">
{pills}
  </div>
  <div class="scope-note"><b>本期口径：</b>仅收录 2026-07-16 00:00 — 2026-07-17 07:50（Asia/Shanghai）发布或明确更新的资讯；旧政策只进入临近节点提醒，并标注原始日期。</div>
  <div class="cards-grid">
{cards_markup}
  </div>
  <section class="trends-section">
    <table><tr><td>趋势1</td></tr></table>
  </section>
  <div class="timeline-section">
    <div class="section-header"><span class="dot"></span><span>临近节点提醒</span></div>
    <div class="tl-item"><span class="tl-date">2026-08-01</span><div class="tl-body"><b>测试节点事项</b>：一句话说明。<a href="https://ustr.gov/article/specific-4">来源</a></div></div>
  </div>
  <footer>本期资讯生成于 2026-07-17 07:50（Asia/Shanghai）</footer>
  {extra_body}
</body>
</html>"""
    return html

# 5 条新闻 + 3 条知无不言 = 8 卡，6 个独立来源
NEWS = [
    ("01", "Marketplace Pulse", "https://www.marketplacepulse.com/articles/specific-article-1", "MP新闻"),
    ("02", "EcomCrew", "https://www.ecomcrew.com/specific-post-2", "EcomCrew新闻"),
    ("03", "亚马逊全球开店", "https://gs.amazon.cn/news/news-notices-260716", "gs新闻"),
    ("04", "CPSC.gov", "https://www.cpsc.gov/Newsroom/News-Releases/specific-3", "CPSC新闻"),
    ("05", "USTR.gov", "https://ustr.gov/article/specific-4", "USTR新闻"),
]
ZHW = [
    ("06", "知无不言", "https://www.wearesellers.com/question/1001", "知无不言帖1", ' card-source-wearesellers'),
    ("07", "知无不言", "https://www.wearesellers.com/question/1002", "知无不言帖2", ' card-source-wearesellers'),
    ("08", "知无不言", "https://www.wearesellers.com/question/1003", "知无不言帖3", ' card-source-wearesellers'),
]

def good_cards():
    out = []
    for n, s, u, t in NEWS:
        out.append(card(n, s, u, t))
    for n, s, u, t, sc in ZHW:
        out.append(card(n, s, u, t, sclass=sc))
    return "\n".join(out)

# ── 样本定义 ──────────────────────────────────────────────
samples = {}

# T1: 完全合规基线（应全部通过）
samples["T1_good_baseline"] = build(good_cards(), 8, 6)

# T2: 专栏/版块页伪装成具体文章（/blog/ 不在拦截名单）
bad2 = good_cards().replace(
    "https://www.ecomcrew.com/specific-post-2",
    "https://www.ecomcrew.com/blog/", 2)
samples["T2_aggregator_section"] = build(bad2, 8, 6)

# T3: 正文中提及禁用域名 ebrun.com（应误报，演示假阳性）
bad3 = good_cards().replace(
    "测试摘要", "测试摘要（参考：亿邦动力 ebrun.com 曾报道类似案例）", 1)
samples["T3_forbidden_in_prose"] = build(bad3, 8, 6)

# T4: 内联 style 引入外部 CDN 背景图（check_external_deps 只查 link/script/@import）
bad4_body = '<div style="background-image:url(https://external-cdn.example.com/bg.jpg)"></div>'
samples["T4_external_bg_image"] = build(good_cards(), 8, 6, extra_body=bad4_body)

# T5: 知无不言标签灌水（3 张卡都标"知无不言"，但内容可伪造）——验证器只看标签
zhw_fake = "\n".join(card(n, "知无不言", u, t, sclass=sc)
                      for n, s, u, t, sc in ZHW)
fake_news = "\n".join(card(n, s, u, t) for n, s, u, t in NEWS[:5])
samples["T5_wearesellers_label_stuffing"] = build(fake_news + "\n" + zhw_fake, 8, 6)

# T6: 日期格式错乱（2026/07/17）—— 验证器应正确拦截（只改 card-date，不改footer）
bad6 = good_cards().replace('class="card-date">2026-07-17<', 'class="card-date">2026/07/17<', 1)
samples["T6_malformed_date"] = build(bad6, 8, 6)

# T11: 禁用域名出现在 href 内（ebrun.com）—— 验证器应正确拦截（反证 T3 正文提及是安全的）
bad11 = good_cards().replace(
    "https://www.marketplacepulse.com/articles/specific-article-1",
    "https://www.ebrun.com/article/xyz", 2)
samples["T11_forbidden_in_href"] = build(bad11, 8, 6)

# T12: 已知聚合模式 /category/ —— 验证器应正确拦截（反证 T2 是「未列入口径」的漏检）
bad12 = good_cards().replace(
    "https://www.marketplacepulse.com/articles/specific-article-1",
    "https://www.ecomcrew.com/category/amazon-news", 2)
samples["T12_known_agg_category"] = build(bad12, 8, 6)

# T7: 二手源伪装（来源标 Marketplace Pulse，链接却是 36kr 二级转载，不在禁用名单）
bad7 = good_cards().replace(
    "https://www.marketplacepulse.com/articles/specific-article-1",
    "https://www.36kr.com/p/1234567", 2)
samples["T7_secondary_disguised"] = build(bad7, 8, 6)

# T8: 首页根路径伪装（链接到 amazon.com 根，非文章页）
bad8 = good_cards().replace(
    "https://www.cpsc.gov/Newsroom/News-Releases/specific-3",
    "https://www.amazon.com/", 2)
samples["T8_homepage_root"] = build(bad8, 8, 6)

# T9: 使用 channels.md 禁用的 upkuajing.com（跨境魔方），但 validator 的 FORBIDDEN 名单漏了它
bad9 = good_cards().replace(
    "https://www.marketplacepulse.com/articles/specific-article-1",
    "https://www.upkuajing.com/article/xyz", 2)
samples["T9_forbidden_subset_gap"] = build(bad9, 8, 6)

# T10: 知无不言仅 2 条（复现 7/17 缺陷）—— 验证器应拦截
news5 = "\n".join(card(n, s, u, t) for n, s, u, t in NEWS)
zhw2 = "\n".join(card(n, s, u, t, sclass=sc) for n, s, u, t, sc in ZHW[:2])
samples["T10_wearesellers_only_2"] = build(news5 + "\n" + zhw2, 7, 6)

# ── 第二轮加固后的新增对抗样本（2026-07-17 复验） ──────────
# T13: 知无不言标签 + 非 wearesellers.com 链接（标签灌水，B2 应拦）
zhw_bad_link = "\n".join(
    card(n, "知无不言", f"https://wearesellers.com.evil.example/question/{i}", t, sclass=sc)
    for i, (n, s, u, t, sc) in enumerate(ZHW, 1))
samples["T13_wearesellers_wrong_domain"] = build(fake_news + "\n" + zhw_bad_link, 8, 6)

# T14: 真实结构 <a class="card-title"> 全合规基线（应 PASS，证明 _card_title_hrefs 修复无误伤）
samples["T14_real_structure_baseline"] = build(good_cards_real(), 8, 6)

# T15: T3 禁用域名 eccang.com（易仓ERP，由 channels.md 同步）出现在 href（A5 应拦）
bad15 = good_cards().replace(
    "https://www.marketplacepulse.com/articles/specific-article-1",
    "https://www.eccang.com/article/xyz", 2)
samples["T15_t3_eccang_href"] = build(bad15, 8, 6)

# T16: 真实结构中两张卡同 URL（重复，check_duplicate_urls 应拦——此前在真实结构下静默空过）
real_dup = good_cards_real().replace(
    "https://www.ecomcrew.com/specific-post-2",
    "https://www.marketplacepulse.com/articles/specific-article-1", 2)
samples["T16_real_dup_url"] = build(real_dup, 8, 6)

# T17: 外部 <img src> 引用（A3 扩展检测应拦）
bad17_body = '<img src="https://external.example.com/pic.png">'
samples["T17_external_img"] = build(good_cards(), 8, 6, extra_body=bad17_body)

# ── 第三轮：B3 底部「→ 链接」按钮校验（2026-07-17） ──────
# T18: 某卡片缺失底部「→ 链接」按钮（B3 应拦截）
missing_bottom = re.sub(r'        <div class="card-link">.*?</div>', '', good_cards(), count=1)
samples["T18_missing_bottom_link"] = build(missing_bottom, 8, 6)

# T19: 底部「→ 链接」按钮指向根路径/首页（B3 应拦截，标题链接仍合规）
bottom_root = good_cards().replace(
    '<div class="card-link"><a href="https://www.marketplacepulse.com/articles/specific-article-1"',
    '<div class="card-link"><a href="https://www.example.com/"', 1)
samples["T19_bottom_root_path"] = build(bottom_root, 8, 6)

# T20: 底部「→ 链接」按钮为占位符 #（B3 应拦截）
bottom_hash = good_cards().replace(
    '<div class="card-link"><a href="https://www.marketplacepulse.com/articles/specific-article-1"',
    '<div class="card-link"><a href="#"', 1)
samples["T20_bottom_placeholder"] = build(bottom_hash, 8, 6)

# Fourth round: each case isolates a guard added for production reports.
samples["T21_invalid_calendar_date"] = build(
    good_cards().replace('class="card-date">2026-07-17<', 'class="card-date">2026-99-99<', 1), 8, 6)
samples["T22_missing_summary"] = build(
    good_cards().replace('<div class="card-summary">测试摘要</div>', '<div class="card-summary"></div>', 1), 8, 6)
samples["T23_source_pill_mismatch"] = build(good_cards(), 8, 6).replace(
    'class="source-pill active">Marketplace Pulse<', 'class="source-pill active">错误来源<', 1)
samples["T24_title_bottom_mismatch"] = build(
    good_cards().replace(
        '<div class="card-link"><a href="https://www.marketplacepulse.com/articles/specific-article-1"',
        '<div class="card-link"><a href="https://www.example.com/articles/other"', 1), 8, 6)
samples["T25_protocol_relative_external"] = build(
    good_cards(), 8, 6, extra_body='<img src="//external.example.com/pic.png">')
samples["T26_self_closing_card_link_baseline"] = re.sub(
    r'<div class="card-link"><a href="([^"]*)">→ 原文链接</a></div>',
    r'<a class="card-link" href="\1">→ 原文链接</a>',
    build(good_cards(), 8, 6))
for _name, _url in {
    "T27_summary_endpoint": "https://gs.amazon.cn/news/summary",
    "T28_announcements_endpoint": "https://sell.amazon.com/blog/announcements",
    "T29_list_endpoint": "https://example.org/list/",
    "T30_index_endpoint": "https://example.org/index.html",
}.items():
    samples[_name] = build(good_cards().replace(
        "https://www.marketplacepulse.com/articles/specific-article-1", _url, 2), 8, 6)
samples["T31_blog_slug_baseline"] = build(good_cards().replace(
    "https://www.ecomcrew.com/specific-post-2", "https://www.ecomcrew.com/blog/specific-post-2", 2), 8, 6)

# ── 第五轮：来源白名单（2026-10-20，v2.6.0）────────────────
# T32: 聚合/UGC 平台大数跨境（10100.com，2026-10-20 降 T3）作为最终链接 —— 白名单应拦
samples["T32_dashuju_aggregator"] = build(good_cards().replace(
    "https://www.marketplacepulse.com/articles/specific-article-1",
    "https://www.10100.com/news/215516", 2), 8, 6)

# T33: 聚合平台出海网（chwang.com，2026-10-20 降 T3）作为最终链接 —— 白名单应拦
samples["T33_chwang_aggregator"] = build(good_cards().replace(
    "https://www.marketplacepulse.com/articles/specific-article-1",
    "https://www.chwang.com/news/211211855206", 2), 8, 6)

# ── 第六轮：第四轮对抗审查实证样本收编（2026-10-20，v2.7.2）──
# T34: 卡片摘要内嵌未登记域链接（zhihu.com）—— 白名单须覆盖卡内全部 <a>（M1）
samples["T34_embedded_link_in_summary"] = build(good_cards().replace(
    '<div class="card-summary">测试摘要</div>',
    '<div class="card-summary">测试摘要 <a href="https://www.zhihu.com/question/123">参考</a></div>', 1), 8, 6)

# T35: embed 指向外部 CDN —— 外部依赖扫描须覆盖 embed（M2）
samples["T35_external_embed"] = build(
    good_cards(), 8, 6, extra_body='<embed src="https://external-cdn.example.com/x.swf">')

# T36: /article/ 无 slug 路径伪装具体文章 —— 聚合页判定须覆盖无 slug 集合（M4）
samples["T36_article_no_slug"] = build(good_cards().replace(
    "https://www.ecomcrew.com/specific-post-2", "https://www.ecomcrew.com/article/", 2), 8, 6)

# T37: 底部链接与标题仅差 trailing slash —— 归一化后比较，不应误报（L5）
samples["T37_trailing_slash_bottom_link"] = build(good_cards().replace(
    '<div class="card-link"><a href="https://www.ecomcrew.com/specific-post-2">',
    '<div class="card-link"><a href="https://www.ecomcrew.com/specific-post-2/">', 1), 8, 6)

# T38: 年度归档 /news/2026 伪装具体文章 —— 归档路径无 slug，须判聚合（M4 残留）
samples["T38_year_archive"] = build(good_cards().replace(
    "https://www.ecomcrew.com/specific-post-2", "https://www.ecomcrew.com/news/2026", 2), 8, 6)

# T39: ?page=N 翻页参数伪装具体文章 —— page= 无条件判聚合（M4 残留，原子句被无 slug 判定覆盖）
samples["T39_page_query"] = build(good_cards().replace(
    "https://www.ecomcrew.com/specific-post-2", "https://www.ecomcrew.com/updates?page=2", 2), 8, 6)

# ── 第七轮：v2.9.0 三项新检查（未来日期 / 审计分区 / P0 占比）──
# T40: 卡片日期晚于 Footer 生成日 —— 未来日期须拦（FUTURE_DATE）
samples["T40_future_card_date"] = build(
    good_cards().replace('class="card-date">2026-07-17<', 'class="card-date">2026-07-20<', 1), 8, 6)

# T41: 审计定档行的分区分布与报告实际分区卡片数不符 —— 须拦（AUDIT_ZONE_MISMATCH）
# 报告实际：cat-policy 2 / cat-reg 1 / cat-logistics 1 / cat-market 1 / cat-community 3
# 审计谎报：① 写 3 行（多 1），④ 写 0 行（少 1）
BAD_AUDIT_ZONE = """# 早报审计 · 2026-07-17

## 五、最终采用（8 条 / 6 来源）

[P0] ① 平台政策 | 卡片一 | 排序:当日
[P1] ① 平台政策 | 卡片二 | 排序:昨日
[P0] ① 平台政策 | 卡片三（实际不在①区） | 排序:当日
[P1] ② 合规监管 | 卡片四 | 排序:昨日
[P1] ③ 物流 | 卡片五 | 排序:昨日
[P1] ④ 行业 | 卡片六 | 排序:昨日
[社区] ⑤ 卖家社区 | 卡片七 | 可复用性
[社区] ⑤ 卖家社区 | 卡片八 | 具体度
"""
GOOD_AUDIT = """# 早报审计 · 2026-07-17

## 五、最终采用（8 条 / 6 来源）

[P0] ① 平台政策 | 卡片一 | 排序:当日
[P1] ① 平台政策 | 卡片二 | 排序:昨日
[P1] ② 合规监管 | 卡片三 | 排序:昨日
[P1] ③ 物流 | 卡片四 | 排序:昨日
[P1] ④ 行业 | 卡片五 | 排序:昨日
[社区] ⑤ 卖家社区 | 卡片六 | 可复用性
[社区] ⑤ 卖家社区 | 卡片七 | 具体度
[社区] ⑤ 卖家社区 | 卡片八 | 对应时点
"""
# 审计相关样本需要「项目根 + 早报审计/」布局，故单独落盘到 out/ 旁的 fixtures 目录
AUDIT_FIXTURES = {"T41_audit_zone_mismatch": BAD_AUDIT_ZONE, "T42_audit_zone_ok": GOOD_AUDIT}

# T43: P0 定档行超过卡片数 40%（8 卡 → 上限 3 行，写 5 行）—— 须拦（P0_RATIO）
P0_OVERFLOW_AUDIT = """# 早报审计 · 2026-07-17

## 五、最终采用（8 条 / 6 来源）

[P0] ① 平台政策 | 卡片一 | 排序:当日
[P0] ① 平台政策 | 卡片二 | 排序:当日
[P0] ② 合规监管 | 卡片三 | 排序:当日
[P0] ② 合规监管 | 卡片四 | 排序:当日
[P0] ③ 物流 | 卡片五 | 排序:当日
[P1] ④ 行业 | 卡片六 | 排序:昨日
[社区] ⑤ 卖家社区 | 卡片七 | 可复用性
[社区] ⑤ 卖家社区 | 卡片八 | 具体度
"""
AUDIT_FIXTURES["T43_p0_ratio_overflow"] = P0_OVERFLOW_AUDIT

for name, html in samples.items():
    with open(os.path.join(OUT, name + ".html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"generated: {name}.html")
# 审计 fixture 需要独立的项目布局（报告 + 早报审计/），供 run_adv.py 的 --audit-fixture 模式使用
FIX = os.path.join(os.path.dirname(OUT), "auditfix")
for name, audit in AUDIT_FIXTURES.items():
    d = os.path.join(FIX, name)
    os.makedirs(os.path.join(d, "早报审计"), exist_ok=True)
    with open(os.path.join(d, "跨境早报-2026-07-17.html"), "w", encoding="utf-8") as f:
        f.write(samples["T1_good_baseline"])
    with open(os.path.join(d, "早报审计", "2026-07-17.md"), "w", encoding="utf-8") as f:
        f.write(audit)
    print(f"generated fixture: {name}")

print(f"\n共 {len(samples)} 个样本 -> {OUT}")
