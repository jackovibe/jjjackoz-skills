#!/usr/bin/env python3
"""Production report structural checks (HTMLParser based).

Checks observable HTML invariants only. It does not claim URL reachability or
article truth; those belong to the collection and audit workflow. Exit 1 means
a structural gate failed.
"""
from __future__ import annotations
import re
import sys
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

# 有意内联，不参与总表解析：jintiankansha / toutiao 为历史对抗样本域，不入总表 T3。
_FORBIDDEN_SUPPLEMENT = ["jintiankansha.com", "toutiao.com"]
SECTION_ORDER = ["cat-policy", "cat-reg", "cat-logistics", "cat-market", "cat-community"]
SECTION_NAMES = {"cat-policy":"平台政策与费用", "cat-reg":"合规与监管", "cat-logistics":"物流与供应链", "cat-market":"行业与市场", "cat-community":"卖家社区"}
CHECK_CODES = {
    "空链接/占位链接":"EMPTY_LINK", "禁止域名":"FORBIDDEN_DOMAIN", "来源白名单":"SOURCE_NOT_IN_REGISTRY", "聚合页URL":"AGGREGATION_URL",
    "外部依赖":"EXTERNAL_DEPENDENCY", "日期格式":"INVALID_DATE", "卡片总数合理":"NO_CARDS",
    "重复URL":"DUPLICATE_URL", "Header条数匹配":"HEADER_CARD_COUNT", "Header来源数及来源pill":"SOURCE_PILLS",
    "卡片Meta顺序":"CARD_META", "卡片标题链接":"CARD_TITLE", "卡片事实摘要":"CARD_SUMMARY",
    "卡片影响与建议动作":"CARD_IMPACT", "本期口径声明":"SCOPE_NOTE", "临近节点时间线":"TIMELINE_SECTION",
    "卡片日期不晚于生成日":"FUTURE_DATE", "审计分区分布一致":"AUDIT_ZONE_MISMATCH", "P0占比上限":"P0_RATIO",
    "HTML结构完整性":"HTML_STRUCTURE", "分区存在与顺序":"SECTION_ORDER", "空分区占位及计数":"SECTION_CARDS",
    "知无不言链接域名一致性":"WEARESELLERS_DOMAIN", "卡片底部链接按钮及一致性":"CARD_BOTTOM_LINK",
    "卡片链接绝对https":"CARD_URL"
}

class Node:
    def __init__(self, tag="root", attrs=None, parent=None):
        self.tag, self.attrs, self.parent = tag, (attrs or {}), parent
        self.children = []
    @property
    def classes(self): return set(self.attrs.get("class", "").split())
    def descendants(self):
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.descendants()
    def text(self): return "".join(c if isinstance(c, str) else c.text() for c in self.children)

class ReportParser(HTMLParser):
    VOID = {"area","base","br","col","embed","hr","img","input","link","meta","param","source","track","wbr"}
    def __init__(self):
        super().__init__(convert_charrefs=True); self.root=Node(); self.stack=[self.root]; self.attrs_seen=[]
    def handle_starttag(self, tag, attrs):
        d={k.lower():(v or "") for k,v in attrs}; n=Node(tag.lower(),d,self.stack[-1]); self.stack[-1].children.append(n); self.attrs_seen.append((tag.lower(),d))
        if tag.lower() not in self.VOID: self.stack.append(n)
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in self.VOID and len(self.stack)>1: self.stack.pop()
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag.lower(): del self.stack[i:]; break
    def handle_data(self, data):
        if data: self.stack[-1].children.append(data)

def parse_html(html):
    p=ReportParser()
    try: p.feed(html); p.close()
    except Exception: pass
    return p
