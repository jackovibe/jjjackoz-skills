#!/usr/bin/env node
// Amazon ASIN crawler standalone CLI.
// Works with any agent (Codex, WorkBuddy, Claude, etc.) that can run Node and
// Playwright. It launches its own Chromium session and never depends on the
// Codex in-app browser runtime.

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));
const CRAWLER_PATH = path.join(MODULE_DIR, "amazon_asin_crawler.mjs");

const KNOWN_PLAYWRIGHT_ROOTS = [
  process.env.PLAYWRIGHT_MODULE_PATH,
  path.join(os.homedir(), ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies", "node", "node_modules", "playwright"),
].filter(Boolean);

function parseArgs(argv) {
  const options = {
    keywords: [],
    maxPages: 3,
    concurrency: 1,
    site: "https://www.amazon.com",
    outputJson: null,
    channel: null,
    headed: false,
    playwrightModule: null,
  };

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    const next = () => argv[++i];
    switch (arg) {
      case "--keywords":
      case "--keyword": {
        const value = next();
        options.keywords.push(
          ...String(value)
            .split(/[;,]/)
            .map((keyword) => keyword.trim())
            .filter(Boolean)
        );
        break;
      }
      case "--max-pages":
        options.maxPages = Number(next());
        break;
      case "--concurrency":
        options.concurrency = Math.max(1, Number(next()));
        break;
      case "--site":
      case "--base-site-url":
        options.site = String(next()).replace(/\/$/, "");
        break;
      case "--output-json":
      case "--output":
        options.outputJson = next();
        break;
      case "--channel":
        options.channel = next();
        break;
      case "--playwright-module":
        options.playwrightModule = next();
        break;
      case "--headed":
        options.headed = true;
        break;
      case "--help":
      case "-h":
        printHelp();
        process.exit(0);
        break;
      default:
        if (arg.startsWith("-")) {
          throw new Error(`Unknown option: ${arg}`);
        }
        options.keywords.push(...String(arg).split(/[;,]/).map((k) => k.trim()).filter(Boolean));
    }
  }

  if (options.keywords.length === 0) {
    throw new Error("At least one keyword is required (--keywords \"kw1;kw2\")");
  }
  return options;
}

function printHelp() {
  console.log(`Usage:
  node run_crawl_standalone.mjs --keywords "red light therapy mask;led face mask" [options]

Options:
  --keywords "a;b;c"       Keywords separated by ; or ,
  --max-pages 3            Pages per keyword (default 3)
  --concurrency 1          Parallel tabs (default 1)
  --site URL               Amazon site base URL (default https://www.amazon.com)
  --output-json PATH       Output JSON path (default cwd/asin_raw_results-YYYYMMDD.json)
  --channel chrome         Chromium channel: chrome, msedge, or omit for bundled Chromium
  --playwright-module PATH Playwright package directory or index file
  --headed                 Show the browser window
`);
}

async function loadPlaywright(explicit) {
  const candidates = [];
  if (explicit) candidates.push(explicit);
  try {
    candidates.push(require.resolve("playwright"));
  } catch {}
  candidates.push(...KNOWN_PLAYWRIGHT_ROOTS);

  let lastError;
  for (const candidate of candidates) {
    if (!candidate) continue;
    try {
      const target = /(index\.mjs|index\.js)$/.test(candidate)
        ? candidate
        : path.join(candidate, "index.mjs");
      if (!fs.existsSync(target)) continue;
      const resolved = await import(pathToFileURL(target).href);
      const chromium = resolved.chromium || resolved.default?.chromium;
      if (!chromium) continue;
      return { chromium };
    } catch (error) {
      lastError = error;
    }
  }
  throw new Error(
    `Playwright was not found. Install it (npm i playwright && npx playwright install chromium) or set --playwright-module. Last error: ${lastError?.message || "unknown"}`
  );
}

async function launchBrowser(playwright, channel, headed) {
  const attempts = channel ? [channel] : ["__bundled__", "chrome", "msedge"];
  let lastError;
  for (const candidate of attempts) {
    try {
      const options = { headless: !headed };
      if (candidate !== "__bundled__") options.channel = candidate;
      return await playwright.chromium.launch(options);
    } catch (error) {
      lastError = error;
    }
  }
  throw new Error(
    `Could not launch a Chromium browser. Try --channel chrome or --channel msedge. Last error: ${lastError?.message || "unknown"}`
  );
}

function adaptPage(page) {
  return {
    async goto(url) {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
    },
    async url() {
      return page.url();
    },
    playwright: {
      async evaluate(fn) {
        return page.evaluate(fn);
      },
      async waitForLoadState({ state = "domcontentloaded", timeoutMs = 30000 } = {}) {
        await page.waitForLoadState(state, { timeout: timeoutMs });
      },
      async waitForTimeout(ms) {
        await page.waitForTimeout(ms);
      },
    },
  };
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const crawler = await import(pathToFileURL(CRAWLER_PATH).href);
  const playwright = await loadPlaywright(options.playwrightModule);
  const browser = await launchBrowser(playwright, options.channel, options.headed);

  const outputJson =
    options.outputJson ||
    crawler.dateSuffixedPath(process.cwd(), "asin_raw_results", "json");

  try {
    const tabCount = Math.min(options.concurrency, options.keywords.length);
    const tabs = [];
    for (let i = 0; i < tabCount; i++) {
      tabs.push(adaptPage(await browser.newPage()));
    }

    const queue = options.keywords.map((keyword, index) => ({ keyword, index }));
    const results = new Array(options.keywords.length);

    async function worker(tab) {
      while (queue.length > 0) {
        const job = queue.shift();
        process.stdout.write(
          `[${job.index + 1}/${options.keywords.length}] ${job.keyword}\n`
        );
        results[job.index] = await crawler.crawlAmazon({
          url: crawler.buildSearchUrl(job.keyword, options.site),
          maxPages: options.maxPages,
          keyword: job.keyword,
          tab,
          outputJsonPath: null,
        });
      }
    }

    await Promise.all(tabs.map(worker));
    const merged = crawler.mergeKeywordResults(results);
    const payload = {
      status: merged.status,
      keywords: options.keywords,
      baseSiteUrl: options.site,
      maxPages: options.maxPages,
      concurrency: options.concurrency,
      pagesScanned: merged.pagesScanned,
      perKeywordStats: merged.perKeywordStats,
      issues: merged.issues,
      rows: merged.rows,
      outputJsonPath: outputJson,
    };
    fs.writeFileSync(outputJson, JSON.stringify(payload, null, 2), "utf8");

    console.log(
      JSON.stringify(
        {
          status: merged.status,
          keywords: options.keywords.length,
          pagesScanned: merged.pagesScanned,
          rows: merged.rows.length,
          uniqueAsins: new Set(merged.rows.map((row) => row.ASIN)).size,
          perKeywordStats: merged.perKeywordStats,
          issues: merged.issues,
          outputJsonPath: outputJson,
        },
        null,
        2
      )
    );
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error.message || error);
  process.exitCode = 1;
});
