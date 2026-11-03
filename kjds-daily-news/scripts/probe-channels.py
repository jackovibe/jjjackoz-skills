#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通道存活探针（每期开工第 0 步）。

回答一个唯一问题：**今天现在**，每个源是什么状态？
禁止用上一期记录、历史结论、记忆里的「某源已死」替代本次实测。

设计要点（来自 2026-11-02 的实战教训）：
1. 通道用 curl --noproxy "*"，不用 urllib（本机 urllib 必超时，curl 可 200）
2. 状态四分，把「供给停滞」从「通道故障」里拆出来：
   FRESH 有窗口内新条目 / STALE 能通但无新条目 / BLOCKED 需换通道 / DEAD 真不通
3. 日期取「≤ 今天」的最大值，防止抓到页面里的未来活动日期
4. 自检：全部 STALE/DEAD 时先怀疑探针本身，不判源死

用法：
    python scripts/probe-channels.py --run-date 2026-11-03 --window-days 3
    python scripts/probe-channels.py --only amazon_seller_blog,cpsc_news
    python scripts/probe-channels.py --json          # 只输出机器可读

退出码：0 正常；2 疑似探针失效（0 个 FRESH）；1 参数/文件错误
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
TARGETS = os.path.join(HERE, "probe-targets.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

MON = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"])}

RE_ISO = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")
RE_US = re.compile(r"\b(" + "|".join(MON) + r")[a-z]*\.?\s+(\d{1,2}),?\s+(20\d{2})\b", re.I)
RE_UK = re.compile(r"\b(\d{1,2})\s+(" + "|".join(MON) + r")[a-z]*\.?,?\s+(20\d{2})\b", re.I)
RE_SLASH = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b")
RE_ZH = re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
RE_PUBDATE = re.compile(r"<(?:pubDate|lastBuildDate|updated|dc:date)>([^<]{6,60})</", re.I)


def curl(url, timeout=25):
    """返回 (code:int, body:str, err:str)。code=0 表示连接层失败。"""
    cmd = ["curl", "-sS", "--noproxy", "*", "-L", "-m", str(timeout),
           "-A", UA, "-H", "Accept-Encoding: identity",
           "-w", "\n__HTTP_CODE__%{http_code}", url]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout + 10)
    except subprocess.TimeoutExpired:
        return 0, "", "subprocess timeout"
    body = p.stdout.decode("utf-8", "replace")
    code = 0
    tail = re.search(r"__HTTP_CODE__(\d{3})\s*$", body.strip())
    if tail:
        code = int(tail.group(1))
        body = body[: tail.start()]
    err = p.stderr.decode("utf-8", "replace").strip()[:200]
    return code, body, err


def safe_date(y, m, d):
    try:
        return dt.date(int(y), int(m), int(d))
    except ValueError:
        return None


def extract_dates(text, today, mode):
    """抽出 ≤ today 的全部合法日期，返回去重列表（降序）。"""
    found = set()
    if mode == "rss" or "xml" in text[:200].lower():
        for frag in RE_PUBDATE.findall(text):
            for y, m, d in RE_ISO.findall(frag) + [
                (a[2], MON[a[0].lower()], a[1]) for a in RE_US.findall(frag)
            ]:
                dd = safe_date(y, m, d)
                if dd:
                    found.add(dd)
    for y, m, d in RE_ISO.findall(text):
        dd = safe_date(y, m, d)
        if dd:
            found.add(dd)
    for mon, d, y in RE_US.findall(text):
        dd = safe_date(y, MON[mon.lower()], d)
        if dd:
            found.add(dd)
    for d, mon, y in RE_UK.findall(text):
        dd = safe_date(y, MON[mon.lower()], d)
        if dd:
            found.add(dd)
    for m, d, y in RE_SLASH.findall(text):
        dd = safe_date(y, m, d)
        if dd:
            found.add(dd)
    for y, m, d in RE_ZH.findall(text):
        dd = safe_date(y, m, d)
        if dd:
            found.add(dd)
    # 只保留不晚于今天、且不早于 2000 年（过滤版权年份等噪音上限靠 today 卡）
    valid = [x for x in found if dt.date(2000, 1, 1) <= x <= today]
    return sorted(valid, reverse=True)


