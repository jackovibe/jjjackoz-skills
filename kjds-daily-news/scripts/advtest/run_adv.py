#!/usr/bin/env python3
"""运行 validator 于所有对抗样本，并标注每个样本的「期望结果 vs 实际结果」。"""
import os
import subprocess
import sys
import re

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "out")
VALIDATOR = os.path.join(HERE, "..", "validate-report.py")

# 期望: "PASS"(应全过) / "FAIL"(应拦截)
EXPECT = {
    "T1_good_baseline": "PASS",
    "T2_aggregator_section": "FAIL",     # 版块页应被拦
    "T3_forbidden_in_prose": "PASS",     # 正文提及禁用域名是安全的（只扫href）
    "T4_external_bg_image": "FAIL",      # 外部CDN应被拦
    "T5_wearesellers_label_stuffing": "PASS",  # 验证器只看标签，已知局限
    "T6_malformed_date": "FAIL",         # 日期错乱应被拦
    "T7_secondary_disguised": "FAIL",     # 二手源伪装：36kr 未登记总表，白名单应拦（v2.6.0 起堵上）
    "T8_homepage_root": "FAIL",          # 根路径非文章页应被拦
    "T9_forbidden_subset_gap": "FAIL",   # 跨境魔方应被拦（validator漏了）
    "T10_wearesellers_only_2": "PASS",   # 3条改为质量目标，低新闻量日可少报并在审计说明
    "T11_forbidden_in_href": "FAIL",     # 禁用域名在href内应被拦（反证T3安全）
    "T12_known_agg_category": "FAIL",    # 已知/category/模式应被拦（反证T2是口径漏检）
    # ── 第二轮新增 ──
    "T13_wearesellers_wrong_domain": "FAIL",  # 知无不言标签但非wearesellers链接（B2应拦）
    "T14_real_structure_baseline": "PASS",    # 真实<a class=card-title>结构全合规（无误伤）
    "T15_t3_eccang_href": "FAIL",             # T3 eccang.com（channels.md同步）应拦（A5）
    "T16_real_dup_url": "FAIL",               # 真实结构重复URL应拦（此前静默空过）
    "T17_external_img": "FAIL",               # 外部<img src>应拦（A3扩展）
    # ── 第三轮新增（B3 底部链接按钮） ──
    "T18_missing_bottom_link": "FAIL",        # 卡片缺底部「→ 链接」按钮应拦（B3）
    "T19_bottom_root_path": "FAIL",           # 底部按钮指向根路径/首页应拦（B3）
    "T20_bottom_placeholder": "FAIL",         # 底部按钮为占位符 # 应拦（B3）
    "T21_invalid_calendar_date": "FAIL",
    "T22_missing_summary": "FAIL",
    "T23_source_pill_mismatch": "FAIL",
    "T24_title_bottom_mismatch": "FAIL",
    "T25_protocol_relative_external": "FAIL",
    "T26_self_closing_card_link_baseline": "PASS",
    "T27_summary_endpoint": "FAIL", "T28_announcements_endpoint": "FAIL",
    "T29_list_endpoint": "FAIL", "T30_index_endpoint": "FAIL",
    "T31_blog_slug_baseline": "PASS",
    # ── 第五轮：来源白名单（2026-10-20，v2.6.0）──
    "T32_dashuju_aggregator": "FAIL",    # 聚合/UGC 平台（10100.com）作最终链接应拦
    "T33_chwang_aggregator": "FAIL",     # 聚合平台（chwang.com）作最终链接应拦
    # ── 第六轮：第四轮审查实证收编（2026-10-20，v2.7.2）──
    "T34_embedded_link_in_summary": "FAIL",   # 摘要内嵌未登记域链接（白名单扩至卡内全部 <a>）
    "T35_external_embed": "FAIL",             # <embed src> 外部 CDN（资源依赖扫描补 embed）
    "T36_article_no_slug": "FAIL",            # /article/ 无 slug（聚合页判定补无 slug 集合）
    "T37_trailing_slash_bottom_link": "PASS", # 底部与标题仅差 trailing slash，归一化后应放行
    "T38_year_archive": "FAIL",               # /news/2026 年度归档（M4 残留应拦）
    "T39_page_query": "FAIL",                 # ?page=2 翻页参数（M4 残留应拦）
    # ── 第七轮：v2.9.0 三项新检查 ──
    "T40_future_card_date": "FAIL",           # 卡片日期晚于 Footer 生成日（FUTURE_DATE 应拦）
}

