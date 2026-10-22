# 跨境早报 HTML 设计规范

## 0. 先看这里（v2.10.0）

**不要手写 HTML。** 早报由 `scripts/render-report.py` 从 `candidates.json` 渲染：

```
python scripts/render-report.py --example > candidates.json
python scripts/render-report.py candidates.json --audit 早报审计
```

渲染器已实现本文档的全部结构（分区容器、卡片、fold 两段、KPI、倒计时、nav、scope-note、timeline、footer、内联脚本），并保证 26 项 validator 检查中的结构项**不可能出错**。

**本文件降级为视觉规范**：只在以下场景查阅——
- 改配色/字号/间距（样式变量在 `assets/report.css`）
- 新增视觉组件（先改 `report.css`，再改 `render-report.py` 的渲染函数）
- 排查渲染结果与预期不符

若渲染器与本文档冲突，**以渲染器为准**，并回头修正本文档。

## 技术约束

- **单文件HTML**: 所有CSS/JS内联，无任何外部CDN依赖
- **响应式布局**: 适配桌面和移动端（@media breakpoint: 760px 卡片降单列 / 640px 移动端紧凑）
- **固定主题分区列表**: 桌面端按五个主题分区顺序展示，移动端单列
- **玻璃拟态风格**: 半透明毛玻璃效果，backdrop-filter: blur(12px)
- **阅读进度条**: 顶部 2px 渐变条（`#pbar`），滚动驱动，纯内联 JS
- **回到顶部**: 右下浮动圆钮（`#toTop`），滚动 >480px 时显示

## 设计色板

```css
--bg-primary: #0c0c16;
--panel: rgba(255, 255, 255, 0.045);
--panel-hover: rgba(255, 255, 255, 0.075);
--card-bg: rgba(255, 255, 255, 0.04);
--card-border: rgba(255, 255, 255, 0.09);
--card-border-hover: rgba(255, 255, 255, 0.16);
--text-primary: #eef0ff;
--text-secondary: rgba(255, 255, 255, 0.62);
--text-muted: rgba(255, 255, 255, 0.36);
--accent: #a78bfa;
--accent-gradient: linear-gradient(135deg, #f0f0ff 0%, #a78bfa 100%);
--indigo: #6366f1;  --red: #ef4444;  --amber: #f59e0b;  --green: #10b981;  --blue: #3b82f6;
--mono: ui-monospace, SFMono-Regular, Consolas, 'Liberation Mono', monospace;
```

**等宽字体用法**：KPI 数值、`card-date`、倒计时 `T-N`、卡内 deadline 徽章统一使用 `--mono`，保证数字纵向对齐。

## 页面结构

### 1. Header 区域
- 使用实际 `<header>` 或带 `.header` class 的容器；统计只从该容器的可见文本读取，HTML 注释、`script`、`style` 中的数字不计入。
- 日期行（英文格式: "Wednesday · 2026.07.15"）
- 主标题（渐变文字: "跨境电商每日早报"）
- 副标题（`精选 X 条 · 采用 Y 个独立来源`）— **必须保留此行**，验证器据此校验计数
- **顶部 KPI 统计条**（`<div class="kpi-strip">`，4 格）— 五秒内回答"今天多少条、来自哪些源、要读多久、最急的是哪个"：

  | 格 | label | value | foot 示例 |
  |:--:|-------|-------|----------|
  | 1 | 本期资讯 | `.card` 总数 | 分布在 N 个分区 |
  | 2 | 独立来源 | `card-source` 去重数 | T0 官方 a · T1 行业 b · T2 社区 c |
  | 3 | 阅读时长 | 读摘要分钟数 | 展开「意义」约 N 分 |
  | 4 | 最近截止 | 倒计时最短的 `T-N` | 对应 deadline 名称与日期 |

  - 第 4 格加 `kpi-alert` class 自动转红；无倒计时时该格改为中性文案（如"本期无临近截止"）
  - **阅读时长口径**：按摘要+趋势的中文字数 ÷ 450 字/分钟取整；foot 注明展开折叠区后的时长
  - ⚠️ KPI 文案不得出现"精选 X 条"或"采用 X 个独立来源"字样，避免干扰 Header 计数正则

- **活动倒计时（仅在有已验证的官方日期时显示）** — 需满足：
  1. 已获得当年官方活动日期
  2. 官方日期来源通过验证
  3. 当前日期在预热窗口内
  4. 倒计时由 `run_date` 动态计算
  - 无可靠官方日期时不展示任何活动徽章