def _nodes(p, cls): return [n for n in p.root.descendants() if cls in n.classes]
def _cards(p): return [n for n in p.root.descendants() if n.tag=="div" and "card" in n.classes and "empty" not in n.classes]
def _links(n): return [x for x in n.descendants() if x.tag=="a"]
def _class_node(n, cls): return next((x for x in n.descendants() if cls in x.classes), None)
def _href(n): return n.attrs.get("href", "")
def _host(url):
    try: return (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError: return ""
def _canonical_url(url):
    """Normalize identity without discarding query parameters that may select an article."""
    try:
        s=urlsplit((url or "").strip())
        scheme=s.scheme.lower(); netloc=s.netloc.lower(); path=s.path or "/"
        if path != "/": path=path.rstrip("/") or "/"
        return urlunsplit((scheme, netloc, path, s.query, ""))
    except ValueError:
        return (url or "").strip()
def _header_node(p):
    return next((n for n in p.root.descendants() if n.tag=="header" or "header" in n.classes), None)
def _visible_text(n):
    if n is None: return ""
    return "".join(c if isinstance(c,str) else ("" if c.tag in {"script","style"} else _visible_text(c)) for c in n.children)

_REGISTRY_ERRORS=[]
def _registry_text(label):
    """Read the master registry; missing/empty/unparsable is a hard error (fail-closed)."""
    path=Path(__file__).resolve().parent.parent/"references"/"跨境资讯一手信息源总表.md"
    if not path.exists():
        _REGISTRY_ERRORS.append(f"{label}: 来源总表不存在 -> {path}"); return ""
    try: text=path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        _REGISTRY_ERRORS.append(f"{label}: 来源总表不可读 ({e})"); return ""
    if not text.strip():
        _REGISTRY_ERRORS.append(f"{label}: 来源总表为空 -> {path}"); return ""
    return text
def _section_by_tag(text, tag):
    """按小节标题中的等级标签（T0/T1/T3）取正文，**不依赖中文数字编号**。

    2026-10-20：原本用 `##\\s*[三四]、` 按编号定位，导致「总表插入新小节 →
    后续编号顺延 → validator 全面失效」。改为按标题里的 T0/T1/T3 标签定位，
    编号可自由重排，只要标签还在标题里就不断链。
    """
    m=re.search(r"^##[^\n]*\b"+tag+r"\b[^\n]*$.*?(?=\n##[^#]|\Z)", text, re.S|re.M)
    return m.group(0) if m else ""
def load_forbidden_domains():
    text=_registry_text("T3禁用域名")
    if not text: return []
    sec=_section_by_tag(text,"T3")
    ds=re.findall(r"`([a-z0-9.-]+\.[a-z]{2,})`",sec,re.I) if sec else []
    if not ds:
        _REGISTRY_ERRORS.append("T3禁用域名: 总表 T3 专区解析为空（检查小节标题是否含「T3」字样、域名是否反引号包裹）"); return []
    return list(dict.fromkeys(x.lower() for x in ds+_FORBIDDEN_SUPPLEMENT))
FORBIDDEN_DOMAINS=load_forbidden_domains()

# 来源白名单：最终链接域名必须 ∈ 总表登记的 T0/T1 来源；T2 中仅社区观察例外域
# （社区讨论本身是报道对象时可引用，见 SKILL.md 裁决表）可作为最终链接。
# 白名单兜底清单已删除：总表不可读时 fail-closed（见 _REGISTRY_ERRORS / main），
# 避免出现第二事实源与总表漂移。社区例外域有意内联，不进总表解析。
_COMMUNITY_EXCEPTION_DOMAINS = ["wearesellers.com", "reddit.com"]
def load_registry_whitelist():
    """Parse T0 + T1 registered domains from the master registry (by tag, not by section number)."""
    text=_registry_text("来源白名单")
    if not text: return list(_COMMUNITY_EXCEPTION_DOMAINS)
    domains=[]
    for tag in ("T0","T1"):
        sec=_section_by_tag(text,tag)
        if not sec: continue
        domains += [d.split("/")[0].lower() for d in re.findall(r"`([a-z0-9.-]+\.[a-z]{2,}(?:/[a-z0-9./-]*)?)`", sec, re.I)]
    # 反引号里也可能是文件名（如 `SKILL.md`），不是域名：按常见文件后缀剔除（2026-10-20）
    domains=[d for d in domains if not re.search(r"\.(md|txt|html?|pdf|json|ya?ml|csv)$", d)]
    if not domains:
        _REGISTRY_ERRORS.append("来源白名单: 总表 T0 / T1 专区解析为空（检查小节标题是否含「T0」「T1」字样、域名是否反引号包裹）")
        return list(_COMMUNITY_EXCEPTION_DOMAINS)
    return list(dict.fromkeys([*domains, *_COMMUNITY_EXCEPTION_DOMAINS]))
REGISTRY_WHITELIST=load_registry_whitelist()
def read_html(path): return Path(path).read_text(encoding="utf-8")
def count_cards(html): return len(_cards(parse_html(html)))

def check_empty_or_placeholder_links(html):
    p=parse_html(html); return [f"空链接或占位链接: href=\"{_href(a)}\"" for a in p.root.descendants() if a.tag=="a" and (not _href(a).strip() or _href(a).strip()=="#")]
def check_forbidden_domains(html):
    failures=[]; p=parse_html(html)
    for n in p.root.descendants():
        if n.tag in {"a","link"}: u=_href(n)
        elif n.tag in {"img","iframe","script","source","embed","audio","video","track"}: u=n.attrs.get("src","")
        elif n.tag=="object": u=n.attrs.get("data","")
        elif n.tag=="form": u=n.attrs.get("action","")
        else: continue
        h=_host(u)
        if any(h==d or h.endswith("."+d) for d in FORBIDDEN_DOMAINS): failures.append(f"包含禁止域名 {h}: href=\"{u}\"")
    return failures
def check_source_whitelist(html):
    """卡内全部 <a> 的域名必须 ∈ 总表登记来源（T0/T1）+ 社区观察例外域（2026-10-20 扩至卡内所有链接）。"""
    failures=[]
    for i,c in enumerate(_cards(parse_html(html)),1):
        urls=[_href(a) for a in _links(c) if _href(a).strip()]
        for u in urls:
            h=_host(u)
            if not h: continue
            if not any(h==d or h.endswith("."+d) for d in REGISTRY_WHITELIST):
                failures.append(f"卡片 {i} 最终链接域名未登记总表（T0/T1/社区例外）: {h} — href=\"{u}\"")
    return list(dict.fromkeys(failures))
_NO_SLUG_PATHS={"/blog","/articles","/article","/posts","/summary","/recalls","/announcements","/news","/search","/category","/tag","/archive","/releasenotes"}
def _is_aggregation(url):
    try:
        parts=urlsplit(url); path=parts.path.rstrip("/").lower(); query=parts.query
    except ValueError: return False
    if not path or path in _NO_SLUG_PATHS: return True
    if path.endswith(("/summary", "/announcements", "/list", "/index.html", "/index.php")): return True
    if re.fullmatch(r"/zb-\d+",path): return True
    # 分页路径 /page/2、?page=2 都是版块翻页，不是具体文章；page= 无条件判聚合（2026-10-20 修：原子句被上一行覆盖，等效失效）
    if re.search(r"/page/\d+$",path): return True
    if re.search(r"(?:^|&)page=\d+",query or "",re.I): return True
    # 年度/月度归档：/news/2026、/blog/2026/10 类路径无 slug，是归档页
    if re.search(r"^/(?:news|blog|articles|article|posts|press|updates)/\d{4}(?:/\d{1,2})?$",path): return True
    return bool(re.match(r"^/(?:category|tag|archive|search)(?:/|$)",path))
def check_aggregation_urls(html):
    failures=[]
    for n in parse_html(html).root.descendants():
        if n.tag=="a" and _is_aggregation(_href(n)): failures.append(f"可能的聚合页URL: href=\"{_href(n)}\"")
    return failures
def check_external_deps(html):
    failures=[]; p=parse_html(html)
    resource_tags={"link","script","img","iframe","source","video","audio","track","input","embed","object"}
    resource_attrs={"object":("data",)}
    def bad_resource_url(u):
        u=(u or "").strip()
        if not u or u.startswith(("data:","#")): return False
        return True
    for tag,a in p.attrs_seen:
        if tag in resource_tags:
            for key in ("src","href")+resource_attrs.get(tag,()):
                if key in a and bad_resource_url(a[key]):
                    failures.append(f"单文件存在资源依赖: <{tag} {key}=\"{a[key]}\">")
            if "srcset" in a:
                # Keep data: payload commas inside one candidate; descriptors end at whitespace.
                candidates=re.findall(r"(?:^|,\s*)(data:[^\s]+|[^,\s]+)", a["srcset"])
                for u in candidates:
                    if bad_resource_url(u): failures.append(f"单文件存在 srcset 资源依赖: {u}")
        elif tag=="form":
            # 表单 action 提交到外部端点即为资源依赖；空值或本页片段(#)不算。
            action=(a.get("action") or "").strip()
            if bad_resource_url(action): failures.append(f"单文件存在资源依赖: <form action=\"{action}\">")
        style=a.get("style","")
        for u in re.findall(r"url\(\s*[\"']?([^\"')\s]+)", style, re.I):
            if bad_resource_url(u): failures.append(f"内联style存在资源依赖: {u}")
    # CSS URLs can live in a style element rather than a style attribute.
    for n in p.root.descendants():
        if n.tag != "style": continue
        css=n.text()
        if re.search(r"@import\s+",css,re.I): failures.append("发现 CSS @import 依赖")
        for u in re.findall(r"url\(\s*[\"']?([^\"')\s]+)", css, re.I):
            if bad_resource_url(u): failures.append(f"style 块存在资源依赖: {u}")
    return failures
def check_date_format(html):
    failures=[]; ds=[n.text().strip() for n in _nodes(parse_html(html),"card-date")]
    if not ds: return ["未找到任何 card-date"]
    for d in ds:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}",d): raise ValueError
            date.fromisoformat(d)
        except ValueError: failures.append(f"日期格式或日历日期不正确（应为 YYYY-MM-DD）: {d!r}")
    return failures