# 需要「项目根 + 早报审计/」布局的 fixture 样本（审计交叉检查）
FIXTURE_EXPECT = {
    "T41_audit_zone_mismatch": "FAIL",        # 审计分区分布与报告不符（AUDIT_ZONE_MISMATCH 应拦）
    "T42_audit_zone_ok": "PASS",              # 审计分区分布完全对齐（不应误报）
    "T43_p0_ratio_overflow": "FAIL",          # P0 行数超 40% 上限（P0_RATIO 应拦）
}
FIXTURE_MUST_MATCH = {
    "T41_audit_zone_mismatch": "AUDIT_ZONE_MISMATCH",
    "T43_p0_ratio_overflow": "P0_RATIO",
}

MUST_MATCH = {
    "T2_aggregator_section": "聚合页URL", "T4_external_bg_image": "外部依赖",
    "T6_malformed_date": "日期格式", "T8_homepage_root": "卡片链接绝对https",
    "T9_forbidden_subset_gap": "禁止域名", "T11_forbidden_in_href": "禁止域名",
    "T12_known_agg_category": "聚合页URL", "T13_wearesellers_wrong_domain": "知无不言链接域名一致性",
    "T15_t3_eccang_href": "禁止域名", "T16_real_dup_url": "重复URL",
    "T17_external_img": "外部依赖", "T18_missing_bottom_link": "卡片底部链接按钮及一致性",
    "T19_bottom_root_path": "卡片底部链接按钮及一致性", "T20_bottom_placeholder": "卡片底部链接按钮及一致性",
    "T21_invalid_calendar_date": "日期格式", "T22_missing_summary": "卡片事实摘要",
    "T23_source_pill_mismatch": "Header来源数及来源pill", "T24_title_bottom_mismatch": "卡片底部链接按钮及一致性",
    "T25_protocol_relative_external": "外部依赖",
    "T7_secondary_disguised": "SOURCE_NOT_IN_REGISTRY",
    "T27_summary_endpoint": "聚合页URL", "T28_announcements_endpoint": "聚合页URL",
    "T29_list_endpoint": "聚合页URL", "T30_index_endpoint": "聚合页URL",
    "T32_dashuju_aggregator": "禁止域名",
    "T33_chwang_aggregator": "禁止域名",
    "T34_embedded_link_in_summary": "SOURCE_NOT_IN_REGISTRY",
    "T35_external_embed": "外部依赖",
    "T36_article_no_slug": "聚合页URL",
    "T38_year_archive": "聚合页URL",
    "T39_page_query": "聚合页URL",
    "T40_future_card_date": "FUTURE_DATE",
}
MUST_MATCH = {k: {
    "聚合页URL":"AGGREGATION_URL", "外部依赖":"EXTERNAL_DEPENDENCY", "日期格式":"INVALID_DATE",
    "卡片链接绝对https":"CARD_URL", "禁止域名":"FORBIDDEN_DOMAIN", "知无不言链接域名一致性":"WEARESELLERS_DOMAIN",
    "重复URL":"DUPLICATE_URL", "卡片底部链接按钮及一致性":"CARD_BOTTOM_LINK", "卡片事实摘要":"CARD_SUMMARY",
    "Header来源数及来源pill":"SOURCE_PILLS"
}.get(v, v) for k,v in MUST_MATCH.items()}