- **倒计时按紧迫度三档着色 + T-N 计数器**（`.countdown-item` 叠加档位 class）：

  | class | 剩余天数 | 颜色 | 用途 |
  |-------|:--------:|------|------|
  | `cd-high` | ≤7 天 | 红 `#fca5a5` | 必须本周处理 |
  | `cd-mid` | 8–30 天 | 琥珀 `#fcd34d` | 需排期 |
  | `cd-low` | >30 天 | 绿 `#6ee7b7` | 观察 |

  - 剩余天数用等宽字体写作 `T-N` 形式（如 `T-3`），置于 `<span>` 内
  - 倒计时下方保留图例 `<div class="legend">`（≤7 天 红 / 8–30 天 琥珀 / >30 天 绿）

### 2. 来源状态条
- **容器**：`<div class="source-bar">`（兼容历史 `<div class="channels-bar">`；验证器检测容器，缺失将判结构缺失）
- 每个 pill：`<span class="source-pill">来源名</span>`，对应一个**本期实际采用的来源**
- 仅展示本期有最终卡片的来源（不展示"尝试过但无结果"的渠道）
- pill 数量及去重后的 pill 集合必须与最终卡片中的非空 `card-source` 集合完全一致。
- 字体: 11px, 半透明白色
- **来源分级着色**（pill 与卡片来源徽章同时适用，按来源总表分级）：

  | class | 层级 | 视觉 | 判定 |
  |-------|:----:|------|------|
  | `src-t0` | T0 官方一手 | 绿色实心 | 官方公告、政府监管机构、官方博客 |
  | `src-t1` | T1 行业权威 | 蓝色实线描边 | 行业媒体、权威分析 |
  | `src-t2` | T2 社区线索 | 紫色虚线描边 | 社区讨论（知无不言、Reddit） |

- ⚠️ **CSS 优先级陷阱**：卡片来源徽章必须写作 `class="card-source src-t0"`，且在 CSS 中 `src-tX` 的样式须定义在 `.card-source` **之后**（或使用双 class 选择器 `.card-source.src-t0`）。否则同特异性会被 `.card-source` 基础样式覆盖，分级色不生效。

### 3. 吸顶分区导航
- `<div class="nav-bar">` 紧接 Header 之后，`position: sticky; top: 8px`，半透明深色底 + blur
- 5 个入口，与五个固定分区一一对应，含圆点色标与条数：`<button class="nav-item" data-target="sec-xxx"><i class="nav-dot nd-xxx"></i>分区名<b>N</b></button>`
- ⚠️ **必须用 `<button data-target>` 而非 `<a href="#xxx">`** —— 验证器 `check_aggregation_urls` 会把 `href="#sec-policy"` 这类同页 fragment 误判为聚合页 URL（`urlsplit()` 得到的 path 为空即判 True），导致 `AGGREGATION_URL` 失败拦截交付
- 每个分区容器须带 `id="sec-xxx"` 与 `scroll-margin-top: 76px`，点击由内联 JS 执行 `scrollIntoView`

### 4. 主题分区结构（5 个固定分区）

早报按 **5 个固定主题分区** 顺序渲染，每个分区独立成块：

| 顺序 | 分区名 | class 标识 | 主题色 | 归属口径 |
|:----:|:------|:----------:|:-----:|---------|
| 1 | 🟣 平台政策与费用 | `cat-policy` | `#6366f1` (indigo) | 平台方发出的：规则/功能/费用/平台扩张（**仅 Amazon / Walmart / TikTok Shop**） |
| 2 | 🔴 合规与监管 | `cat-reg` | `#ef4444` (red) | 政府/监管机构发出的：召回、认证、EPR、**税务与关务** |
| 3 | 🟡 物流与供应链 | `cat-logistics` | `#f59e0b` (amber) | 头程/仓/尾程/履约时效（不含税则申报） |
| 4 | 🟢 行业与市场 | `cat-market` | `#10b981` (emerald) | 大盘数据、平台格局、资本动态 |
| 5 | 🔵 卖家社区 | `cat-community` | `#3b82f6` (blue) | 知无不言精华帖、社区讨论 |