def check_total_cards(html): return [] if count_cards(html) else ["未找到任何 .card 卡片（早报不应为空）"]
def _card_title_hrefs(html):
    out=[]
    for c in _cards(parse_html(html)):
        a=next((x for x in _links(c) if "card-title" in x.classes),None)
        if a: out.append(_href(a)); continue
        box=_class_node(c,"card-title"); a=next((x for x in _links(box)),None) if box else None
        if a: out.append(_href(a))
    return out
def check_duplicate_urls(html):
    seen=set(); failures=[]
    for u in _card_title_hrefs(html):
        canonical=_canonical_url(u)
        if canonical in seen: failures.append(f"重复URL: {u}")
        seen.add(canonical)
    return failures
def check_header_count_matches_cards(html):
    p=parse_html(html); header=_header_node(p); m=re.search(r"精选\s*(\d+)\s*条",_visible_text(header) if header else "")
    if not m: return ["Header 中未找到'精选 X 条'"]
    n=count_cards(html); return [] if int(m.group(1))==n else [f"Header 声称精选 {m.group(1)} 条，但实际有 {n} 张卡片"]
def check_source_count_in_header(html):
    p=parse_html(html); header=_header_node(p); m=re.search(r"采用\s*(\d+)\s*个独立来源",_visible_text(header) if header else ""); failures=[]
    if not m:
        if re.search(r"覆盖\s*\d+\s*个",_visible_text(header) if header else ""): return ["Header 仍在使用旧格式'覆盖X个渠道'，应改为'采用Y个独立来源'"]
        return ["Header 中未找到来源数量（应为'采用X个独立来源'）"]
    bars=[n for n in p.root.descendants() if "source-bar" in n.classes or "channels-bar" in n.classes]
    pills=[n for b in bars for n in b.descendants() if n.tag=="span" and "source-pill" in n.classes]
    card_sources=[(_class_node(c,"card-source").text().strip() if _class_node(c,"card-source") else "") for c in _cards(p)]
    unique_cards=set(card_sources); pill_text=[n.text().strip() for n in pills]; unique_pills=set(pill_text)
    if any(not s for s in card_sources): failures.append("存在卡片来源标签为空")
    if int(m.group(1))!=len(unique_cards): failures.append(f"Header 声称 {m.group(1)} 个来源，但卡片实际有 {len(unique_cards)} 个独立来源")
    if not bars: failures.append("缺少来源状态条容器")
    if len(pill_text)!=len(unique_pills): failures.append("来源状态条存在重复 pill")
    if len(pill_text)!=len(unique_cards): failures.append(f"来源 pill 数={len(pill_text)}，实际独立来源数={len(unique_cards)}")
    cs=unique_cards; ps=unique_pills
    if cs!=ps: failures.append(f"来源状态条与卡片来源不一致: 卡片={sorted(cs)}，pill={sorted(ps)}")
    return failures