def classify(code, dates, window_start, mode, channel="curl"):
    """判定优先级：连接层/协议层问题 > 通道不匹配 > 内容新鲜度。

    channel=ego 的源在 curl 下 401/403/000 是**预期行为**，不是通道死亡——
    必须记 NEEDS_EGO，否则每期都会把「要换通道」误读成「源挂了」。
    """
    if mode == "none":
        # 站点本身无日期口径，只能判可通性，禁止凭空抽出页面里的旧日期当更新日
        if code == 0:
            return ("NEEDS_EGO", "连接失败，须 ego 复核") if channel == "ego" else ("DEAD", "连接层失败")
        if code in (401, 403, 407, 429):
            return ("NEEDS_EGO", f"HTTP {code}，须 ego/WebFetch") if channel != "curl" else ("BLOCKED", f"HTTP {code}（WAF/限流，换通道）")
        return "OPEN_NODATE", "可通，站点无日期口径（需快照 diff 判更新）"
    if code == 0:
        if channel == "ego":
            return "NEEDS_EGO", "curl 连接失败（此类源预期须 ego）"
        return "DEAD", "连接层失败"
    if code in (401, 402, 403, 407, 429):
        if channel == "ego":
            return "NEEDS_EGO", f"curl HTTP {code}（此类源预期须 ego 渲染）"
        if channel == "webfetch":
            return "NEEDS_WEBFETCH", f"curl HTTP {code}（WAF 拦 curl，WebFetch 可读）"
        return "BLOCKED", f"HTTP {code}（WAF/限流，换通道）"
    if code in (404, 410):
        return "GONE", f"HTTP {code}（路径已废，改入口）"
    if code >= 500:
        return "DEAD", f"HTTP {code}（服务端错误）"
    if code not in (200, 203, 204):
        return "BLOCKED", f"HTTP {code}"
    if not dates:
        return "OPEN_NODATE", "可通，但未抽到日期（需 ego 二次判读）"
    latest = dates[0]
    if latest >= window_start:
        return "FRESH", f"最新 {latest}"
    return "STALE", f"最新 {latest}（距今天 {(window_start - latest).days} 天前已在窗口外）"