**分区容器结构**：
```html
<div class="section cat-policy">
  <div class="section-header">
    <span class="dot"></span>
    <span>平台政策与费用</span>
    <span class="count">0 条</span>
  </div>
  <!-- 有内容：.card 列表 -->
  <div class="card"> ... </div>
  <!-- 无内容：.empty 占位 -->
  <div class="empty">⚪ 今日暂无平台政策与费用更新</div>
</div>
```

**分区渲染规则**：
- 5 个分区**全部渲染**，顺序固定（policy→reg→logistics→market→community），不可省略任意分区
- 有内容的分区：内部为 `.card` 列表，`.section-header` 的 `.count` 显示该分区卡片数
- 无内容的分区：内部仅渲染 `.empty` 占位（不渲染任何 `.card`），`.count` 显示"0 条"
- 每个 `.card` 必须恰好位于一个固定分区；各分区 `.count` 之和必须等于全局卡片数；有卡片的分区不得同时出现 `.empty` 占位。
- `.section-header` 背景色 + 左侧 border 由 `cat-xxx` class 控制（见上方主题色）

**卡片结构（分区内）**：
- 标题（可点击，hover紫色+↗符号）：`<div class="card-title"><a href="...">` 或 `<a class="card-title" href="...">`；链接和可见标题文字均不能为空
- meta 行：`card-date` → `card-source` → `[可选 badge]` → `[可选 deadline 徽章]`
- **事实摘要**（仅陈述原文可验证内容，不加编辑判断）：`<div class="card-summary">`
- **影响 / 建议动作折叠区（每卡必带）**：`<details class="fold" open><summary>对卖家的意义</summary><div class="fold-body"><p class="fold-impact"><b>影响：</b>…</p><p class="fold-act"><b>建议动作：</b>…</p></div></details>`（**默认展开**，详见下方「影响 / 建议动作字段规范」）
- 底部链接按钮：`<a class="card-link" href="...">→ 原文链接</a>`
- 单文件资源必须随 HTML 提供：允许内联 CSS/JS、`data:` 或本页片段资源；禁止外部或相对 `src`/`href`/`srcset`、CSS `url()` 与 `@import` 依赖。内嵌图片的 `data:` URL 使用 `src`；当前 `srcset` 校验不支持含逗号的 data URL，不在 `srcset` 中使用。
- 卡片圆角: 12px（内边距 15px 16px 14px）；Hover: 背景变亮 + 上移1px + 边框变亮

**头条 Hero 卡（当日最高权重 1 条）**：
```html
<div class="card hero-card">
  <div class="hero-flag">头条</div>
  <div class="card-title"><a href="canonical_url">标题</a></div>
  <div class="card-meta">…</div>
  <div class="card-summary">…</div>
  <details class="fold" open><summary>对卖家的意义</summary><div class="fold-body"><p class="fold-impact"><b>影响：</b>…</p><p class="fold-act"><b>建议动作：</b>…</p></div></details>
  <a class="card-link" href="canonical_url">→ 原文链接</a>
</div>
```
- 跨整行（`grid-column: 1/-1`）、indigo 渐变底、更大字号
- ⚠️ **必须保留 `card-title` class**：只能写 `<div class="card-title">`，**不得**改成 `hero-title` 之类的独立 class，否则 `check_card_title_link_present` 找不到标题链接而失败。字号差异通过 `.hero-card .card-title` 后代选择器实现

**卡内 deadline 徽章（可选）**：
- 当卡片内容本身对应一个已验证 deadline 时，在 meta 行追加 `<span class="dl dl-mid">9/22 投产 T-10</span>`
- 档位与倒计时一致：`dl-high`（≤7 天红）/ `dl-mid`（8–30 天琥珀）/ `dl-low`（>30 天绿）
- 无 deadline 的卡片不加，不为了视觉统一而强行添加

#### 影响 / 建议动作字段规范（v2.8.0 起每卡必带，验证器 CARD_IMPACT）
- 每张 `.card`（含 Hero 卡、空分区除外——空分区无卡片）必须有且仅有一个 `<details class="fold">`，summary 文字固定为「对卖家的意义」
- `fold-body` 内固定两段，标签措辞不可改：
  - `<p class="fold-impact"><b>影响：</b>…</p>` —— 对卖家成本/履约/合规的具体后果
  - `<p class="fold-act"><b>建议动作：</b>…</p>` —— 可执行的下一步（含"观察项"级别动作，如"关注官方后续公告并核对后台设置"）