def check_card_meta_order(html):
    failures=[]
    for i,c in enumerate(_cards(parse_html(html)),1):
        m=_class_node(c,"card-meta")
        if not m:
            failures.append(f"卡片 {i} 缺少 card-meta")
            continue
        spans=[x for x in m.descendants() if x.tag=="span"]; names=[x.classes for x in spans]; di=next((j for j,s in enumerate(names) if "card-date" in s),-1); si=next((j for j,s in enumerate(names) if "card-source" in s),-1)
        if di<0 or si<0: failures.append(f"卡片 {i} 缺少 card-date 或 card-source")
        elif di>si: failures.append(f"卡片 {i} meta 顺序错误: date 应在 source 之前")
    return failures

def check_card_title_link_present(html):
    failures=[]
    for i,c in enumerate(_cards(parse_html(html)),1):
        a=_title_anchor(c)
        if a is None or not _href(a).strip(): failures.append(f"卡片 {i} 缺少标题链接")
        elif not re.sub(r"\s+", "", _visible_text(a)): failures.append(f"卡片 {i} 标题文字为空")
    return failures
def check_card_summary_content(html):
    failures=[]
    for i,c in enumerate(_cards(parse_html(html)),1):
        s=_class_node(c,"card-summary")
        if s is None or not re.sub(r"\s+","",s.text()): failures.append(f"卡片 {i} 缺少事实摘要")
    return failures
