# 🐴 JJJackoz Skills

日常工作中打磨的 AI Agent 技能（SKILL.md 格式），全部开源，拿来即用。

> **Strive for excellence, and success will come along.** — 追求卓越，成功将伴你而行。

## 技能目录

| 技能 | 一句话 | 讲解 |
|------|--------|------|
| [amazon-asin-crawler](amazon-asin-crawler/) | 按关键词抓亚马逊搜索结果前3页 ASIN 列表，多关键词合并去重，输出 XLSX | [README](amazon-asin-crawler/README.md) |
| [amazon-also-viewed](amazon-also-viewed/) | 抓商品页 "Customers who viewed this item also viewed" 推荐的全部竞品 ASIN（含标题/价格/评分/评论），输出 JSON + CSV | [README](amazon-also-viewed/README.md) |

## 安装方式

### 方式一：让 Agent 帮你装（推荐）

在支持 Agent Skills 的工具（WorkBuddy / Codex / Claude Code / Cursor 等）中对 Agent 说：

```
帮我安装这个 skill：https://github.com/jackovibe/jjjackoz-skills/tree/main/<skill-name>
```

### 方式二：手动安装

```bash
# 克隆仓库
git clone https://github.com/jackovibe/jjjackoz-skills.git

# 复制到你的 Agent 技能目录（以 WorkBuddy / Claude Code 为例）
cp -r jjjackoz-skills/amazon-asin-crawler ~/.workbuddy/skills/
cp -r jjjackoz-skills/amazon-also-viewed ~/.workbuddy/skills/
# 或
cp -r jjjackoz-skills/amazon-asin-crawler ~/.claude/skills/
```

## 技能详解

### 🕷️ amazon-asin-crawler — 亚马逊 ASIN 抓取

**一句话**：给关键词，出表格。抓取亚马逊搜索结果前3页的 ASIN、标题、价格、评分、评论数和首图链接，支持 5-8 个关键词合并去重，最终交付一份 XLSX。

**适用场景**：
- 选品调研：输入品类关键词，批量拉取竞品 ASIN 清单
- 广告投放：收集自然排名靠前的商品，作为竞品追踪对象

**不适用场景**：
- 其他电商平台（淘宝、eBay 等）
- 需要登录后数据或广告位数据（本技能只抓公开自然结果）

**触发示例**：
- "抓取 phone case 前3页 ASIN 列表"
- "用这5个关键词抓亚马逊产品，合并成一份 Excel"

**链接**：[SKILL.md](amazon-asin-crawler/SKILL.md) · [README](amazon-asin-crawler/README.md)

---

### 👀 amazon-also-viewed — 看了又看竞品挖掘

**一句话**：给一个 ASIN，挖出一整排竞品。抓取商品页 "Customers who viewed this item also viewed" 模块的全部推荐 ASIN（40+ 个），补全标题、价格、评分、评论数，输出 JSON + CSV。

**适用场景**：
- 竞品分析：从头部竞品页延伸挖掘同品类其他玩家
- 定价参考：快速获取同类商品价格带和评分分布

**不适用场景**：
- 需要商品详情页完整描述/图片（本技能只取推荐模块字段）
- 需要历史数据（推荐是实时变化的，每次抓取 ±1~2 个波动属正常）

**触发示例**：
- "爬一下 B07SCL613T 的 also viewed ASIN"
- "提取看了又看推荐，输出 CSV"

**链接**：[SKILL.md](amazon-also-viewed/SKILL.md) · [README](amazon-also-viewed/README.md)

---

## 关于

这些技能是日常工作中打磨出来的工具，开源共享，欢迎 star、fork、提 issue。

## License

[MIT License](LICENSE) — 自由使用、修改、再分发。