- 与事实摘要**视觉上分开**（折叠区本身即分隔）
- 使用"影响"、"建议"等准确措辞，不得伪装成原文事实
- 不包含无法从政策范围合理推导的结论，不包含具体运营参数（如"建议降价至$X"属于过度推导）
- **默认展开（2026-10-20 用户拍板）**：`<details class="fold" open>`，点击 summary 收起；summary 行右侧提示文字随状态切换——CSS 示例：`.fold summary::after{content:"点击展开";…}.fold[open] summary::after{content:"点击收起"}`

### 5. 趋势总结（结论条形式）
- 容器仍为 `<div class="trends-section">`（验证器检测该 class），标题「今日趋势总结」
- 每条趋势一个 `<div class="trend-item">`，结构：
  ```html
  <div class="trend-item">
    <div class="trend-head"><span class="trend-dot"></span><b>结论式小标题</b><span class="trend-tag">分类标签</span></div>
    <p>关键解读</p>
  </div>
  ```
- 小标题写**结论**（如"参考价从『卖家声明』变成『平台证据』"），不写中性栏目名
- 条数 4–7 条；表格形式（`trends-table`）已废弃，改为结论条以提升扫读效率

### 6. 本期口径声明块（v2.8.0 新增，验证器 SCOPE_NOTE）
- 位置：紧跟吸顶分区导航（`nav-bar`）之后、第一个主题分区之前
- 结构：`<div class="scope-note"><b>本期口径：</b>…</div>`，浅色提示条样式（半透明底 + 边框）
- 内容必须说明（一段即可，不用列表）：
  1. **收录窗口**：`仅收录 YYYY-MM-DD HH:mm — YYYY-MM-DD HH:mm（Asia/Shanghai）发布或明确更新的资讯`
  2. 旧政策处理口径（如"旧政策只进入临近节点提醒，并标注原始日期"）
  3. 复核轮增补说明（如有）：增补几条、各自原始发布日期是否单独标注
  4. 存疑信源标注（如有）：如"某条来自卖家邮件截图，已标注待官方复核"
- 窗口起点/终点必须与步骤4验证窗口与 `window` 字段、Footer 生成时间逻辑一致，不得虚构精确到分的时刻

### 7. 临近节点提醒时间线（v2.8.0 新增，验证器 TIMELINE_SECTION）
- 位置：趋势总结（`trends-section`）之后、Footer 之前
- 结构：
  ```html
  <div class="timeline-section">
    <div class="section-header"><span class="dot"></span><span>临近节点提醒</span></div>
    <div class="tl-item"><span class="tl-date">2026-11-18</span><div class="tl-body"><b>事项名</b>：一句话说明。<a href="canonical_url">来源</a></div></div>
    …
  </div>
  ```
- 数据源：`早报状态/topic-registry.md`「三、倒计时看板」+ 当期卡内已验证 deadline；只收**未来日期**（含当日 T-0）且来源已验证的节点，按日期升序
- 每条必须：日期用 `tl-date`（`YYYY-MM-DD`，等宽字体）+ 事项一句话 + 一个原文链接（`<a>` 绝对 https 具体文章页；聚合页 URL 会被验证器全局拦截）
- 节点数 0 条时：容器仍须渲染，内部放一行占位文字（如"⚪ 本期无 45 天内临近节点"）
- 与卡内 deadline 徽章分工：徽章挂在当日新闻卡上，时间线承载**非当日**的跨期节点——旧政策不得混入主题分区，只进时间线并标原始日期
- 样式：垂直时间轴线 + 圆点（≤7 天红点 / 8–30 天琥珀 / >30 天绿点，与倒计时三档同色系）

### 8. Footer
- 文字: `本期资讯生成于 YYYY-MM-DD HH:mm（Asia/Shanghai）`
- 字体: 12px, 透明度 0.25
- 注意：使用**实际生成时间**，而非计划调度时间

### 9. 交互脚本（内联，无依赖）
- 阅读进度条：`scroll` 事件按 `scrollY / (scrollHeight - innerHeight)` 更新 `#pbar` 宽度
- 回到顶部：`scrollY > 480` 时给 `#toTop` 加 `.show`
- 分区导航：`.nav-item` 点击读取 `data-target`，`scrollIntoView({behavior:'smooth'})`
- 全部用 `addEventListener(..., {passive:true})` 包裹，无 jQuery、无 CDN