def load_prev(state_dir, run_date):
    """找最近一期 probe json，用于标记「上期判错、本期恢复」。"""
    if not os.path.isdir(state_dir):
        return None, None
    best = None
    for fn in os.listdir(state_dir):
        m = re.match(r"probe-(\d{4}-\d{2}-\d{2})\.json$", fn)
        if m and m.group(1) < run_date.isoformat():
            if best is None or m.group(1) > best[0]:
                best = (m.group(1), os.path.join(state_dir, fn))
    if not best:
        return None, None
    try:
        with open(best[1], encoding="utf-8") as f:
            return best[0], json.load(f)
    except Exception:
        return best[0], None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-date", default=dt.date.today().isoformat())
    ap.add_argument("--window-days", type=int, default=3,
                    help="回溯窗口天数：周一=3，其余=2")
    ap.add_argument("--state-dir", default="早报状态")
    ap.add_argument("--only", default="", help="逗号分隔的 target id")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--timeout", type=int, default=25)
    a = ap.parse_args()

    run_date = dt.date.fromisoformat(a.run_date)
    window_start = run_date - dt.timedelta(days=a.window_days)

    with open(TARGETS, encoding="utf-8") as f:
        targets = json.load(f)["targets"]
    if a.only:
        want = {s.strip() for s in a.only.split(",") if s.strip()}
        targets = [t for t in targets if t["id"] in want]
        if not targets:
            print("没有匹配的 target", file=sys.stderr)
            return 1

    prev_date, prev = load_prev(a.state_dir, run_date)
    prev_map = {}
    if prev:
        for r in prev.get("results", []):
            prev_map[r["id"]] = r["verdict"]

    results = []
    for t in targets:
        code, body, err = curl(t["url"], a.timeout)
        dates = extract_dates(body, run_date, t["expect"])
        verdict, why = classify(code, dates, window_start, t["expect"], t["channel"])
        rec = {
            "id": t["id"], "name": t["name"], "zone": t["zone"],
            "url": t["url"], "channel": t["channel"],
            "http_code": code, "bytes": len(body),
            # expect=none 的站不认日期口径，抽出的一律只作参考，不摆进「最新日期」列误导判断
            "latest_date": (dates[0].isoformat() if dates else None) if t["expect"] != "none" else None,
            "raw_date_seen": dates[0].isoformat() if dates else None,
            "verdict": verdict, "reason": why,
            "prev_verdict": prev_map.get(t["id"]),
            "error": err,
        }
        if rec["prev_verdict"] in ("DEAD", "BLOCKED", "GONE") and verdict in ("FRESH", "STALE", "OPEN_NODATE"):
            rec["warning"] = f"上期记为 {rec['prev_verdict']}，本期实测可通 —— 上期结论作废，禁止继承"
        results.append(rec)
        if not a.json:
            print(f"[{verdict:12}] {t['id']:26} code={code:3} {len(body):>8}B  {why}")
            if rec.get("warning"):
                print(f"             ^^ {rec['warning']}")

    counts = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    fresh = counts.get("FRESH", 0)

    payload = {
        "probe_date": run_date.isoformat(),
        "window_days": a.window_days,
        "window_start": window_start.isoformat(),
        "counts": counts,
        "self_check": "OK" if fresh > 0 else "SUSPECT_PROBE_BROKEN",
        "results": results,
        "prev_probe": prev_date,
    }

    # --only 是抽查模式：只打印，不写基线，避免子集结果覆盖当日全量快照
    if a.only:
        print()
        print("统计（抽查模式，不写盘）：" + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        return 0

    os.makedirs(a.state_dir, exist_ok=True)
    jpath = os.path.join(a.state_dir, f"probe-{run_date.isoformat()}.json")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    if a.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if fresh > 0 else 2

    # markdown 摘要
    lines = [f"# 通道存活探针 {run_date.isoformat()}", "",
             f"窗口：{window_start.isoformat()} ~ {run_date.isoformat()}（{a.window_days} 天）｜"
             f"自检：**{payload['self_check']}**｜上一期：{prev_date or '无'}",
             "", "| 源 | 区 | 通道 | HTTP | 字节 | 最新日期 | 判定 | 说明 |",
             "|---|---|---|---|---|---|---|---|"]
    for r in results:
        lines.append("| {} | {} | {} | {} | {} | {} | **{}** | {} |".format(
            r["name"], r["zone"], r["channel"], r["http_code"], r["bytes"],
            r["latest_date"] or "—", r["verdict"], r["reason"]))
    warns = [r for r in results if r.get("warning")]
    if warns:
        lines += ["", "## ⚠️ 上期结论作废", ""]
        lines += [f"- {r['name']}：{r['warning']}" for r in warns]
    lines += ["", "## 判定口径", "",
              "- **FRESH**：窗口内有新条目，可正常采集",
              "- **STALE**：通道正常但无窗口内新条目 → 记 `NO_NEW_IN_WINDOW`，**不得**记成通道故障",
              "- **NEEDS_EGO / NEEDS_WEBFETCH**：该源本就不是 curl 能读的，**不是通道死亡**，按通道阶梯换手段",
              "- **BLOCKED / DEAD**：必须按通道阶梯（curl → WebFetch → ego → RSS/sitemap）跑完才可判死",
              "- **OPEN_NODATE**：可通但无日期口径，需 ego 判读或做 URL 快照 diff", ""]
    mpath = os.path.join(a.state_dir, f"probe-{run_date.isoformat()}.md")
    with open(mpath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print()
    print("统计：" + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"自检：{payload['self_check']}")
    print(f"已写入 {jpath}")
    print(f"已写入 {mpath}")
    if fresh == 0:
        print("\n!! 0 个 FRESH：先怀疑探针本身（本机网络/curl/正则），不要据此判所有源死。", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
