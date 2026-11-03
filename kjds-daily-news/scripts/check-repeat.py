#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文章级跨期查重（用户定策 2026-11-03）。

核心口径：**判重只看「文章」，不看「话题」**。
  - 禁止：同一篇文章二次上版（同 canonical URL，或同域同 slug）→ 报 DUPLICATE_URL，硬淘汰
  - 允许：同一话题换一篇新文章、换一个角度 → 照收，不因「话题报过 N 次」降档

用法：
    python scripts/check-repeat.py candidates-2026-11-03.json
    python scripts/check-repeat.py candidates-2026-11-03.json --project "D:/workbuddy space/跨境圈"
    python scripts/check-repeat.py candidates-2026-11-03.json --days 30      # 只看近 30 期
    python scripts/check-repeat.py candidates-2026-11-03.json --json

退出码：0 = 无重复；1 = 命中重复；2 = 参数/文件错误。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "fbclid", "gclid", "spm", "ref", "source"}

RE_CARD_HREF = re.compile(r'class="card-title".{0,400}?href="([^"]+)"', re.S)
RE_VALID_URL = re.compile(r"^https?://", re.I)


def norm_url(u: str) -> str:
    """归一化：小写 host、去 www.、去尾斜杠、去 fragment、丢跟踪参数。"""
    u = (u or "").strip()
    if not RE_VALID_URL.match(u):
        return ""
    try:
        s = urlsplit(u)
    except ValueError:
        return ""
    host = (s.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/+$", "", s.path or "/") or "/"
    q = [(k, v) for k, v in
         (p.split("=", 1) if "=" in p else (p, "") for p in (s.query or "").split("&") if p)
         if k.lower() not in TRACKING]
    query = "&".join(f"{k}={v}" if v else k for k, v in q)
    return urlunsplit((s.scheme.lower() or "https", host, path, query, ""))


def slug_of(nurl: str) -> str:
    """取路径最后一段做镜像线索（跨域同 slug 只作 WARN，不作判死）。"""
    p = urlsplit(nurl).path.strip("/")
    last = p.split("/")[-1].lower()
    return last if len(last) >= 12 and re.search(r"[a-z]", last) else ""


def date_of_name(name: str) -> str:
    m = re.search(r"(20\d{2}-\d{2}-\d{2})", name)
    return m.group(1) if m else ""


def load_candidates(path: Path):
    """返回 [(zone, title, url, tier)]，兼容本期 candidates 结构。"""
    d = json.loads(path.read_text(encoding="utf-8"))
    out = []
    if isinstance(d, dict) and "sections" in d:
        for zone, sec in d["sections"].items():
            for c in sec.get("cards", []):
                out.append((zone, c.get("title", ""), c.get("url", ""), c.get("tier", "")))
    elif isinstance(d, list):
        for c in d:
            out.append((c.get("zone", ""), c.get("title", ""), c.get("url", ""), c.get("tier", "")))
    return out


def collect_history(project: Path, skip_dates: set[str], days: int | None):
    """从往期报告 HTML 与 candidates JSON 收集已用文章。

    返回 {norm_url: [(日期, 来源文件, 标题)]}
    """
    hist: dict[str, list[tuple[str, str, str]]] = {}
    reports = sorted(project.glob("跨境早报-*.html")) + sorted(project.glob("归档/**/跨境早报-*.html"))
    for f in reports:
        d = date_of_name(f.name)
        if d and d in skip_dates:
            continue
        try:
            html = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for raw in RE_CARD_HREF.findall(html):
            nu = norm_url(raw)
            if nu:
                hist.setdefault(nu, []).append((d, f.name, ""))
    for f in sorted(project.glob("candidates-*.json")) + sorted(project.glob("归档/**/candidates-*.json")):
        d = date_of_name(f.name)
        if d and d in skip_dates:
            continue
        try:
            for _z, t, u, _tier in load_candidates(f):
                nu = norm_url(u)
                if nu:
                    hist.setdefault(nu, []).append((d, f.name, t))
        except (OSError, json.JSONDecodeError):
            continue
    if days:
        cut = (dt.date.today() - dt.timedelta(days=days)).isoformat()
        hist = {k: [x for x in v if not x[0] or x[0] >= cut] for k, v in hist.items()}
        hist = {k: v for k, v in hist.items() if v}
    return hist


def main() -> int:
    ap = argparse.ArgumentParser(description="文章级跨期查重（同一篇文章不得二次上版）")
    ap.add_argument("candidates", help="本期 candidates-YYYY-MM-DD.json")
    ap.add_argument("--project", default=".", help="项目根目录（默认当前目录）")
    ap.add_argument("--days", type=int, default=None, help="只比最近 N 天（默认全历史）")
    ap.add_argument("--json", action="store_true", help="只输出机器可读 JSON")
    a = ap.parse_args()

    cpath = Path(a.candidates)
    if not cpath.is_file():
        print(f"[ERR] candidates 文件不存在: {cpath}", file=sys.stderr)
        return 2
    project = Path(a.project).resolve()
    if not project.is_dir():
        print(f"[ERR] 项目目录不存在: {project}", file=sys.stderr)
        return 2

    try:
        cards = load_candidates(cpath)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[ERR] candidates 解析失败: {e}", file=sys.stderr)
        return 2
    if not cards:
        print("[ERR] candidates 里没有卡片", file=sys.stderr)
        return 2

    run_date = date_of_name(cpath.name)
    hist = collect_history(project, {run_date} if run_date else set(), a.days)

    # 本期内部重复
    seen: dict[str, str] = {}
    internal = []
    # 跨期重复
    cross = []
    # 跨域同 slug（镜像可疑）
    warns = []
    slugs = {slug_of(u): u for u in hist if slug_of(u)}

    for zone, title, url, tier in cards:
        nu = norm_url(url)
        if not nu:
            continue
        if nu in seen:
            internal.append({"url": nu, "title": title, "first_title": seen[nu], "zone": zone})
            continue
        seen[nu] = title
        if nu in hist:
            cross.append({
                "url": nu, "title": title, "zone": zone, "tier": tier,
                "issues": sorted({x[0] for x in hist[nu] if x[0]}),
                "files": sorted({x[1] for x in hist[nu]})[:5],
            })
        else:
            sl = slug_of(nu)
            if sl and sl in slugs and slugs[sl] != nu:
                warns.append({"url": nu, "title": title, "slug": sl, "other": slugs[sl]})

    result = {
        "candidates": str(cpath),
        "run_date": run_date,
        "cards": len(cards),
        "history_urls": len(hist),
        "internal_duplicates": internal,
        "cross_issue_duplicates": cross,
        "slug_mirror_warnings": warns,
        "pass": not internal and not cross,
    }

    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0 if result["pass"] else 1

    print(f"本期卡片 {len(cards)} 条 · 往期已用文章 {len(hist)} 篇"
          + (f" · 比对区间近 {a.days} 天" if a.days else " · 全历史"))
    if internal:
        print("\n❌ 本期内部重复（同一篇出现两次）")
        for x in internal:
            print(f"   - {x['title'][:48]} ← 与「{x['first_title'][:32]}」同链接")
            print(f"     {x['url']}")
    if cross:
        print("\n❌ 跨期重复：同一篇文章往期已上版（DUPLICATE_URL，硬淘汰）")
        for x in cross:
            print(f"   - [{x['zone']}/{x['tier']}] {x['title'][:48]}")
            print(f"     {x['url']}")
            print(f"     往期: {', '.join(x['issues']) or '?'} | {', '.join(x['files'])}")
    if warns:
        print("\n⚠️ 跨域同 slug（疑似镜像/改写版，人工确认，不自动淘汰）")
        for x in warns:
            print(f"   - {x['title'][:44]}")
            print(f"     {x['url']}  ≈  {x['other']}")
    if result["pass"]:
        print("\n✅ 无文章级重复：所有卡片均为往期未用过的新文章")
        if warns:
            print("   （上方 WARN 需人工确认是否同一篇的镜像）")
        return 0
    print("\n→ 命中重复的卡片按 DUPLICATE_URL 淘汰并回填该区缺口（见 SKILL.md 步骤 3.1）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