## 分区主题色（固定，不可循环替换）

5 个分区各绑定一种固定主题色，由 `cat-xxx` class 控制背景与 dot 颜色：

```
cat-policy     #6366f1  (indigo)    平台政策与费用
cat-reg        #ef4444  (red)       合规与监管
cat-logistics  #f59e0b  (amber)     物流与供应链
cat-market     #10b981  (emerald)   行业与市场
cat-community  #3b82f6  (blue)      卖家社区
```

## 字体栈

```css
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC',
  'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
```

## 每条卡片内容规范

- **英文标题格式**: `"中文翻译 (English Original Title)"`
- **中文标题**: 直接使用原文标题
- **链接**: 必须使用步骤4验证通过的 `canonical_url`，不能是聚合页（渲染器直接取卡片 `url` 字段）
- **来源标注**: 写在卡片 meta 行的 `<span class="card-source src-tX">` 中，必须是第一手原始出处（知无不言也必须用此 class）；`src-tX` 按来源总表分级着色
- **发布时间**: 从原文页面提取的真实发布时间，写入 `<span class="card-date">YYYY-MM-DD</span>`
- **meta 顺序**: `card-date` → `card-source` → `[可选 badge]` → `[可选 deadline 徽章]`，date 必须在 source 之前
- **事实与解读分离**: 摘要区域只陈述原文事实，「影响 / 建议动作」折叠区（`fold-impact` / `fold-act`）承载解读与下一步，每卡必带
- **底部链接**: 每个卡片底部必须有 `<a class="card-link" href="canonical_url">→ 原文链接</a>`

### ⚠️ card-date 三条硬规则（2026-09-16 实战补充，违反即 exit 1）
1. **只准 `YYYY-MM-DD` 十字符**。带任何中文后缀都会触发 `check_date_format` 的 `INVALID_DATE`：
   - ❌ `2026-09-08 发布` / ❌ `2026-08-25 公文` / ❌ `2026-09（官方公告）`
   - ✅ `2026-09-08`，补充说明放进 `card-badge` 或摘要正文
2. **政策页 / 规则页 / 长期有效文书**：无新闻发布日时，用页面显式标注的 `Last updated on <date>` / `Updated <date>` 作为 card-date（例：沃尔玛 Marketplace Learn 保险政策页 `2025-12-12`）。**不要为了凑日期编造，也不要因为"没有发布日"就省略 card-date**（`check_card_meta_order` 要求每张卡都有）。
3. **相对时间必须折算**：Seller Central 论坛类页面只显示"N 小时前 / N 天前"，按 run_date 回推成绝对日期后在审计中标注"折算日期"。

### ⚠️ 链接与可达性判定（2026-09-16 实战补充）
- **一律写绝对 `https://`**：`http://` 会被 `check_card_bottom_link` 与 `check_card_links_absolute_https` 双重拦下。连标题链接与底部「→ 原文链接」按钮，两者必须完全一致。
- **可达性判定用 WebFetch，不要用严格 TLS 客户端下结论**。已知案例：`customs.gov.cn` 的 HTTPS **证书链不完整**（本机 PowerShell `Invoke-WebRequest` 报"未能为 SSL/TLS 安全通道建立信任关系"），但 WebFetch（标准 CA 链）可正常抓全文。**结论仍是写 https**，并在审计中登记该局限。
- **替换源前先查禁用名单**：想用某站替换不通的链接时，先确认其不在总表 T3 / validator `FORBIDDEN_DOMAINS` 内。典型案例：`ebrun.com`（亿邦动力）是 T3 禁用源，**不可**作为替换源。


## 自适应设计

```css
@media (max-width: 760px) {
  .cards { grid-template-columns: 1fr; }                          /* 卡片降单列 */
  .kpi-strip { grid-template-columns: repeat(2, minmax(0,1fr)); }  /* KPI 4→2 格 */
}
@media (max-width: 640px) {
  body { padding: 14px; }
  .header { padding: 24px 18px; }
  .header-title { font-size: 22px; }
  .section, .trends-section { padding: 18px 16px; }
  .card { padding: 15px 15px 14px; }
  .card-title { font-size: 14px; }
  .hero-card { padding: 16px 16px; }
  .hero-card .card-title { font-size: 16.5px; }
  .trend-tag { margin-left: 0; }                                   /* 标签换行不右浮 */
  /* 方案 A 已移除全局卡片编号 .card-number，分区结构无此元素 */
}
```

