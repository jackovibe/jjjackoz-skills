---
name: amazon-also-viewed
description: 抓取亚马逊商品页 "Customers who viewed this item also viewed" 推荐模块的全部竞品 ASIN（含标题/价格/评分/评论数），输出 JSON + CSV。仅需 Python 标准库，零第三方依赖，任何 agent（WorkBuddy / Codex / Claude Code / Cursor 等）均可直接调用。当用户说「爬 also viewed ASIN」「抓取看了又看推荐」「提取竞品 ASIN 列表」「Customers who viewed also viewed」时触发。
disable-model-invocation: false
---

# Amazon "Also Viewed" ASIN 抓取 Skill

抓取亚马逊商品详情页中 **"Customers who viewed this item also viewed"** 模块的全部推荐 ASIN（约 40+ 个，对应 carousel 全部页数），并补全每个 ASIN 的标题、价格、评分、评论数，输出 JSON + CSV。

## 为什么不需要浏览器

亚马逊商品页 HTML 内嵌了 `data-a-carousel-options` 属性，其 `ajax.id_list` JSON 里包含整个推荐 carousel 的**全部**商品 ASIN（40+ 个），一次 HTTP 请求即可拿到，**无需浏览器渲染、无需翻页、无需点击**。详情字段则通过移动版页面 `/gp/aw/d/{asin}` 逐个补全（移动版反爬较宽松）。

> 备选方案（当 HTTP 被反爬拦截时）：Playwright 无头浏览器渲染 + 滚动触发懒加载 + 点击 carousel 翻页。但优先使用内嵌 JSON 方案。

## 前置条件

- Python 3.8+（**仅标准库**，无需 pip install 任何包）
- 网络可访问 amazon.com（美国站）

## 用法

```bash
# 完整跑：ASIN 列表 + 标题/价格/评分/评论，输出 XLSX + CSV
python scripts/also_viewed.py B0BNWD9XHV

# 只要 ASIN 列表（更快，不请求详情页）
python scripts/also_viewed.py B0BNWD9XHV --no-detail

# 需要 HTML 报告时额外生成
python scripts/also_viewed.py B0BNWD9XHV --html

# 需要 JSON 时额外生成
python scripts/also_viewed.py B0BNWD9XHV --json

# 自定义输出目录
python scripts/also_viewed.py B0BNWD9XHV --out /path/to/out
```

参数：

| 参数 | 说明 | 默认 |
|---|---|---|
| `asin` | 源商品 ASIN（必填） | - |
| `--no-detail` | 跳过详情补全，只输出 ASIN 列表 | 否 |
| `--html` | 额外生成玻璃拟态 HTML 报告 | 否 |
| `--json` | 额外生成 JSON 文件 | 否 |
| `--interval` | 详情请求间隔秒数（防反爬） | 1.0 |
| `--out` | 输出目录 | 脚本旁 `output/` |

## 输出

```
output/{ASIN}_also_viewed.xlsx  ← Excel 工作簿（默认输出，含表头与列宽）
output/{ASIN}_also_viewed.csv   ← CSV 表格（默认输出，utf-8-sig 带 BOM）
output/{ASIN}_also_viewed.html   ← 玻璃拟态卡片报告（仅 --html 时生成）
output/{ASIN}_also_viewed.json   ← 结构化数据（仅 --json 时生成）
```

表格列：`序号 | ASIN | 价格 | 评分 | 评论数 | 标题 | 商品链接`

HTML 报告（`--html`）：深色玻璃拟态卡片布局（渐变 CTA 按钮、统计面板、星级评分、商品直达链接），浏览器直接打开，适合晨会汇报或发给同事看。

## 工作原理（给 agent 的实现说明）

1. **请求商品页**：`GET https://www.amazon.com/dp/{ASIN}`，带桌面浏览器 UA + 先访问首页拿 cookie。
2. **提取 id_list**：定位 `Customers who viewed this item also viewed` 标题，在其前后 20-30KB 范围内提取内嵌 JSON 中的 ASIN。**必须兼容三种编码格式**（这是本 skill 踩过的坑）：
   - `"ajax":"{\"id_list\":\"[{\\\"id\\\":\\\"B0...\\\"}]\"}"`（字符串化，id_list 值带引号）
   - `"ajax":{"id_list":[{"id":"B0..."}]}`（真实 JSON 数组）
   - 兜底：模块容器内 `data-asin="B0..."` 属性
   - 亚马逊**每次请求返回的格式会随机变化**，三种都要试。
3. **补全详情**：逐个 `GET https://www.amazon.com/gp/aw/d/{asin}`（iPhone UA），从移动版页面提取 `<meta name="title">`、`.a-price-whole/.a-price-fraction`、`X out of 5 stars`、`N ratings`。
4. **输出**：写 JSON + CSV（CSV 用 utf-8-sig 带 BOM，Excel 直接打开不乱码）。

## 反爬注意事项

- 详情请求务必限速（`--interval` 默认 1.0s），44 个 ASIN 大约需要 1 分钟。
- 若商品页返回 "Continue shopping" 或 HTTP 非 200，是反爬拦截：等待 15-60 秒重试；连续失败则改用 Playwright 方案。
- 推荐 ASIN 列表每次抓取可能有 ±1~2 个波动（亚马逊实时推荐），属正常现象。
- 建议把输出重定向到日志文件而非管道截断：`python ... > run.log 2>&1`（管道 `| head` 会因 broken pipe 中断长任务）。

## 参考

- `scripts/also_viewed.py`：唯一脚本，纯标准库，可直接读源码修改。
- 首次开发记录见项目工作日志（2026-08-21）：反爬、格式兼容、沙箱限制等完整踩坑史。
