#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""来源核验门禁（check-provenance）。

解决的问题不是「抓不到」，而是**用历史结论替代实测**：
上一期写了「某源连续 N 期超时」，这一期直接抄过来当淘汰理由，跳过实跑。

做法：不猜语义，只查**举证责任**。
    默认假设「源活着」。任何「源死了 / 抓不到 / 没有更新」的结论，
    必须在审计里附当日 probe 实测记录，否则判红。

四条检查：
    P1 PROBE_CITED          审计必须引用当日 probe-YYYY-MM-DD（无引用=整期没做实测）
    P2 DEATH_NEEDS_CHAIN    写 URL_UNREACHABLE 必须附四阶通道梯证据（curl/webfetch/ego/rss）
    P3 INHERITED_RULING     判定句里的「连续第 N 期/沿用上期」若无当日 probe 引用→红；
                            出现在「更正/误判/不成立」语境→放行（那是教训记录，该留）
    P4 STALE_VS_DEAD        NO_NEW_IN_WINDOW 与 URL_UNREACHABLE 同源互斥，同时出现在同一源→红

用法：
    python scripts/check-provenance.py --audit 早报审计/2026-11-02.md --run-date 2026-11-02
退出码：0 通过；1 有 ERROR
"""
import argparse
import datetime as dt
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 判定 / 结论类措辞
RULING_WORDS = re.compile(
    r"连续第\s*\d+\s*期|沿用上期|维持原判|维持上期|同上期结论|与上期一致|一如上期|承接上期判定")
# 合法的「讲教训」语境
LESSON_WORDS = re.compile(r"更正|误判|作废|有误|不成立|推翻|原记|此前记错|教训|曾因")
DEATH_CLAIM = re.compile(r"URL_UNREACHABLE|登录墙|CONNECTION_TIMED_OUT|站点已死|域已死")
# 否定语境：句子里明说「不是不可达/非取不到源」，属正确表述，不要求举证
NEGATION = re.compile(r"非「?取不到|不是不可达|并非不可达|非不可达|不是登录墙|不属登录墙")
STALE_CLAIM = re.compile(r"NO_NEW_IN_WINDOW")
# 四阶通道梯
LADDER = {
    "curl": re.compile(r"curl|HTTP\s*\d{3}|状态码|PowerShell|Invoke-WebRequest", re.I),
    "webfetch": re.compile(r"WebFetch|fetch failed|语义抓取|转\s*markdown", re.I),
    "ego": re.compile(r"ego|ego lite|浏览器渲染|Chromium", re.I),
    "rss": re.compile(r"RSS|sitemap|/feed|pubDate|lastmod", re.I),
}
PROBE_REF = re.compile(r"probe-\d{4}-\d{2}-\d{2}")


def load_probe(state_dir, run_date):
    p = os.path.join(state_dir, f"probe-{run_date}.json")
    if not os.path.isfile(p):
        return None, p
    with open(p, encoding="utf-8") as f:
        return json.load(f), p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", required=True)
    ap.add_argument("--run-date", default=dt.date.today().isoformat())
    ap.add_argument("--state-dir", default="早报状态")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if not os.path.isfile(a.audit):
        print(f"审计文件不存在：{a.audit}", file=sys.stderr)
        return 1
    with open(a.audit, encoding="utf-8") as f:
        lines = f.read().splitlines()

    probe, probe_path = load_probe(a.state_dir, a.run_date)
    errors, warns = [], []

    # P1 是否做过当日实测
    cited = [i + 1 for i, ln in enumerate(lines) if PROBE_REF.search(ln)]
    if probe is None:
        errors.append({
            "code": "P1_PROBE_MISSING",
            "line": 0,
            "msg": f"当日探针文件不存在：{probe_path}。采集前必须跑 probe-channels.py，"
                   f"否则「源今天什么状态」无任何实测依据",
        })
    elif not cited:
        errors.append({
            "code": "P1_PROBE_CITED",
            "line": 0,
            "msg": f"审计全文未引用当日探针（{os.path.basename(probe_path)}）。"
                   f"探针跑过但没写进审计=结论仍无出处，读者无法区分「实测」与「记忆」",
        })

    # 逐行 P2 / P3
    for i, ln in enumerate(lines, 1):
        has_probe_ref = bool(PROBE_REF.search(ln))

        # 「更正/教训」语境里的死亡措辞是在纠正旧判断，不要求四阶举证
        in_lesson = bool(LESSON_WORDS.search(ln)) or bool(NEGATION.search(ln))
        if DEATH_CLAIM.search(ln) and not has_probe_ref and not in_lesson:
            hit = [k for k, rx in LADDER.items() if rx.search(ln)]
            if len(hit) < 3:
                errors.append({
                    "code": "P2_DEATH_NEEDS_CHAIN",
                    "line": i,
                    "msg": f"判定源不可达/登录墙，但只走了 {len(hit)}/4 阶通道梯（{','.join(hit) or '无'}），"
                           f"且未引当日 probe。判死须举证：curl→WebFetch→ego→RSS/sitemap",
                })

        if RULING_WORDS.search(ln):
            if LESSON_WORDS.search(ln):
                warns.append({
                    "code": "P3_LESSON_CONTEXT",
                    "line": i,
                    "msg": "继承性表述出现在「更正/教训」语境，放行（此类记录应当保留）",
                })
            elif not has_probe_ref:
                m = RULING_WORDS.search(ln)
                errors.append({
                    "code": "P3_INHERITED_RULING",
                    "line": i,
                    "msg": f"以「{m.group(0)}」作为本期判定依据，且无当日 probe 引用。"
                           f"历史结论只是待验证假设，本期必须实跑",
                })

    # P4 同一源既「无更新」又「不可达」
    if probe:
        verdicts = {}
        for r in probe.get("results", []):
            verdicts[r["id"]] = r["verdict"]
        for i, ln in enumerate(lines, 1):
            if STALE_CLAIM.search(ln) and DEATH_CLAIM.search(ln) and not LESSON_WORDS.search(ln):
                errors.append({
                    "code": "P4_STALE_VS_DEAD",
                    "line": i,
                    "msg": "同一行同时出现「无窗口内新增」与「不可达/登录墙」，两种判定互斥："
                           "供给停滞不是通道故障",
                })

    ok = not errors
    if a.json:
        print(json.dumps({"ok": ok, "run_date": a.run_date,
                          "probe": os.path.basename(probe_path) if probe else None,
                          "errors": errors, "warns": warns},
                         ensure_ascii=False, indent=2))
    else:
        print(f"来源核验 {a.audit}  (run_date={a.run_date})")
        print(f"探针：{os.path.basename(probe_path) if probe else '缺失'}"
              f"（审计内引用 {len(cited)} 处）")
        if probe:
            c = probe.get("counts", {})
            print("探针判定：" + "  ".join(f"{k}={v}" for k, v in sorted(c.items())))
        print()
        if ok:
            print("✅ 通过：所有源状态判定都有当日实测出处")
        for e in errors:
            print(f"❌ [{e['code']}] 第 {e['line']} 行  {e['msg']}")
        if warns:
            print()
            for w in warns:
                print(f"ℹ️  [{w['code']}] 第 {w['line']} 行  {w['msg']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
