#!/usr/bin/env python3
"""Independent v2.4.1 mutation regression; no network and no production writes."""
from __future__ import annotations
import re, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALIDATOR = HERE.parent / "validate-report.py"
BASELINE = HERE / "out" / "T1_good_baseline.html"

def run(html: str, production: bool = False, parent_audit: bool = False):
    with tempfile.TemporaryDirectory(prefix="kjds-v241-") as td:
        root = Path(td) / "project"
        root.mkdir()
        report = root / ("跨境早报-2026-07-17.html" if production else "sample.html")
        report.write_text(html, encoding="utf-8")
        if parent_audit:
            (Path(td) / "早报审计").mkdir()
            (Path(td) / "早报审计" / "2026-07-17.md").write_text("other project audit " * 20, encoding="utf-8")
        args = [sys.executable, str(VALIDATOR), str(report)]
        if not production: args.append("--test-mode")
        r = subprocess.run(args, capture_output=True, text=True)
        return r

def expect_case(name, html, code):
    r = run(html)
    codes = set(re.findall(r"^❌ \[[^\n]+\] code=([A-Z0-9_]+)$", r.stdout, re.M))
    if r.returncode == 0 or code not in codes:
        raise AssertionError(f"{name}: rc={r.returncode}, codes={sorted(codes)}\n{r.stdout}")

def main():
    base = BASELINE.read_text(encoding="utf-8")
    if run(base).returncode != 0:
        raise AssertionError("independent baseline did not pass")
    # Keep this list independent from the production advtest EXPECT table.
    cases = {
        "no_source_pills": (re.sub(r"\s*<span class=\"source-pill[^>]*>.*?</span>", "", base, flags=re.S), "SOURCE_PILLS"),
        "pills_outside_container": (base.replace('class="channels-bar"', 'class="channels-wrap"', 1), "SOURCE_PILLS"),
        "orphan_card": (base.replace('<section class="section cat-policy">', '<section class="section">', 1), "SECTION_CARDS"),
        "nonempty_with_empty": (base.replace('</section>', '<div class="empty">今日暂无</div></section>', 1), "SECTION_CARDS"),
        "header_comment_spoof": (base.replace('<p>精选 8 条 · 采用 6 个独立来源</p>', '<!-- 精选 8 条 · 采用 6 个独立来源 --><p>精选 999 条 · 采用 999 个独立来源</p>', 1), "HEADER_CARD_COUNT"),
        "external_srcset": (base.replace('</header>', '</header><img srcset="https://example.org/a.png 1x">', 1), "EXTERNAL_DEPENDENCY"),
        "relative_stylesheet": (base.replace('</head>', '<link rel="stylesheet" href="styles.css"></head>', 1), "EXTERNAL_DEPENDENCY"),
        "duplicate_fragment": (base.replace('https://www.ecomcrew.com/specific-post-2', 'https://www.marketplacepulse.com/articles/specific-article-1#section-two'), "DUPLICATE_URL"),
        "empty_title": (base.replace('>MP新闻</a>', '>   </a>', 1), "CARD_TITLE"),
    }
    for name, (html, code) in cases.items(): expect_case(name, html, code)
    # An audit in a parent directory belonging to another project must not satisfy production mode.
    r = run(base, production=True, parent_audit=True)
    if r.returncode == 0 or "AUDIT_RECORD_MISSING" not in r.stdout:
        raise AssertionError("wrong-project audit was accepted")
    print(f"v2.4.1 mutation regression: PASS ({len(cases)} HTML mutations + audit-boundary case)")

if __name__ == "__main__": main()