_IMP_RE=re.compile(r"影响[：:]\s*\S.{3,}",re.S)
_ACT_RE=re.compile(r"建议动作[：:]\s*\S.{3,}",re.S)
def check_card_impact_action(html):
    """v2.8.0：每卡必带 fold 折叠区，内含「影响：」与「建议动作：」两段非空内容。"""
    failures=[]
    for i,c in enumerate(_cards(parse_html(html)),1):
        folds=[n for n in c.descendants() if n.tag=="details" and "fold" in n.classes]
        if len(folds)!=1:
            failures.append(f"卡片 {i} 缺少或有多个 <details class=fold> 影响折叠区（应恰有 1 个）"); continue
        body=_class_node(folds[0],"fold-body")
        if body is None:
            failures.append(f"卡片 {i} fold 折叠区缺少 fold-body"); continue
        txt=_visible_text(body)
        if not _IMP_RE.search(txt): failures.append(f"卡片 {i} 折叠区缺少「影响：」及后续说明")
        if not _ACT_RE.search(txt): failures.append(f"卡片 {i} 折叠区缺少「建议动作：」及后续说明")
    return failures
def check_scope_note(html):
    """v2.8.0：nav-bar 后必须有「本期口径」声明块，含收录窗口日期。"""
    p=parse_html(html); notes=[n for n in p.root.descendants() if "scope-note" in n.classes]
    if not notes: return ["缺少本期口径声明块 <div class=\"scope-note\">"]
    if len(notes)>1: return [f"scope-note 声明块应只有 1 个，实际 {len(notes)} 个"]
    txt=_visible_text(notes[0])
    failures=[]
    if "本期口径" not in txt: failures.append("scope-note 未包含「本期口径」字样")
    if not re.search(r"\d{4}-\d{2}-\d{2}",txt): failures.append("scope-note 未标注收录窗口日期（YYYY-MM-DD）")
    if len(re.sub(r"\s+","",txt))<30: failures.append("scope-note 内容过短，未说明收录窗口/口径")
    return failures
def check_timeline_section(html):
    """v2.8.0：趋势总结后须有临近节点时间线容器；tl-item 须有合法日期与 https 文章页链接。"""
    p=parse_html(html); tls=[n for n in p.root.descendants() if "timeline-section" in n.classes]
    if not tls: return ["缺少临近节点提醒时间线 <div class=\"timeline-section\">"]
    if len(tls)>1: return [f"timeline-section 容器应只有 1 个，实际 {len(tls)} 个"]
    sec=tls[0]; failures=[]
    items=[n for n in sec.descendants() if n.tag=="div" and "tl-item" in n.classes]
    if not items:
        if not re.sub(r"\s+","",_visible_text(sec)): failures.append("timeline-section 为空且无占位说明")
        return failures
    for i,it in enumerate(items,1):
        d=_class_node(it,"tl-date")
        if d is None:
            failures.append(f"时间线条目 {i} 缺少 tl-date"); continue
        ds=d.text().strip()
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}",ds): raise ValueError
            date.fromisoformat(ds)
        except ValueError: failures.append(f"时间线条目 {i} 日期格式或日历日期不正确: {ds!r}")
        links=[a for a in _links(it) if _href(a).strip()]
        if not links:
            failures.append(f"时间线条目 {i} 无来源链接"); continue
        for a in links:
            u=_href(a)
            if not u.startswith("https://") or not _host(u):
                failures.append(f"时间线条目 {i} 链接非绝对 https: {u}"); continue
            if _is_aggregation(u) or not urlsplit(u).path.strip("/"):
                failures.append(f"时间线条目 {i} 链接不是具体文章页: {u}")
    return failures
# 审计定档行格式：[P0]/[P1]/[P2]/[社区] + 分区符号（①②③④⑤）
_TIER_ZONE_RE = re.compile(r"^\s*\[(P0|P1|P2|社区)\]\s*([①②③④⑤])", re.M)
_ZONE_BY_SYM = {"①": "cat-policy", "②": "cat-reg", "③": "cat-logistics", "④": "cat-market", "⑤": "cat-community"}
_P0_MAX_RATIO = 0.4

def _footer_run_date(p):
    """报告生成日（Footer「本期资讯生成于 YYYY-MM-DD HH:mm」）；取不到返回 None。"""
    for n in p.root.descendants():
        if n.tag == "footer":
            m = re.search(r"本期资讯生成于\s*(\d{4}-\d{2}-\d{2})", _visible_text(n))
            if m: return date.fromisoformat(m.group(1))
    return None

