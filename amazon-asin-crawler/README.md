# amazon-asin-crawler

按一个或多个关键词抓取亚马逊搜索结果前3页的 ASIN、标题、价格、评分、评论数和首图链接，跨关键词按 ASIN 去重后输出一份 XLSX。

使用方式：直接对 Codex 说“抓取亚马逊 `<关键词>` 前3页 ASIN 列表”，或给出 5-8 个关键词要求合并成一份表格。

多关键词默认一个一个抓（`concurrency=1`），也可显式要求并行（`concurrency=2` 或 3），但并行会增加亚马逊风控/验证码概率。

## 组成

- `SKILL.md`：技能入口，包含触发方式、执行流程和约束。
- `scripts/amazon_asin_crawler.mjs`：Codex 内置浏览器抓取器，支持单关键词和多关键词合并去重。
- `scripts/build_asin_xlsx.py`：把抓取 JSON 转成 Excel。
- `agents/openai.yaml`：Codex UI 中的显示信息。

多关键词抓取时，JSON 内 `perKeywordStats` 记录每个关键词独立抓取数量（该关键词内部去重后），不生成每关键词独立表格；Excel 只输出合并去重后的结果。

## 其他 Agent 使用

Codex 之外（WorkBuddy、Claude 等）请使用：

```powershell
node "<你的技能目录>/scripts/run_crawl_standalone.mjs" --keywords "red light therapy mask;led face mask" --max-pages 3 --output-json "output.json"
```

需要 Node.js 和 Playwright（`npm i playwright && npx playwright install chromium`），或指定 `--playwright-module`。该 CLI 用自己的 Chromium 会话，不依赖 Codex 内置浏览器。

输出文件通常为：

- `<任务 outputs>/asin_raw_results-YYYYMMDD.json`
- `<任务 outputs>/亚马逊前3页ASIN列表-YYYYMMDD.xlsx`

同一天生成多个文档时，日期后追加 `-01`、`-02` 序号，例如 `亚马逊前3页ASIN列表-20260820-01.xlsx`。