⚠️ **禁用 `a[href^="#"]` 锚点**：验证器 `check_aggregation_urls` 会把无 path 的 fragment URL 判为聚合页。分区导航与回到顶部一律用 `<button>` + JS，不要写 `<a href="#...">`。

## 2026-10-20 变更记录（v2.8.0，学自 Sorftime 跨境资讯日报站）
1. **卡片「影响 / 建议动作」每卡必带**：`fold-body` 内固定 `fold-impact`（影响：）+ `fold-act`（建议动作：）两段；原"可选卖家影响"升级为强制结构（验证器 CARD_IMPACT）
2. **本期口径声明块**（`scope-note`）：nav-bar 后、首分区前，亮明收录窗口/复核轮/存疑信源（验证器 SCOPE_NOTE）
3. **临近节点提醒时间线**（`timeline-section`）：趋势总结后、Footer 前，承载跨期 deadline（数据源 topic-registry 倒计时看板），旧政策只进时间线不混主题分区（验证器 TIMELINE_SECTION）
4. 新增小节编号后移：Footer→8、交互脚本→9；同步改 `scripts/render-report.py` 的渲染顺序

## 2026-09-12 变更记录（看板视觉升级，8 组件）
1. **顶部 KPI 统计条**（`kpi-strip`，4 格）：本期资讯 / 独立来源 / 阅读时长 / 最近截止；第 4 格 `kpi-alert` 自动转红
2. **倒计时紧迫度三档着色**：`cd-high`(≤7天红) / `cd-mid`(8–30天琥珀) / `cd-low`(>30天绿) + 等宽 `T-N` 计数 + 图例
3. **头条 Hero 卡**（`hero-card`）：头条跨整行升格，`hero-flag` 标识；**必须保留 `card-title` class**
4. **吸顶分区导航**（`nav-bar` / `nav-item` / `nav-dot`）：5 入口带色标与条数；**必须用 button + data-target，禁用 `#` 锚点**
5. **「对卖家的意义」默认折叠**（`details.fold`）：改用原生 `<details>`，默认收起，摘要行右侧提示"默认收起 · 点击展开"
6. **来源分级徽章**：`src-t0` 绿实心 / `src-t1` 蓝实线 / `src-t2` 紫虚线，pill 与卡片来源同步；**CSS 需置于 `.card-source` 之后或用双 class 选择器**
7. **卡内 deadline 徽章**：`dl-high/dl-mid/dl-low`，仅当卡片本身对应已验证 deadline 时添加
8. **趋势总结改结论条**：`trends-section` 容器不变，内部由 `trends-table` 改为 `trend-item` 列表，小标题写结论
9. **小改进**：顶部 2px 阅读进度条；右下「回到顶部」；数字/日期统一等宽字体；卡片圆角 14→12px、内边距 18→15px 提升同屏密度
10. **色板更新**：`--bg-primary` 改为 `#0c0c16`，新增 `--panel/--panel-hover/--accent/--indigo/--red/--amber/--green/--blue/--mono`；断点新增 760px（卡片单列）

## 2026-07-15 变更记录

1. **来源状态条重构**: 从"active/warn双态"改为"仅展示本期实际采用来源"，不再展示无结果渠道
2. **Header 副标题**: 从"覆盖X个渠道"改为"采用Y个独立来源"
3. **活动倒计时**: 移除"仅在6月显示"的固定规则，改为动态判断（需官方日期验证通过）
4. **Footer**: 从"以上资讯由自动化任务于今日早上8:30自动生成"改为"本期资讯生成于 YYYY-MM-DD HH:mm（Asia/Shanghai）"
5. **新增卖家影响字段**: 卡片增加可选"卖家影响"区域，与事实摘要分离

## 2026-07-18 变更记录（方案 A 分区结构适配）
1. **布局统一**：五个固定分区按顺序展示，桌面和移动端均不使用旧网格布局描述
2. **来源状态条容器**：明确外层 `<div class="source-bar">` 容器（验证器检测依赖），内部 `<span class="source-pill">`
3. **移除 cards-grid / card-number**：方案 A 无全局卡片编号，删除旧响应式残留
4. **分区主题色/结构**：新增第 3 节「主题分区结构（方案 A）」，绑定 `cat-xxx` class 与固定主题色