def check_card_date_not_future(html):
    """卡片日期不得晚于报告生成日。基准取 Footer 生成日而非「今天」——
    历史期次复跑时「今天」会持续前移，用它会把正常旧稿判成未来日期。"""
    p=parse_html(html); failures=[]
    run=_footer_run_date(p)
    if run is None:
        return []  # 无 Footer 生成日时不做判定，交给 HTML_STRUCTURE 检查 Footer 存在性
    for i,c in enumerate(_cards(p),1):
        d=_class_node(c,"card-date")
        if d is None: continue
        try: cd=date.fromisoformat(d.text().strip())
        except ValueError: continue  # 格式错误由 check_date_format 负责
        if cd>run: failures.append(f"卡片 {i} 日期 {cd.isoformat()} 晚于报告生成日 {run.isoformat()}")
    return failures

def check_audit_zone_distribution(html, audit_text):
    """审计定档行的分区分布必须与报告实际分区卡片数一致。
    只对含定档行的审计生效（无定档行由 AUDIT_TIER_LINES 报错）。"""
    rows=_TIER_ZONE_RE.findall(audit_text or "")
    if not rows: return []
    p=parse_html(html); actual={}
    for sec in _nodes(p,"section"):
        cat=next((x for x in sec.classes if x in SECTION_ORDER),None)
        if not cat: continue
        actual[cat]=len([n for n in sec.descendants() if n.tag=="div" and "card" in n.classes and "empty" not in n.classes])
    claimed={}
    for tier,sym in rows:
        cat=_ZONE_BY_SYM.get(sym)
        if not cat: continue
        claimed[cat]=claimed.get(cat,0)+1
    failures=[]
    for cat in SECTION_ORDER:
        a=actual.get(cat,0); c=claimed.get(cat,0)
        if a!=c: failures.append(f"审计定档行分区分布与报告不符: {SECTION_NAMES[cat]} 审计 {c} 行 / 报告 {a} 张卡片")
    return failures

def check_p0_ratio(html, audit_text):
    """单期 P0 不超过卡片数的 40%（向下取整，最少 1 条）。"""
    rows=_TIER_ZONE_RE.findall(audit_text or "")
    if not rows: return []
    n_cards=count_cards(html)
    n_p0=sum(1 for tier,_ in rows if tier=="P0")
    limit=max(1, int(n_cards*_P0_MAX_RATIO))
    if n_p0>limit:
        return [f"P0 定档行 {n_p0} 条，超过上限 {limit} 条（卡片数 {n_cards} × {_P0_MAX_RATIO:.0%}，最少 1 条）"]
    return []

def check_html_structure(html):
    p=parse_html(html); failures=[]
    if "跨境电商每日早报" not in p.root.text(): failures.append("缺少关键结构: 标题")
    if not _nodes(p,"trends-section"): failures.append("缺少关键结构: 趋势总结")
    if not re.search(r"本期资讯生成于|以上资讯",p.root.text()): failures.append("缺少关键结构: Footer")
    if not (_nodes(p,"channels-bar") or _nodes(p,"source-bar")): failures.append("缺少关键结构: 来源状态条")
    if not _nodes(p,"section"): failures.append("缺少关键结构: 主题分区")
    return failures
def check_sections_order(html):
    cats=[]
    for n in _nodes(parse_html(html),"section"):
        cats += [x for x in n.classes if x in SECTION_ORDER]
    failures=[]
    if set(cats)!=set(SECTION_ORDER): failures.append(f"缺少固定分区: {'、'.join(SECTION_NAMES[x] for x in SECTION_ORDER if x not in cats)}")
    if cats!=SECTION_ORDER: failures.append(f"分区顺序错误: 实际 {cats}，期望 {SECTION_ORDER}")
    return failures
def check_empty_sections(html):
    failures=[]; p=parse_html(html); sections=[s for s in _nodes(p,"section") if any(x in SECTION_ORDER for x in s.classes)]; all_cards=_cards(p); section_card_total=0
    for c in all_cards:
        owners=[]; cur=c.parent
        while cur is not None:
            if "section" in cur.classes and any(x in SECTION_ORDER for x in cur.classes): owners.append(cur)
            cur=cur.parent
        if len(owners)!=1: failures.append("卡片必须恰好归属一个允许主题分区")
    for sec in sections:
        cat=next((x for x in sec.classes if x in SECTION_ORDER),None)
        if not cat: continue
        cards=[n for n in sec.descendants() if n.tag=="div" and "card" in n.classes and "empty" not in n.classes]; empty=any("empty" in n.classes for n in sec.descendants()); count_node=_class_node(sec,"count"); m=re.search(r"(\d+)\s*条",count_node.text()) if count_node else None; count=int(m.group(1)) if m else None
        section_card_total += len(cards)
        if not cards and not empty: failures.append(f"分区 {SECTION_NAMES[cat]} 既无卡片也无空占位")
        if not cards and empty and count!=0: failures.append(f"分区 {SECTION_NAMES[cat]} 为空但 count 显示 {count} 条（应为 0）")
        if cards and empty: failures.append(f"分区 {SECTION_NAMES[cat]} 同时存在卡片和空占位")
        if cards and count!=len(cards): failures.append(f"分区 {SECTION_NAMES[cat]} count={count}，实际卡片={len(cards)}")
    if section_card_total != len(all_cards): failures.append(f"分区卡片总数={section_card_total} 与全局卡片数={len(all_cards)} 不一致")
    return failures
