# kjds-daily-news · 跨境电商每日早报

> 面向 Amazon / Walmart / TikTok Shop 卖家的 AI Agent Skill：从一手信息源采集、四维验证、生成玻璃拟态 HTML 早报。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../../LICENSE)
![Python](https://img.shields.io/badge/python-3.9%2B-3776AB)

> 本 skill 是 [JJJackoz Skills](../../) 合集的一员。返回 [技能目录](../../README.md) 查看其他技能。

---

## 它解决什么问题

跨境电商资讯的两个老毛病：**链接打不开**（404/登录墙/聚合页）和**二手冒充一手**（公众号转述当官方公告）。

这个 Skill 把「可信度」放在「数量」前面：宁可 7 条每条可核验，不要 14 条一半是死链。为此它不是一份提示词，而是一套**带门禁的流水线**——采集有分区早停，验证有四维核对，出稿有 26 项结构校验，任何一项失败即拒绝交付。

## 核心机制

| 环节 | 做法 |
|:--|:--|
| **来源分级** | T0 官方发布 / T1 原创媒体 / T2 社区线索 / T3 聚合洗稿。最终链接只允许 T0/T1，T3 域名出现在任何 `href` 即拦截 |
| **分区版面** | ①平台政策与费用 ②合规与监管 ③物流与供应链 ④行业与市场 ⑤卖家社区，下限 13 条上限 21 条，① 区三平台（Amazon/Walmart/TikTok Shop）各至少 1 条 |
| **廉价预筛** | 先按结构硬淘汰（T3 域名/聚合页/重复 URL/跨期重复），**不做质量判断**——跨境标题常不含关键信息，按标题排序会误杀政策类 |
| **四维验证** | 只对 shortlist 跑：URL 可达 → 是具体文章页而非列表页 → 来源标签与域名一致 → 正文与摘要相符 |
| **定档制** | P0 卖家明天必须改做法 / P1 有影响但可缓 / P2 背景信息。P0 全局不超过 40%，超限降档不删卡 |
| **结构门禁** | `validate-report.py` 26 项检查（链接、域名白名单、日期合法性、分区配额、P0 比例、审计一致性），非零退出即禁止交付 |
| **状态复用** | `topic-registry.md` 记录跨期话题指纹与 deadline，避免「旧闻新发现」重复上报 |

## 快速开始

```bash
# 1. 装到 Agent 的 skills 目录（任选其一）
#    WorkBuddy:    ~/.workbuddy/skills/
#    Claude Code:  ~/.claude/skills/

git clone https://github.com/jackovibe/jjjackoz-skills.git
cp -r jjjackoz-skills/kjds-daily-news ~/.workbuddy/skills/

# 2. 依赖
python 3.9+   # 无第三方包，纯标准库

# 3. 在对话里触发
"生成今天的跨境早报"
```

Agent 会读取 `SKILL.md` 执行六步工作流，产物落在**当前项目目录**：

```
<你的项目>/
├── 跨境早报-YYYY-MM-DD.html      # 玻璃拟态单文件报告（无外部 CDN）
├── 早报审计/YYYY-MM-DD.md        # 入选/淘汰全记录，含根因
└── 早报状态/
    ├── topic-registry.md        # 跨期话题指纹 + deadline 倒计时
    └── channel-health.md        # 渠道可用性
```

## 脚本

| 脚本 | 作用 |
|:--|:--|
| `scripts/render-report.py` | 吃结构化 JSON 出 HTML + 审计，替代手写模板。结构错误在写盘前就被挡住 |
| `scripts/validate-report.py` | 26 项结构门禁，`exit != 0` 即禁止交付 |
| `scripts/build-index.py` | 把多期报告聚合为单文件期次索引页（搜索/月分组） |
| `scripts/compact-state.py` | 状态文件瘦身：僵尸话题归档 + 备注压缩（实测 数百 KB → 132KB，证据零丢失） |
| `scripts/advtest/` | 回归测试：43 个对抗样本 + 变异测试 + 渲染器回归 |

```bash
# 渲染一期
python scripts/render-report.py candidates.json --audit 早报审计

# 出一份空白输入骨架
python scripts/render-report.py --example > candidates.json

# 门禁
python scripts/validate-report.py 跨境早报-2026-10-22.html

# 回归（先 gen.py 生成样本，再跑）
python scripts/advtest/gen.py && python scripts/advtest/run_adv.py
python scripts/advtest/test_render.py
python scripts/advtest/test_v241_mutations.py
```

## 目录结构

```
kjds-daily-news/
├── SKILL.md                              # 主规则（六步工作流）
├── references/
│   ├── 跨境资讯一手信息源总表.md           # 来源唯一权威清单（T0–T3 + 频率 + 分区）
│   ├── selection-score.md                # 选稿判据（档位制，唯一裁决依据）
│   ├── html-spec.md                      # HTML 结构与 CSS 类名规范
│   ├── channel-health.md                 # 渠道状态空表模板
│   └── changelog.md                      # 版本历史（追溯用，执行时不读）
├── assets/report.css                     # 玻璃拟态样式
└── scripts/                              # 渲染 / 校验 / 索引 / 瘦身 / 回归
```

## 设计取舍（踩过的坑）

- **档位制而非分数制**：LLM 打 0–3 分必然聚集在 2 分，门槛失去区分度。三档定义强迫回答「卖家明天要不要改做法」。
- **验证放在 shortlist 上，不是全部候选**：全量验证的成本压垮单次运行，且大量候选本就过不了预筛。
- **预筛只砍结构，不砍质量**：「这条看着不重要」不是淘汰理由，已写进规则。
- **Tier A 必须有 ③ 区源**：初期 Tier A 全是政策源，导致「③区 ≥ N」永远不满足、早停永不触发，每期白跑 Tier B。
- **`sellercentral.amazon.com` 只认论坛路径**：`/news` 与 `/amazonsell/...seller-news` 都是登录墙，`/seller-forums/discussions` 才是公开的。

## 局限

- 需运行在具备联网抓取能力的 Agent 运行环境中，非独立可执行程序。
- `validate-report.py` 是**结构门禁**，查不出「版块页伪装成文章页」这类语义问题——那需要人工/模型判断。
- 来源总表按 2026 年实测维护，渠道随时可能改版或加登录墙，失效属常态，需按 `channel-health.md` 记录并替换。
- 中文报告，面向中国大陆跨境卖家；未做多语言输出。

## License

MIT，见仓库根目录 [LICENSE](../../LICENSE)。来源清单中的第三方站点版权归各自所有，本仓库仅登记域名与分级，不转载其内容。
