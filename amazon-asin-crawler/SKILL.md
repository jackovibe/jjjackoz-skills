---
name: amazon-asin-crawler
description: 抓取亚马逊搜索结果前3页的 ASIN、标题、价格、评分、评论数和首图链接，支持单关键词或多个关键词（5-8个）合并去重，并输出一份 XLSX。当用户用自然语言给出关键词，要求“抓取/搜索亚马逊 ASIN/产品列表/出 Excel”时使用；不适用于其他电商平台或非搜索结果页。
---

# Amazon ASIN Crawler

用户给一个或多个关键词（常见 5-8 个）后，打开每个关键词的亚马逊搜索结果页，抓取前3页自然结果，跨关键词按 ASIN 去重，合并生成一份 `亚马逊前3页ASIN列表.xlsx`，并把绝对路径交付给用户。合并表会带“关键词”列，标注该 ASIN 第一次命中的搜索词。

## 前置：连接内置浏览器

按 `codex-in-app-browser` skill 连接 Codex 内置浏览器（通过 `mcp__node_repl__js`）。本 skill 使用内置浏览器，不用 Chrome 主配置文件；当前内置浏览器没有无痕开关，也不要声明无痕。

## 执行流程

1. 把每个关键词 URL 编码后组成搜索地址，默认美国站：`https://www.amazon.com/s?k=<urlencoded keyword>`；用户指定站点时用对应域名。
2. 多关键词使用 `crawlKeywords`，单关键词可用 `crawlAmazon`。在 node_repl 中导入并运行 `scripts/amazon_asin_crawler.mjs`（用 `file://` 绝对路径，注意避免 REPL 变量重名），传入 `keywords`、`maxPages=3`、`outputJsonPath=<当前任务 outputs 目录>/asin_raw_results-YYYYMMDD.json`。当天已有同名文件时，用 `dateSuffixedPath(outputsDir, "asin_raw_results", "json")` 生成 `-01`、`-02` 后缀路径，避免覆盖。如果内置浏览器插件路径与脚本内置提示不一致，按 `codex-in-app-browser` 的 Bootstrap 路径通过 `pluginRoot` 参数覆盖。
3. 默认 `concurrency=1`：一个一个抓。除非用户明确要求提速，不要默认开并行；用户要求时可设 `concurrency=2` 或 `3`（多标签并行，验证码/风控概率更高）。
4. 检查返回的 `status`：
   - `ok`：全部关键词完成，继续生成 Excel。
   - `partial`：部分关键词成功、部分失败，保留成功数据，把失败项列入 `issues` 并告知用户。
   - `login_required` / `blocked`：全部被登录墙或验证码拦住，请用户在内置浏览器里登录或通过验证码后重跑；不要绕过验证码、登录墙或机器人检查。
5. 运行 `scripts/build_asin_xlsx.py`，把 JSON 转成同一 outputs 目录下的 `亚马逊前3页ASIN列表-YYYYMMDD.xlsx`。脚本默认使用日期后缀；传显式路径时，若该路径已存在会自动追加 `-01`、`-02`。
6. 用 openpyxl 只读加载核对：表头、数据行数、唯一 ASIN 数；然后只交付 Excel 的绝对链接（JSON 为中间产物，不交付），并汇报 `keywords`、`pagesScanned`、`perKeywordStats`、`rows`、`uniqueAsins`、状态。`perKeywordStats` 记录每个关键词独立抓取的数量（该关键词内部去重后），不生成每词独立表格。

## 脚本说明

- `scripts/amazon_asin_crawler.mjs`：ESM 模块，支持 `crawlAmazon`（单关键词）和 `crawlKeywords`（多关键词）；打开搜索页、逐页读取并翻页、跨关键词按 ASIN 去重；只抓非 sponsored/非广告自然位，每页最多 48 条。默认输出到模块目录，实际使用时显式传 `outputJsonPath`。
- `scripts/build_asin_xlsx.py`：读取 JSON 生成带表头的 Excel；有“关键词”字段时自动增加“关键词”列。可用第二个参数指定输出路径。

## 每关键词独立数量

合并 JSON 的 `perKeywordStats` 字段记录每个关键词独立抓取数量，结构如下：

```json
{"keyword": "red light therapy mask", "pagesScanned": 3, "uniqueAsins": 141, "status": "ok"}
```

不生成每关键词独立表格；交付时把这些数量汇报给用户。

## 约束

- 只读抓取公开搜索结果；不绕过验证码、登录墙、机器人检查，也不在浏览器中提交表单、登录、付款或发送数据。
- 多关键词默认串行，理由是同一内置浏览器会话下串行更稳、风控概率更低；并行只是可选加速，不保证更快或更稳。
- 输出写入当前任务的 outputs 目录，最终只交付 outputs 下 Excel 的绝对路径链接；JSON 为中间产物，仅内部保留、不交付。
- 若亚马逊改版导致字段缺失，保留已抓到的 JSON 并报告缺失字段，再决定是否调整选择器。

## 其他 Agent（WorkBuddy、Claude 等）使用

`amazon_asin_crawler.mjs` 中的 Codex 内置浏览器逻辑只在 Codex 会话里使用。非 Codex Agent 请改用 `scripts/run_crawl_standalone.mjs`，它用 Playwright 启动独立 Chromium，不依赖 Codex 浏览器运行时，也不使用 Codex 登录态。

前置要求：Node.js 18+，且可解析 `playwright` 包（`npm i playwright && npx playwright install chromium`），或通过 `--playwright-module` 指定本机 Playwright 包目录。

示例：

```powershell
node "<你的技能目录>/scripts/run_crawl_standalone.mjs" --keywords "red light therapy mask;led face mask" --max-pages 3 --output-json "<输出目录>/asin_raw_results-20260820.json"
```

常用参数：

- `--keywords "a;b;c"`：多个关键词，分号或逗号分隔。
- `--max-pages 3`：每个关键词抓取页数。
- `--concurrency 1`：并行标签数，默认串行。
- `--site https://www.amazon.com`：站点基地址。
- `--output-json PATH`：输出 JSON 路径；缺省按当天日期自动生成。
- `--channel chrome|msedge`：使用本机 Chrome/Edge；缺省尝试自带 Chromium。
- `--headed`：显示浏览器窗口，便于人工处理验证码。

该 CLI 与 Codex 内置浏览器版输出同一 JSON 结构（含 `perKeywordStats`），随后可继续用 `build_asin_xlsx.py` 生成 Excel。

## 输出文件命名

- Excel（交付物）：`亚马逊前3页ASIN列表-YYYYMMDD.xlsx`
- JSON（中间产物，不交付）：`asin_raw_results-YYYYMMDD.json`；JSON 内 `perKeywordStats` 记录每个关键词独立抓取数量，用于合并前/合并后数量对照。
- 同一天生成多个文档时，在日期后追加两位序号：`-01`、`-02`，如 `亚马逊前3页ASIN列表-20260820-01.xlsx`。
- 若一次运行同时产生多份独立结果（例如多批次关键词），每份都按上述规则独立编号，并在交付说明里列出每份文件对应的批次或关键词。
