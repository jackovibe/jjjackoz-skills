#!/usr/bin/env python3
"""渲染器回归 —— 保证 render-report.py 出的 HTML 能过 validator。

为什么单独测：v2.10.0 把「写 HTML」换成「填 JSON + 渲染」，结构正确性从
validator 事后拦截变成渲染器保证。这个测试就是那份保证的证据：
  ① 正常数据 → 渲染出的 HTML 必须 26/26 通过
  ② P0 超 40% → 渲染器必须在写盘前拒绝（不能靠 validator 兜）
  ③ 卡片日期晚于生成日 → 同上
  ④ 字段缺失 → 同上
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent.parent
RENDER = SKILL / "scripts" / "render-report.py"
VALIDATOR = SKILL / "scripts" / "validate-report.py"
PY = sys.executable


def card(tier, title, url, src, st, tag, hero=False, note="排序:当日"):
    return {"tier": tier, "hero": hero, "title": title, "url": url, "date": "2026-10-20",
            "source": src, "src_tier": st, "tag": tag, "deadline": "",
            "summary": f"{title} 的事实摘要，含具体数字与生效日。",
            "impact": "对卖家意味着什么。", "action": "明天要改什么。", "audit_note": note}


def base(n_policy=3, n_reg=2, n_log=2, n_mkt=1):
    return {
        "date": "2026-10-21", "generated_at": "2026-10-21 07:50",
        "window": ["2026-10-20 00:00", "2026-10-21 07:50"],
        "scope_note": "仅收录 2026-10-20 00:00 — 2026-10-21 07:50（Asia/Shanghai）发布或明确更新的资讯。",
        "stats": {"candidates": 42, "shortlist": 26, "rejected_in_verify": 13},
        "countdown": [{"date": "2026-10-27", "name": "节点一", "level": "high"}],
        "trends": [{"head": "一句话结论", "tag": "标签", "text": "支撑事实。"}],
        "timeline": [{"date": "2026-11-01", "title": "节点事项", "note": "说明",
                      "url": "https://container-news.com/maersk-gemini", "link_text": "来源"}],
        "sections": {
            "cat-policy": {"cards": [
                card("P0" if i == 0 else "P1", f"政策卡{i}", f"https://www.marketplacepulse.com/articles/p{i}",
                     "Marketplace Pulse", "T1", "后台功能", hero=(i == 0)) for i in range(n_policy)]},
            "cat-reg": {"cards": [
                card("P1", f"合规卡{i}", f"https://www.cpsc.gov/Recalls/2026/r{i}", "CPSC.gov", "T0", "召回")
                for i in range(n_reg)]},
            "cat-logistics": {"cards": [
                card("P1", f"物流卡{i}", f"https://container-news.com/log{i}", "Container News", "T1", "航线")
                for i in range(n_log)]},
            "cat-market": {"cards": [
                card("P2", f"市场卡{i}", f"https://www.marketplacepulse.com/articles/m{i}", "Marketplace Pulse", "T1", "大盘数据")
                for i in range(n_mkt)]},
            "cat-community": {"cards": [
                card("社区", f"社区帖{i}", f"https://www.wearesellers.com/question/9{i}", "知无不言", "T2", "运营实操",
                     note="可复用性/具体度") for i in range(3)]},
        },
        "rejected": [{"title": "某服务商白皮书", "code": "A1", "reason": "服务商推广"}],
    }


def run(args, cwd):
    return subprocess.run([PY] + args, cwd=cwd, capture_output=True, text=True)


def main():
    results = []

    # ① 正常数据 → 必须 26/26 通过
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "早报审计").mkdir()
        (d / "c.json").write_text(json.dumps(base(), ensure_ascii=False), encoding="utf-8")
        r = run([str(RENDER), "c.json", "--out", "跨境早报-2026-10-21.html", "--audit", "早报审计"], d)
        if r.returncode != 0:
            results.append(("正常数据渲染", "FAIL", r.stdout + r.stderr))
        else:
            v = run([str(VALIDATOR), "跨境早报-2026-10-21.html"], d)
            ok = v.returncode == 0 and "全部结构检查通过" in v.stdout
            results.append(("渲染结果过 26 项门禁", "PASS" if ok else "FAIL",
                            "" if ok else v.stdout[-800:]))

    # ②③④ 坏数据 → 渲染器必须拒绝（exit≠0）
    def reject_case(name, mutate):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            data = base()
            mutate(data)
            (d / "c.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            r = run([str(RENDER), "c.json", "--out", "x.html"], d)
            refused = r.returncode != 0 and not (d / "x.html").exists()
            results.append((name, "PASS" if refused else "FAIL",
                            "" if refused else f"未拒绝，exit={r.returncode}"))

    def p0_overflow(data):
        for i, c in enumerate(data["sections"]["cat-policy"]["cards"]):
            c["tier"] = "P0"
        for c in data["sections"]["cat-reg"]["cards"]:
            c["tier"] = "P0"
        data["sections"]["cat-logistics"]["cards"][0]["tier"] = "P0"
        data["sections"]["cat-market"]["cards"][0]["tier"] = "P0"

    reject_case("P0 超 40% 拒绝渲染", p0_overflow)
    reject_case("卡片日期晚于生成日拒绝", lambda d: d["sections"]["cat-market"]["cards"][0].update(date="2026-10-25"))
    reject_case("字段缺失拒绝", lambda d: d["sections"]["cat-reg"]["cards"][0].update(impact=""))
    reject_case("卡片不足 7 条拒绝", lambda d: d.update(sections={k: {"cards": []} for k in d["sections"]}) or
                d["sections"]["cat-policy"]["cards"].append(card("P0", "唯一卡", "https://www.cpsc.gov/Recalls/2026/x", "CPSC.gov", "T0", "召回")))

    # 输出
    print("=" * 78)
    print("渲染器回归（render-report.py）")
    print("=" * 78)
    bad = 0
    for name, verdict, detail in results:
        print(f"{name:<30}{verdict}")
        if verdict != "PASS":
            bad += 1
            if detail:
                print("   " + detail.replace("\n", "\n   "))
    print("=" * 78)
    print(f"统计: 通过 {len(results) - bad} / 总 {len(results)}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