def check_wearesellers_link_domain(html):
    failures=[]
    for i,c in enumerate(_cards(parse_html(html)),1):
        s=_class_node(c,"card-source")
        if not s or "知无不言" not in s.text(): continue
        u=_title_href(c); h=_host(u)
        if h!="wearesellers.com" and not h.endswith(".wearesellers.com"): failures.append(f"知无不言卡片 {i} 链接域名非 wearesellers.com: {u}")
    return failures
def _title_href(c):
    a=_title_anchor(c)
    return _href(a) if a else ""
def _title_anchor(c):
    a=next((x for x in _links(c) if "card-title" in x.classes),None)
    if a: return a
    box=_class_node(c,"card-title")
    return next((x for x in _links(box)),None) if box else None
def check_card_bottom_link(html):
    failures=[]
    for i,c in enumerate(_cards(parse_html(html)),1):
        box=_class_node(c,"card-link")
        candidates = ([box] if box and box.tag == "a" else _links(box)) if box else []
        b=next((a for a in candidates if "链接" in re.sub(r"\s+","",a.text())),None)
        if not b: failures.append(f"卡片 {i} 缺少底部「→ 链接」按钮"); continue
        u=_href(b)
        if not u or u=="#": failures.append(f"卡片 {i} 底部链接为空或占位链接: {u}"); continue
        if not u.startswith("https://") or not _host(u): failures.append(f"卡片 {i} 底部链接非绝对 https 链接: {u}"); continue
        if _is_aggregation(u) or not urlsplit(u).path.strip("/"): failures.append(f"卡片 {i} 底部链接不是具体文章页: {u}")
        if _title_href(c) and _canonical_url(u)!=_canonical_url(_title_href(c)): failures.append(f"卡片 {i} 标题链接与底部按钮链接不一致")
    return failures
def check_card_links_absolute_https(html):
    failures=[]
    for u in _card_title_hrefs(html):
        if not u.startswith("https://") or not _host(u): failures.append(f"卡片链接非绝对 https 链接: {u}"); continue
        if _is_aggregation(u) or not urlsplit(u).path.strip("/"): failures.append(f"卡片链接疑似列表/聚合页: {u}")
    return failures
def _resolve_project_root(report_path, explicit_root=None):
    report=Path(report_path).resolve()
    if explicit_root:
        root=Path(explicit_root).resolve()
        try: report.relative_to(root)
        except ValueError: return None
        return root
    parent=report.parent
    # Normal production report lives directly under project root.
    if (parent/"早报审计").is_dir(): return parent
    # Archived report may live exactly under project/归档/YYYY-MM/.
    if parent.name and re.fullmatch(r"\d{4}-\d{2}", parent.name) and parent.parent.name=="归档":
        root=parent.parent.parent
        return root if (root/"早报审计").is_dir() else None
    return None
def read_audit_text(html_path, test_mode=False, project_root=None):
    """返回 (审计文本, 审计文件路径)；不适用时返回 (None, None)。"""
    m=re.match(r"跨境早报-(\d{4}-\d{2}-\d{2})\.html$",Path(html_path).name)
    if not m: return (None, None)
    d=m.group(1); root=_resolve_project_root(html_path, project_root)
    p=(root/"早报审计"/f"{d}.md") if root else None
    if p is None or not p.exists(): return (None, p)
    return (p.read_text(encoding="utf-8"), p)

