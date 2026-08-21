# Amazon Also Viewed ASIN 抓取 — 跨 Agent 使用说明

本 skill 是一个**零依赖、工具无关**的抓取工具：核心只有 1 个纯 Python 标准库脚本，
任何支持「读 SKILL.md + 跑脚本」的 agent 都能用。

## 文件结构

```
amazon-also-viewed/
├── SKILL.md              ← 给 agent 看的说明（触发词 + 用法 + 原理）
└── scripts/
    └── also_viewed.py    ← 唯一脚本，纯标准库，Python 3.8+
```

## 已支持/兼容的 Agent

| Agent | 怎么用 | 挂载位置 |
|---|---|---|
| **WorkBuddy** | 已安装在用户级 skills 目录，对话里说「爬 also viewed ASIN」自动触发 | `~/.workbuddy/skills/amazon-also-viewed/` |
| **Codex (OpenAI)** | 把本目录复制到 `~/.codex/skills/amazon-also-viewed/`，Codex 的 skill 发现机制会自动加载；或在对话里直接告诉它 `python <路径>/scripts/also_viewed.py <ASIN>` | `~/.codex/skills/` |
| **Claude Code** | 把本目录复制到 `~/.claude/skills/amazon-also-viewed/` | `~/.claude/skills/` |
| **Cursor** | 在 `.cursor/rules/` 里放一份 SKILL.md（或直接引用脚本路径） | 项目 `.cursor/rules/` |
| **任何 CLI agent** | 直接跑脚本即可，不依赖 agent 框架 | 任意位置 |

> 注：不同 agent 的 skills 目录可能随版本变化，若目录不存在则手动创建。
> 核心脚本 `scripts/also_viewed.py` 本身与 agent 无关，复制到任何机器都能 `python also_viewed.py <ASIN>` 运行。

## 快速验证

```bash
python scripts/also_viewed.py B0BNWD9XHV --no-detail   # 30 秒内出 ASIN 列表
```

## 输出

```
output/{ASIN}_also_viewed.xlsx  ← Excel 工作簿（默认输出）
output/{ASIN}_also_viewed.csv   ← CSV 表格（默认输出, utf-8-sig 带 BOM）
output/{ASIN}_also_viewed.html  ← 玻璃拟态报告（仅 --html 时生成）
output/{ASIN}_also_viewed.json  ← 结构化数据（仅 --json 时生成）
```

- 默认生成 XLSX + CSV（XLSX 为纯标准库生成，Excel/WPS 直接打开）；`--html` 额外生成 HTML 报告；`--json` 额外生成 JSON；`--no-detail` 只出 ASIN 列表。
- HTML 报告为深色玻璃拟态卡片布局，单文件无外部依赖，双击即看。

## 环境要求

- Python 3.8+（Windows / macOS / Linux 均可）
- 无需 pip install（仅用 urllib / re / json / csv / argparse 等标准库）
- 网络可达 amazon.com

## 常见问题

- **HTTP 被反爬拦截**（返回 "Continue shopping" / 非 200）：等 15-60 秒重试；
  连续失败可改用 Playwright 渲染方案（见 SKILL.md「为什么不需要浏览器」一节）。
- **输出目录**：默认在 `scripts/output/`，可用 `--out` 覆盖。
- **ASIN 数量波动**：每次抓取 40-44 个之间浮动属正常（亚马逊实时推荐）。