# 各样本意图说明
INTENT = {
    "T1_good_baseline": "完全合规基线",
    "T2_aggregator_section": "用 /blog/ 版块页伪装具体文章",
    "T3_forbidden_in_prose": "正文提及禁用域名 ebrun.com（应安全）",
    "T4_external_bg_image": "内联 style 引入外部 CDN 背景图",
    "T5_wearesellers_label_stuffing": "知无不言标签灌水（已知只看标签）",
    "T6_malformed_date": "card-date 写成 2026/07/17",
    "T7_secondary_disguised": "来源标MP，链接是36kr二级转载（白名单v2.6.0已堵）",
    "T8_homepage_root": "链接到 amazon.com 根路径",
    "T9_forbidden_subset_gap": "用跨境魔方 upkuajing.com（validator漏检）",
    "T10_wearesellers_only_2": "知无不言仅 2 条（复现7/17缺陷）",
    "T11_forbidden_in_href": "禁用域名 ebrun 出现在 href 内（应拦）",
    "T12_known_agg_category": "/category/ 已知聚合模式（应拦）",
    "T13_wearesellers_wrong_domain": "知无不言标签但链接非wearesellers.com（B2应拦）",
    "T14_real_structure_baseline": "真实<a class=card-title>结构全合规（无误伤）",
    "T15_t3_eccang_href": "T3 eccang.com链接（channels.md同步，A5应拦）",
    "T16_real_dup_url": "真实结构两张卡同URL（重复应拦）",
    "T17_external_img": "外部<img src>引用（A3扩展应拦）",
    "T18_missing_bottom_link": "卡片缺底部「→ 链接」按钮（B3应拦）",
    "T19_bottom_root_path": "底部按钮指向根路径/首页（B3应拦）",
    "T20_bottom_placeholder": "底部按钮为占位符 #（B3应拦）",
    "T21_invalid_calendar_date": "日期为不存在的日历日期 2026-99-99",
    "T22_missing_summary": "卡片缺少事实摘要",
    "T23_source_pill_mismatch": "来源 pill 与卡片来源不一致",
    "T24_title_bottom_mismatch": "标题与底部按钮 URL 不一致",
    "T25_protocol_relative_external": "协议相对外部图片依赖",
    "T26_self_closing_card_link_baseline": "规范中的 a.card-link 合规基线",
    "T27_summary_endpoint": "summary 聚合终端路径",
    "T28_announcements_endpoint": "announcements 聚合终端路径",
    "T29_list_endpoint": "list 聚合终端路径",
    "T30_index_endpoint": "index.html 聚合终端路径",
    "T31_blog_slug_baseline": "/blog/具体slug 合规基线",
    "T32_dashuju_aggregator": "大数跨境10100.com（T3禁用域）作最终来源应拦",
    "T33_chwang_aggregator": "出海网chwang.com（T3禁用域）作最终来源应拦",
    "T34_embedded_link_in_summary": "摘要内嵌 zhihu.com 未登记域链接（M1 应拦）",
    "T35_external_embed": "<embed src> 指向外部 CDN（M2 应拦）",
    "T36_article_no_slug": "/article/ 无 slug 的版块页（M4 应拦）",
    "T37_trailing_slash_bottom_link": "底部链接与标题仅差 trailing slash（L5 应放行）",
    "T38_year_archive": "年度归档 /news/2026 无 slug（M4 残留应拦）",
    "T39_page_query": "?page=2 翻页参数（M4 残留应拦）",
    "T40_future_card_date": "卡片日期晚于报告生成日（未来日期应拦）",
}

def suite_preflight(names):
    actual=set(names); expected=set(EXPECT)
    return bool(actual) and actual == expected
def case_matches(name, actual, stdout):
    expect=EXPECT.get(name, "?")
    if expect == "?": return False
    if actual != expect: return False
    if expect == "FAIL" and name in MUST_MATCH:
        codes=set(re.findall(r"^❌ \[[^\n]+\] code=([A-Z0-9_]+)$", stdout, re.M))
        return MUST_MATCH[name] in codes
    return True

if "--self-test" in sys.argv[1:]:
    assert not case_matches("T21_invalid_calendar_date", "FAIL", "❌ [卡片事实摘要] code=CARD_SUMMARY"), "wrong failure reason accepted"
    assert not case_matches("T21_invalid_calendar_date", "FAIL", "详情 href=https://x.test/?code=INVALID_DATE\n❌ [卡片事实摘要] code=CARD_SUMMARY"), "URL query spoof accepted"
    assert not suite_preflight([]), "empty suite accepted"
    assert not suite_preflight(set(EXPECT)-{"T1_good_baseline"}), "missing case accepted"
    assert suite_preflight(EXPECT), "complete suite rejected"
    print("runner self-test: PASS (wrong failure reason, empty suite, missing case)")
    sys.exit(0)