def check_audit_record_exists(html_path, test_mode=False, project_root=None, html=""):
    m=re.match(r"跨境早报-(\d{4}-\d{2}-\d{2})\.html$",Path(html_path).name)
    if not m:
        return [] if test_mode else ["非标准生产报告命名；如为测试样本请显式传入 --test-mode"]
    d=m.group(1); root=_resolve_project_root(html_path, project_root)
    p=(root/"早报审计"/f"{d}.md") if root else None
    if p is None or not p.exists(): return [f"当日审计记录缺失或项目根未确认: 早报审计/{d}.md（生产报告检查）"]
    text=p.read_text(encoding="utf-8")
    if len(text.strip())<50: return [f"当日审计记录疑似空文件: {p}"]
    # 内容门禁结构兜底（L2）：审计必须按 selection-score §12 格式为每张入选卡片留一行档位记录，
    # [P0]/[P1]/[P2]/[社区] 行数须等于报告卡片数，防止"审计只有流水账、定档环节被跳过"。
    tier_lines=re.findall(r"^\s*\[(P0|P1|P2|社区)\]",text,re.M)
    n_cards=count_cards(html) if html else 0
    if not tier_lines: return [f"审计记录无任何定档行（[P0]/[P1]/[P2]/[社区]），内容价值门禁未留痕: {p}"]
    if len(tier_lines)!=n_cards: return [f"审计定档行数={len(tier_lines)} 与报告卡片数={n_cards} 不一致（每张卡片须有一行 [P0]/[P1]/[P2]/[社区] 记录）: {p}"]
    return []

def main():
    if len(sys.argv)<2 or not Path(sys.argv[1]).exists(): print("用法: python validate-report.py <path/to/跨境早报-YYYY-MM-DD.html> [--test-mode] [--project-root ROOT]"); sys.exit(1)
    if _REGISTRY_ERRORS:
        # fail-closed：宁可不给结论，也不启用内联兜底造成第二事实源漂移（M3）
        print("❌ [来源总表] code=REGISTRY_UNREADABLE")
        [print(f"   - {e}") for e in _REGISTRY_ERRORS]
        sys.exit(1)
    test_mode="--test-mode" in sys.argv[2:]; path=sys.argv[1]; html=read_html(path); checks=[("空链接/占位链接",check_empty_or_placeholder_links),("禁止域名",check_forbidden_domains),("来源白名单",check_source_whitelist),("聚合页URL",check_aggregation_urls),("外部依赖",check_external_deps),("日期格式",check_date_format),("卡片总数合理",check_total_cards),("重复URL",check_duplicate_urls),("Header条数匹配",check_header_count_matches_cards),("Header来源数及来源pill",check_source_count_in_header),("卡片Meta顺序",check_card_meta_order),("卡片标题链接",check_card_title_link_present),("卡片事实摘要",check_card_summary_content),("卡片日期不晚于生成日",check_card_date_not_future),("卡片影响与建议动作",check_card_impact_action),("HTML结构完整性",check_html_structure),("分区存在与顺序",check_sections_order),("空分区占位及计数",check_empty_sections),("本期口径声明",check_scope_note),("临近节点时间线",check_timeline_section),("知无不言链接域名一致性",check_wearesellers_link_domain),("卡片底部链接按钮及一致性",check_card_bottom_link),("卡片链接绝对https",check_card_links_absolute_https)]
    project_root=None
    if "--project-root" in sys.argv[2:]:
        i=sys.argv.index("--project-root")
        if i+1>=len(sys.argv): print("--project-root 需要路径"); sys.exit(1)
        project_root=sys.argv[i+1]
    failed=[]
    for name,fn in checks:
        errs=fn(html)
        if errs: print(f"❌ [{name}] code={CHECK_CODES.get(name,'STRUCTURE_ERROR')}"); [print(f"   - {e}") for e in errs]; failed.extend(errs)
        else: print(f"✅ [{name}]")
    errs=check_audit_record_exists(path, test_mode, project_root, html)
    if errs:
        code="AUDIT_TIER_LINES" if any("定档" in e for e in errs) else "AUDIT_RECORD_MISSING"
        print(f"❌ [生产报告审计记录] code={code}"); [print(f"   - {e}") for e in errs]; failed.extend(errs)
    else: print("✅ [生产报告审计记录]")
    # 审计相关的两项交叉检查：需要审计正文，故放在审计存在性检查之后
    audit_text,_=read_audit_text(path, test_mode, project_root)
    for name,fn in (("审计分区分布一致",check_audit_zone_distribution),("P0占比上限",check_p0_ratio)):
        errs=fn(html, audit_text)
        if errs: print(f"❌ [{name}] code={CHECK_CODES.get(name,'STRUCTURE_ERROR')}"); [print(f"   - {e}") for e in errs]; failed.extend(errs)
        else: print(f"✅ [{name}]")
    print("\n"+(f"⚠️ 共发现 {len(failed)} 项问题" if failed else "✅ 全部结构检查通过")); sys.exit(1 if failed else 0)
if __name__=="__main__": main()
