#!/usr/bin/env python3
"""压缩项目运行状态文件：把已失效的活跃话题行迁入已归档区。

背景
----
`早报状态/topic-registry.md` 的活跃区会持续膨胀：每期登记新话题，但归档
只在「deadline 明确到期」时执行，缺 deadline 的观察型话题、以及 deadline
已过但无人复核的行会一直留在活跃区。实测 2026-10-20：206 行活跃话题中有
130 行是僵尸（42 行 deadline 已过 + 88 行无 deadline 且 30 天无动静），
占文件 85% 体积，而运行时真正需要的只有活跃区表格与倒计时看板。

本脚本做两件事
--------------
1. **僵尸行归档**：deadline 已过、或无 deadline 且超过冷却期未确认的行，
   迁入「二、已归档」区并写明归档原因。归档 = 不再跟踪，不是丢弃——
   canonical_url 与来源证据随行保留，需要时可回溯。
2. **备注瘦身**：活跃区行内的大段历史说明保留（那是来源证据），但把
   「历史说明（保留）」类长段落压缩为一行摘要。归档区行的备注过长时
   截断到指定长度，完整内容写入 `早报状态/归档说明-<name>.md`。

安全约束
--------
- 默认 **dry-run**：只报告将要发生的迁移，不写盘。加 `--apply` 才落盘。
- 落盘前自动备份到 `早报状态/.backup/<name>.<日期>.md`。
- 幂等：重复执行不会二次归档同一行。
- 不删任何行：只改位置 + 缩短归档区备注。

用法
----
    python scripts/compact-state.py <项目根>            # dry-run，报告
    python scripts/compact-state.py <项目根> --apply     # 落盘
    python scripts/compact-state.py <项目根> --apply --stale-days 21
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

ARCHIVE_ROW_RE = re.compile(r"^\|(.*)\|\s*$")
DATE_RE = re.compile(r"(20\d{2})-(\d{1,2})-(\d{1,2})")
MD_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)")
FINGERPRINT_RE = re.compile(r"\*\*(.+?)\*\*")

# 归档区备注截断长度（字符）。超长部分写入旁档文件，不丢失。
ARCHIVE_NOTE_KEEP = 160
# 无 deadline 话题的冷却期：多少天没有「最后确认」就视为僵尸
DEFAULT_STALE_DAYS = 30


def parse_sections(text: str) -> dict[str, tuple[int, int]]:
    """返回 {小节标题: (起始行号, 结束行号)}，行号基于 split('\\n')。"""
    lines = text.split("\n")
    heads = [(i, l) for i, l in enumerate(lines) if l.startswith("## ")]
    out: dict[str, tuple[int, int]] = {}
    for idx, (i, title) in enumerate(heads):
        end = heads[idx + 1][0] if idx + 1 < len(heads) else len(lines)
        out[title.strip()] = (i, end)
    return out


def row_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def is_table_row(line: str) -> bool:
    return line.startswith("|") and line.rstrip().endswith("|") and not set(line) <= set("|-: ")


def extract_dates(text: str, year: int) -> list[date]:
    """从文本抽取所有日期（完整 YYYY-MM-DD 与 MM-DD）。MM-DD 用给定年份补全。"""
    out: list[date] = []
    for y, m, d in DATE_RE.findall(text):
        try:
            out.append(date(int(y), int(m), int(d)))
        except ValueError:
            continue
    for m, d in MD_DATE_RE.findall(text):
        try:
            out.append(date(year, int(m), int(d)))
        except ValueError:
            continue
    return out


def row_deadline_date(cells: list[str], year: int) -> date | None:
    """取该行最晚的 deadline 日期。deadline 列之外也看状态列的「持续执行」类描述。"""
    tail = " ".join(cells[4:6])
    dates = extract_dates(tail, year)
    return max(dates) if dates else None


def row_last_confirmed(cells: list[str]) -> date | None:
    if len(cells) < 3:
        return None
    m = re.fullmatch(r"(20\d{2}-\d{2}-\d{2})", cells[2])
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def build_archive_row(cells: list[str], reason: str, run: date) -> str:
    """把活跃行转成归档行：指纹 | 首报日 | 归档日 | 归档原因。"""
    fp = cells[0].strip()
    m = FINGERPRINT_RE.match(fp)
    fp = m.group(1) if m else fp
    first = cells[1] if len(cells) > 1 else "—"
    return f"| {fp} | {first} | {run.isoformat()} | {reason} |"


DETAIL_REF_RE = re.compile(r"\[详情#(\d+)\]")
DETAIL_MIN_KEEP = 120   # 备注短于该长度不外置，直接留在表里


def externalize_details(text: str, state_dir: Path) -> tuple[str, list[str], Path | None]:
    """把活跃区超长备注正文外置到 `话题详情.md`，表格里留 [详情#N] 引用。

    为什么要外置：活跃区 206 行里 89 行备注超 300 字符，备注列占了活跃区
    67% 的体积（62.8KB / 94.3KB）。但预筛只需要「指纹 + deadline + 最后确认」
    三列，备注正文只在人工回溯时才看。外置后表格瘦身、证据不丢。

    返回 (新文本, 外置条目列表, 详情文件路径或 None)。
    """
    lines = text.split("\n")
    secs = parse_sections(text)
    active_key = next((k for k in secs if k.startswith("## 一、")), None)
    if not active_key:
        return text, [], None
    a0, a1 = secs[active_key]

    entries: list[tuple[int, str, str]] = []   # (序号, 指纹, 备注正文)
    counter = 0
    for i in range(a0, a1):
        line = lines[i]
        if not is_table_row(line):
            continue
        cells = row_cells(line)
        if len(cells) < 7 or not FINGERPRINT_RE.match(cells[0]):
            continue
        note = cells[6]
        if len(note) <= DETAIL_MIN_KEEP:
            continue
        counter += 1
        fp_m = FINGERPRINT_RE.match(cells[0])
        fp = fp_m.group(1) if fp_m else cells[0]
        entries.append((counter, fp, note))
        cells[6] = f"[详情#{counter}]"
        lines[i] = "| " + " | ".join(cells) + " |"

    if not entries:
        return "\n".join(lines), [], None

    detail_path = state_dir / "话题详情.md"
    existing = detail_path.read_text(encoding="utf-8") if detail_path.exists() else (
        "# 话题详情（活跃区备注正文外置）\n\n"
        "> 活跃区表格的「备注」列超长时，正文移入本文件，表格留 `[详情#N]` 引用。\n"
        "> 编号与表格内的 `[详情#N]` 一一对应。\n\n"
    )
    block = []
    for num, fp, note in entries:
        block.append(f"## 详情#{num} · {fp}\n\n{note}\n")
    detail_path.write_text(existing.rstrip("\n") + "\n\n" + "\n".join(block), encoding="utf-8")
    return "\n".join(lines), [f"{fp}" for _, fp, _ in entries], detail_path


def compact_topic_registry(text: str, run: date, stale_days: int) -> tuple[str, list[str], list[str]]:
    """返回 (新文本, 迁入归档的行, 缩短备注的行)。"""
    lines = text.split("\n")
    secs = parse_sections(text)
    active_key = next((k for k in secs if k.startswith("## 一、")), None)
    archive_key = next((k for k in secs if k.startswith("## 二、")), None)
    if not active_key or not archive_key:
        raise SystemExit("未能定位活跃区/已归档区小节")

    a0, a1 = secs[active_key]
    b0, b1 = secs[archive_key]

    # 归档区表格的表头行位置（用于插入新行）
    archive_insert_at = b1
    for i in range(b0, b1):
        if lines[i].startswith("|") and "话题指纹" in lines[i]:
            # 跳过表头 + 分隔行，插在其后
            archive_insert_at = i + 2
            break

    moved: list[str] = []
    trimmed: list[str] = []
    keep_idx: list[int] = []
    year = run.year

    for i in range(a0, a1):
        line = lines[i]
        if not is_table_row(line):
            keep_idx.append(i)
            continue
        cells = row_cells(line)
        if len(cells) < 3 or cells[0] in ("话题指纹",) or set(cells[0]) <= set("-: "):
            keep_idx.append(i)
            continue

        dl = row_deadline_date(cells, year)
        last = row_last_confirmed(cells)
        reason = None

        if dl is not None and dl < run:
            reason = f"deadline {dl.isoformat()} 已过，按单节点口径归档"
        elif dl is None and last is not None:
            idle = (run - last).days
            if idle > stale_days:
                reason = f"无 deadline 且连续 {idle} 天未确认（冷却期 {stale_days} 天），归档停止跟踪"

        if reason:
            moved.append(build_archive_row(cells, reason, run))
        else:
            keep_idx.append(i)

    if not moved:
        return text, moved, trimmed

    # 组装新文本
    new_lines: list[str] = []
    new_lines.extend(lines[:a0])
    # 活跃区：保留 keep_idx 中属于 [a0,a1) 的行
    new_lines.extend(lines[i] for i in keep_idx if a0 <= i < a1)
    # 到归档区起点
    new_lines.extend(lines[a1:archive_insert_at])
    new_lines.extend(moved)
    new_lines.extend(lines[archive_insert_at:b1])
    new_lines.extend(lines[b1:])
    return "\n".join(new_lines), moved, trimmed


def shorten_archive_notes(text: str, keep: int) -> tuple[str, list[str]]:
    """把归档区超长备注截断；完整内容写入旁档。"""
    lines = text.split("\n")
    secs = parse_sections(text)
    archive_key = next((k for k in secs if k.startswith("## 二、")), None)
    if not archive_key:
        return text, []
    b0, b1 = secs[archive_key]
    over: list[str] = []
    for i in range(b0, b1):
        line = lines[i]
        if not is_table_row(line):
            continue
        cells = row_cells(line)
        if len(cells) < 4:
            continue
        note = cells[3]
        if len(note) <= keep:
            continue
        cells[3] = note[:keep] + "…（详见归档说明旁档）"
        lines[i] = "| " + " | ".join(cells) + " |"
        over.append(f"{cells[0][:60]}｜{note}")
    return "\n".join(lines), over


def externalize_channel_history(text: str, keep_runs: int) -> tuple[str, list[str], str]:
    """把 channel-health.md / topic-registry.md 头部说明区的「历史说明（保留）」段落外置。

    头部说明区每期追加一段「YYYY-MM-DD 历史说明（保留）」，实测 11 段占 12KB。
    运行时只需要「最后更新」那一段（本期状态），更早的段落只用于追溯。

    返回 (新文本, 被外置的段落首行列表, 被外置的正文)。
    """
    lines = text.split("\n")
    idxs = [i for i, l in enumerate(lines)
            if l.startswith("> **") and ("历史说明" in l or "最后更新" in l)]
    if len(idxs) <= keep_runs:
        return text, [], ""
    # 保留最后 keep_runs 段
    moved_idx = idxs[:-keep_runs]
    cut = moved_idx[0]
    # 被外置段落之间的分隔行（">"）也一并移走
    end = idxs[-keep_runs]
    moved_body = "\n".join(lines[cut:end]).rstrip()
    titles = [lines[i][:80] for i in moved_idx]
    pointer = [">", f"> 更早的 {len(moved_idx)} 期「历史说明（保留）」已外置到 `状态历史说明.md`，主文件仅保留最近 {keep_runs} 期。", ">"]
    new_lines = lines[:cut] + pointer + lines[end:]
    return "\n".join(new_lines), titles, moved_body



def externalize_channel_rows(text: str, state_dir: Path, min_keep: int) -> tuple[str, int, Path | None]:
    """把 channel-health.md 渠道状态表的「已知问题/替代方案」长文本外置。

    渠道表有 88 行，每行 50-1550 字符，其中「已知问题」列是长文本。运行时
    只需要「渠道 ID / 状态 / 最后确认」判断要不要用这个渠道，长文本只在真正
    遇到故障时才看。外置后表格瘦身、故障记录不丢。

    返回 (新文本, 外置行数, 详情文件路径或 None)。
    """
    lines = text.split("\n")
    heads = [i for i, l in enumerate(lines) if l.startswith("## ")]
    if not heads:
        return text, 0, None
    table_end = heads[0]
    entries: list[tuple[int, str, str]] = []
    counter = 0
    for i in range(0, table_end):
        line = lines[i]
        if not is_table_row(line):
            continue
        cells = row_cells(line)
        if len(cells) < 5 or not cells[0].startswith("`"):
            continue
        last = cells[-1]
        if len(last) <= min_keep:
            continue
        counter += 1
        entries.append((counter, cells[0], " | ".join(cells)))
        cells[-1] = f"[行详情#{counter}]"
        lines[i] = "| " + " | ".join(cells) + " |"

    if not entries:
        return "\n".join(lines), 0, None

    detail_path = state_dir / "渠道详情.md"
    existing = detail_path.read_text(encoding="utf-8") if detail_path.exists() else (
        "# 渠道详情（状态表长文本外置）\n\n"
        "> `channel-health.md` 渠道状态表的最后一行（已知问题 / 替代方案等）超长时，\n"
        "> 整行内容移入本文件，主表留 `[行详情#N]` 引用。编号一一对应。\n\n"
    )
    block = []
    for num, cid, full in entries:
        block.append(f"## 行详情#{num} · {cid}\n\n{full}\n")
    detail_path.write_text(existing.rstrip("\n") + "\n\n" + "\n".join(block), encoding="utf-8")
    return "\n".join(lines), len(entries), detail_path



def compact_channel_health(text: str, keep_logs: int) -> tuple[str, list[str]]:
    """把 channel-health.md 的历史更新日志小节外置，主文件只保留最近 keep_logs 期。

    为什么要拆：更新日志区每期追加一个小节，实测 10 期累积 70KB，占文件 63%。
    但运行时真正需要的是「渠道状态表」（头部，每期刷新 last_verified）+ 最近
    1–2 期日志（本期新增/变更）。历史日志只在追溯某个渠道何时开始故障时才看。

    返回 (新文本, 被外置的小节标题列表, 被外置的正文)。
    """
    lines = text.split("\n")
    # 本文件的日志区布局（实测）：
    #   [头部说明 + 渠道状态表]
    #   ## 更新日志            ← 通用段，其下是 ### YYYY-MM-DD 子段（存放较早期次）
    #   ## 更新日志 · 2026-XX-XX（…） ← 每个近期期次一个 h2
    # 通用段整体属于「较早期次」，日期 h2 段是更新的。保留最近 keep_logs 个日期 h2，
    # 通用段与其余日期段整体外置。
    dated = [i for i, l in enumerate(lines)
             if l.startswith("## 更新日志") and re.search(r"20\d{2}-\d{2}-\d{2}", l)]
    generic = [i for i, l in enumerate(lines) if l.rstrip() == "## 更新日志"]
    if len(dated) <= keep_logs and not generic:
        return text, [], ""

    keep_from = dated[-keep_logs] if keep_logs > 0 and len(dated) >= keep_logs else (dated[0] if dated else len(lines))
    # 外置起点：通用段起点（若在 keep_from 之前）否则第一个日期段
    move_from = generic[0] if generic and generic[0] < keep_from else (dated[0] if dated else keep_from)
    if move_from >= keep_from:
        return text, [], ""

    head_part = lines[:move_from]
    moved_part = lines[move_from:keep_from]
    kept_part = lines[keep_from:]
    titles = [lines[i][:70] for i in dated if i < keep_from]
    if generic and generic[0] < keep_from:
        titles.insert(0, "## 更新日志（含早期期次 ### 子段）")
    pointer = ["", "---", "",
               f"> 历史更新日志（{len(titles)} 期）已外置到 `渠道更新日志.md`，主文件仅保留最近 {keep_logs} 期。",
               "> 需要追溯某渠道何时开始故障时，查阅旁档文件。", ""]
    return "\n".join(head_part + pointer + kept_part), titles, "\n".join(moved_part)


def main() -> None:
    ap = argparse.ArgumentParser(description="压缩早报状态文件：归档僵尸话题 + 截断归档区超长备注")
    ap.add_argument("project_root", help="项目根目录（含 早报状态/）")
    ap.add_argument("--apply", action="store_true", help="实际写盘（默认 dry-run）")
    ap.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS,
                    help=f"无 deadline 话题的冷却期天数，默认 {DEFAULT_STALE_DAYS}")
    ap.add_argument("--keep-note", type=int, default=ARCHIVE_NOTE_KEEP,
                    help=f"归档区备注保留字符数，默认 {ARCHIVE_NOTE_KEEP}")
    ap.add_argument("--keep-runs", type=int, default=2,
                    help="头部「历史说明（保留）」段落保留最近几期，默认 2")
    ap.add_argument("--keep-logs", type=int, default=2,
                    help="channel-health.md 主文件保留最近几期更新日志，默认 2")
    args = ap.parse_args()

    root = Path(args.project_root).resolve()
    state_dir = root / "早报状态"
    target = state_dir / "topic-registry.md"
    if not target.exists():
        print(f"❌ 找不到状态文件: {target}")
        sys.exit(1)

    run = date.today()
    original = target.read_text(encoding="utf-8")
    new_text, moved, _ = compact_topic_registry(original, run, args.stale_days)
    new_text, _hist_titles, _hist_body = externalize_channel_history(new_text, args.keep_runs)
    new_text, ext_list, detail_path = externalize_details(new_text, state_dir)
    new_text, over = shorten_archive_notes(new_text, args.keep_note)

    before = len(original.encode("utf-8"))
    after = len(new_text.encode("utf-8"))
    print(f"📄 {target}")
    print(f"   体积: {before:,} → {after:,} 字节（{after / before:.0%}）")
    print(f"   迁入归档: {len(moved)} 行")
    for row in moved[:12]:
        print(f"     - {row[:150]}")
    if len(moved) > 12:
        print(f"     … 另有 {len(moved) - 12} 行")
    print(f"   归档区超长备注截断: {len(over)} 行")
    print(f"   活跃区详情外置: {len(ext_list)} 行 → 话题详情.md" if ext_list else "   活跃区详情外置: 0 行")

    # ── channel-health.md：历史更新日志外置 ──
    ch_path = state_dir / "channel-health.md"
    ch_new = ch_original = None
    ch_titles: list[str] = []
    ch_moved = ""
    _hist_body = ""
    _ch_body = ""
    if ch_path.exists():
        ch_original = ch_path.read_text(encoding="utf-8")
        ch_new, ch_titles, ch_moved = compact_channel_health(ch_original, args.keep_logs)
        ch_new, ch_rows, ch_detail = externalize_channel_rows(ch_new, state_dir, args.keep_note)
        ch_new, _ch_titles, _ch_body = externalize_channel_history(ch_new, args.keep_runs)
        ch_before = len(ch_original.encode("utf-8")); ch_after = len(ch_new.encode("utf-8"))
        print(f"\n📄 {ch_path}")
        print(f"   体积: {ch_before:,} → {ch_after:,} 字节（{ch_after / ch_before:.0%}）")
        print(f"   外置历史更新日志: {len(ch_titles)} 期（保留最近 {args.keep_logs} 期）")
        print(f"   渠道表长文本外置: {ch_rows} 行 → 渠道详情.md")

    if not args.apply:
        # dry-run 不得留下任何写入痕迹：外置阶段产生的详情文件在此清掉
        if detail_path is not None and detail_path.exists():
            detail_path.unlink()
        if ch_detail is not None and ch_detail.exists():
            ch_detail.unlink()
        print("\n[dry-run] 未写盘。确认无误后加 --apply 执行。")
        return

    backup_dir = state_dir / ".backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = backup_dir / f"topic-registry.{stamp}.md"
    shutil.copy2(target, backup)
    target.write_text(new_text, encoding="utf-8")

    if ch_new is not None and ch_titles:
        backup_dir.mkdir(parents=True, exist_ok=True)
        ch_backup = backup_dir / f"channel-health.{stamp}.md"
        shutil.copy2(ch_path, ch_backup)
    if _hist_body.strip() or _ch_body.strip():
        hist_side = state_dir / "状态历史说明.md"
        existing_hist = hist_side.read_text(encoding="utf-8") if hist_side.exists() else (
            "# 状态历史说明（历史期次外置）\n\n"
            "> `topic-registry.md` 与 `channel-health.md` 头部说明区的「历史说明（保留）」段落，\n"
            "> 更早的期次整段移入本文件，主文件仅保留最近几期。\n\n"
        )
        parts = [existing_hist.rstrip("\n")]
        if _hist_body.strip():
            parts.append("## topic-registry.md 历史说明\n\n" + _hist_body)
        if _ch_body.strip():
            parts.append("## channel-health.md 历史说明\n\n" + _ch_body)
        hist_side.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
        print(f"   历史说明写入: {hist_side.name}")


        side = state_dir / "渠道更新日志.md"
        existing_log = side.read_text(encoding="utf-8") if side.exists() else (
            "# 渠道更新日志（历史期次外置）\n\n"
            "> 主文件 `channel-health.md` 只保留最近几期；更早的日志整段移入本文件。\n\n"
        )
        side.write_text(existing_log.rstrip("\n") + "\n\n" + ch_moved.lstrip("\n"), encoding="utf-8")
        ch_path.write_text(ch_new, encoding="utf-8")
        print(f"✅ channel-health 已写盘。备份: {ch_backup}")

    if over:
        side = state_dir / f"归档说明-{run.isoformat()}.md"
        body = f"# 归档区完整备注（{run.isoformat()} 截断时留存）\n\n"
        body += "\n\n".join(f"- {o}" for o in over)
        side.write_text(body, encoding="utf-8")
        print(f"   完整备注写入: {side.name}")

    print(f"✅ 已写盘。备份: {backup}")


if __name__ == "__main__":
    main()