files = sorted(f for f in os.listdir(OUT) if f.endswith(".html"))
if not suite_preflight([f[:-5] for f in files]):
    actual_names={f[:-5] for f in files}; expected_names=set(EXPECT)
    missing=sorted(expected_names-actual_names); extra=sorted(actual_names-expected_names)
    print(f"测试集不完整或为空: 实际={len(actual_names)} 期望={len(expected_names)} 缺失={missing} 多余={extra}")
    sys.exit(1)
print("=" * 90)
print(f"{'样本':<32}{'意图':<28}{'期望':<6}{'实际':<6}  判定")
print("=" * 90)

bypasses, falsepos, correct = [], [], []
for f in files:
    name = f[:-5]
    path = os.path.join(OUT, f)
    r = subprocess.run([sys.executable, VALIDATOR, path, "--test-mode"],
                       capture_output=True, text=True)
    actual = "PASS" if r.returncode == 0 else "FAIL"
    expect = EXPECT.get(name, "?")
    codes=set(re.findall(r"^❌ \[[^\n]+\] code=([A-Z0-9_]+)$", r.stdout, re.M))
    if actual == expect and expect == "FAIL" and name in MUST_MATCH and MUST_MATCH[name] not in codes:
        verdict = "⚠️  目标检查未触发"
        falsepos.append(name)
    elif actual == expect:
        verdict = "✅ 符合预期"
        correct.append(name)
    else:
        if actual == "PASS" and expect == "FAIL":
            verdict = "⚠️  绕过(护栏失效)"
            bypasses.append(name)
        elif actual == "FAIL" and expect == "PASS":
            verdict = "⚠️  假阳性(误杀)"
            falsepos.append(name)
        else:
            verdict = "❓ 未定义"
    print(f"{name:<32}{INTENT[name]:<28}{expect:<6}{actual:<6}  {verdict}")

# ── fixture 模式：需要项目根 + 早报审计/ 布局的审计交叉检查样本 ──
FIX = os.path.join(HERE, "auditfix")
fix_names = sorted(d for d in os.listdir(FIX) if os.path.isdir(os.path.join(FIX, d))) if os.path.isdir(FIX) else []
if fix_names:
    print()
    print("=" * 90)
    print("审计交叉检查 fixture")
    print("=" * 90)
    for name in fix_names:
        if name not in FIXTURE_EXPECT:
            print(f"{name:<32}{'未定义':<28}{'—':<6}{'—':<6}  ❓ 未定义")
            bypasses.append(name); continue
        report = os.path.join(FIX, name, "跨境早报-2026-07-17.html")
        r = subprocess.run([sys.executable, VALIDATOR, report],
                           capture_output=True, text=True)
        actual = "PASS" if r.returncode == 0 else "FAIL"
        expect = FIXTURE_EXPECT[name]
        codes = set(re.findall(r"^❌ \[[^\n]+\] code=([A-Z0-9_]+)$", r.stdout, re.M))
        if actual == expect and (expect != "FAIL" or FIXTURE_MUST_MATCH.get(name) in codes):
            verdict = "✅ 符合预期"; correct.append(name)
        elif actual == "PASS" and expect == "FAIL":
            verdict = "⚠️  绕过(护栏失效)"; bypasses.append(name)
        elif actual == "FAIL" and expect == "PASS":
            verdict = "⚠️  假阳性(误杀)"; falsepos.append(name)
        else:
            verdict = "⚠️  目标检查未触发" if expect == "FAIL" else "❓ 未定义"
            falsepos.append(name)
        print(f"{name:<32}{'审计交叉检查':<28}{expect:<6}{actual:<6}  {verdict}")

print("=" * 90)
if bypasses or falsepos or any(EXPECT.get(f[:-5], "?") == "?" for f in files):
    sys.exit(1)
print(f"\n统计: 符合预期 {len(correct)} / 总 {len(files) + len(fix_names)}")
if bypasses:
    print(f"\n🚨 护栏失效(应拦未拦): {', '.join(bypasses)}")
if falsepos:
    print(f"\n⚠️  假阳性(误杀): {', '.join(falsepos)}")
print("=" * 90)
