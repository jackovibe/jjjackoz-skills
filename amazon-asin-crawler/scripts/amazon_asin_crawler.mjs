// Amazon ASIN crawler for the Codex in-app browser.
// This replaces the F12 console script: it drives the in-app browser through
// the browser-client runtime, reads each search page, follows pagination, and
// writes the deduplicated rows to a JSON file for the xlsx builder.

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const PLUGIN_ROOT_HINT = path.join(
  os.homedir(),
  ".codex",
  "plugins",
  "cache",
  "openai-bundled",
  "browser"
);

const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));

function localDateStamp(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}${month}${day}`;
}

export function dateSuffixedPath(
  dir,
  baseName,
  extension,
  { date = new Date(), maxIndex = 99 } = {}
) {
  const stamp = localDateStamp(date);
  let candidate = path.join(dir, `${baseName}-${stamp}.${extension}`);
  for (let index = 1; fs.existsSync(candidate) && index <= maxIndex; index++) {
    const suffix = String(index).padStart(2, "0");
    candidate = path.join(dir, `${baseName}-${stamp}-${suffix}.${extension}`);
  }
  return candidate;
}

function resolvePluginRoot() {
  const roots = [PLUGIN_ROOT_HINT];
  for (const root of roots) {
    if (fs.existsSync(path.join(root, "scripts", "browser-client.mjs"))) {
      return root;
    }
  }

  const base = path.join(
    os.homedir(),
    ".codex",
    "plugins",
    "cache",
    "openai-bundled",
    "browser"
  );
  if (fs.existsSync(base)) {
    const versions = fs
      .readdirSync(base)
      .filter((name) => /^\d/.test(name))
      .sort((a, b) => {
        const na = a.split(".").map(Number);
        const nb = b.split(".").map(Number);
        for (let i = 0; i < Math.max(na.length, nb.length); i++) {
          const va = na[i] || 0;
          const vb = nb[i] || 0;
          if (va !== vb) return vb - va;
        }
        return 0;
      });
    for (const version of versions) {
      const root = path.join(base, version);
      if (fs.existsSync(path.join(root, "scripts", "browser-client.mjs"))) {
        return root;
      }
    }
  }
  throw new Error("browser-client.mjs not found under the browser plugin");
}

async function getBrowser() {
  if (globalThis.agent?.browsers == null) {
    const root = resolvePluginRoot();
    const { setupBrowserRuntime } = await import(
      pathToFileURL(path.join(root, "scripts", "browser-client.mjs")).href
    );
    globalThis.agent = await setupBrowserRuntime();
  }
  return globalThis.agent.browsers.get("iab");
}

async function getTab(browser) {
  const existing = await browser.tabs.list();
  if (existing.length > 0) {
    return browser.tabs.get(existing[0].id);
  }
  const selected = await browser.tabs.selected();
  if (selected) {
    return selected;
  }
  return browser.tabs.new();
}

async function waitForPage(tab) {
  try {
    await tab.playwright.waitForLoadState({
      state: "domcontentloaded",
      timeoutMs: 30000,
    });
  } catch {
    // The page may already be interactive; the locator timeout below is the
    // authoritative check.
  }
  await tab.playwright.waitForTimeout(1200);
}

async function extractPage(tab) {
  return tab.playwright.evaluate(() => {
    const cards = Array.from(
      document.querySelectorAll('div[data-component-type="s-search-result"]')
    )
      .filter((card) => (card.dataset.asin || "").trim())
      .filter(
        (card) =>
          card.dataset.sponsored !== "1" &&
          card.getAttribute("data-component-type") !== "sp-sponsored-result"
      )
      .filter((card) => {
        const text = (card.textContent || "").toLowerCase();
        return !text.includes("sponsored") && !text.includes("ad ");
      })
      .slice(0, 48);

    const rows = cards.map((card) => {
      const asin = (card.dataset.asin || "").trim();

      let title = "无标题";
      for (const selector of [
        'h2 a span',
        'h2 span',
        '[data-cy="title-recipe"] h2 a span',
        '[data-cy="title-recipe"] h2 span',
        '.a-size-medium.a-color-base.a-text-normal',
        'h2 a',
      ]) {
        const el = card.querySelector(selector);
        if (el && el.textContent && el.textContent.trim()) {
          title = el.textContent.trim();
          break;
        }
      }
      if (title === "无标题") {
        const h2 = card.querySelector("h2");
        if (h2 && h2.textContent && h2.textContent.trim()) {
          title = h2.textContent.trim();
        }
      }

      let price = "无报价";
      const priceWhole = card.querySelector("span.a-price-whole");
      if (priceWhole) {
        const symbolEl = card.querySelector("span.a-price-symbol");
        const fractionEl = card.querySelector("span.a-price-fraction");
        const symbol = symbolEl ? symbolEl.textContent.trim() : "$";
        const whole = (priceWhole.textContent || "").trim().replace(/[^0-9]/g, "");
        const fraction = fractionEl ? fractionEl.textContent.trim() : "00";
        price = `${symbol}${whole}.${fraction}`;
      } else {
        const fallback =
          card.querySelector("span.a-color-price") ||
          card.querySelector("span.a-offscreen");
        if (fallback && fallback.textContent && fallback.textContent.trim()) {
          price = fallback.textContent.trim();
        }
      }

      let rating = "无评分";
      const ratingEl = card.querySelector("span.a-icon-alt");
      if (ratingEl && ratingEl.textContent) {
        const match = ratingEl.textContent.trim().match(/([\d.]+)\s*out of 5/i);
        rating = match ? `${match[1]} 星` : ratingEl.textContent.trim();
      }

      let reviewCount = "0";
      if (ratingEl) {
        let current = ratingEl;
        for (let depth = 0; depth < 5 && current; depth++) {
          current = current.parentNode;
          if (!current) break;
          const parentText = current.textContent || "";
          const match = parentText.match(/\(([\d,.]+K?)\)/i);
          if (match) {
            reviewCount = match[1].replace(/,/g, "").replace(/k$/i, "K");
            break;
          }
        }
      }

      const imgEl = card.querySelector("img.s-image");
      const img =
        imgEl && (imgEl.dataset.oldHires || imgEl.dataset.src || imgEl.src)
          ? imgEl.dataset.oldHires || imgEl.dataset.src || imgEl.src
          : "无";

      return {
        ASIN: asin,
        产品标题: title,
        产品价格: price,
        星级评分: rating,
        评论数量: reviewCount,
        产品首图链接: img,
      };
    });

    const next = document.querySelector(
      'a.s-pagination-next:not(.s-pagination-disabled)'
    );
    return {
      rows,
      nextHref: next ? next.href : null,
      pageUrl: location.href,
      pageText: (document.body ? document.body.innerText : "").slice(0, 800),
    };
  });
}

function isBotCheck(url, pageText) {
  const lowerUrl = url.toLowerCase();
  const lowerText = pageText.toLowerCase();
  return (
    lowerUrl.includes("captcha") ||
    lowerUrl.includes("/errors/validatecaptcha") ||
    /#captcha-form/.test(lowerText) ||
    lowerText.includes("enter the characters you see below") ||
    lowerText.includes("not a robot")
  );
}

function isLoginWall(url) {
  try {
    const parsed = new URL(url);
    return (
      parsed.hostname.includes("signin") ||
      parsed.pathname.startsWith("/ap/signin") ||
      parsed.pathname.startsWith("/ap/entry")
    );
  } catch {
    return false;
  }
}

export async function crawlAmazon({
  url,
  maxPages = 3,
  outputJsonPath,
  pluginRoot,
  keyword,
  tab: providedTab,
} = {}) {
  if (pluginRoot) {
    // Allow the caller to override the plugin path when a session uses a
    // different bundled browser version.
    globalThis.__codexBrowserPluginRoot = pluginRoot;
  }

  const tab = providedTab || (await getTab(await getBrowser()));
  await tab.goto(url);
  await waitForPage(tab);

  const allRows = [];
  const seen = new Set();
  let pagesScanned = 0;
  let nextHref = null;

  for (let page = 1; page <= maxPages; page++) {
    const snapshot = await extractPage(tab);
    const currentUrl = await tab.url();
    pagesScanned += 1;

    if (isBotCheck(currentUrl, snapshot.pageText)) {
      const result = {
        status: "blocked",
        message: "Amazon returned a robot/captcha check; solve it in the browser and rerun.",
        pagesScanned,
        rows: allRows,
        outputJsonPath,
      };
      if (outputJsonPath) {
        fs.writeFileSync(outputJsonPath, JSON.stringify(result, null, 2), "utf8");
      }
      return result;
    }

    if (isLoginWall(currentUrl)) {
      const result = {
        status: "login_required",
        message: "Amazon redirected to sign-in; log in in the browser and rerun.",
        pagesScanned,
        rows: allRows,
        outputJsonPath,
      };
      if (outputJsonPath) {
        fs.writeFileSync(outputJsonPath, JSON.stringify(result, null, 2), "utf8");
      }
      return result;
    }

    for (const row of snapshot.rows) {
      if (keyword) {
        row["关键词"] = keyword;
      }
      if (!seen.has(row.ASIN)) {
        seen.add(row.ASIN);
        allRows.push(row);
      }
    }

    nextHref = snapshot.nextHref;
    if (
      page >= maxPages ||
      !nextHref ||
      nextHref.startsWith("javascript:") ||
      nextHref === snapshot.pageUrl
    ) {
      break;
    }

    await tab.goto(nextHref);
    await waitForPage(tab);
  }

  const result = {
    status: "ok",
    pagesScanned,
    url,
    keyword,
    uniqueAsins: seen.size,
    rows: allRows,
    outputJsonPath,
  };
  if (outputJsonPath) {
    fs.writeFileSync(outputJsonPath, JSON.stringify(result, null, 2), "utf8");
  }
  return result;
}

export function buildSearchUrl(keyword, baseSiteUrl = "https://www.amazon.com") {
  const encoded = encodeURIComponent(String(keyword).trim());
  return `${baseSiteUrl.replace(/\/$/, "")}/s?k=${encoded}`;
}

async function runKeywordPool({
  keywords,
  baseSiteUrl,
  maxPages,
  concurrency,
  pluginRoot,
}) {
  const browser = await getBrowser();
  const tabs = [];
  for (let i = 0; i < Math.min(concurrency, keywords.length); i++) {
    tabs.push(i === 0 ? await getTab(browser) : await browser.tabs.new());
  }

  const queue = keywords.map((keyword, index) => ({ keyword, index }));
  const results = new Array(keywords.length);

  async function worker(tab, workerId) {
    while (queue.length > 0) {
      const job = queue.shift();
      const result = await crawlAmazon({
        url: buildSearchUrl(job.keyword, baseSiteUrl),
        maxPages,
        keyword: job.keyword,
        tab,
        pluginRoot,
      });
      results[job.index] = result;
    }
  }

  await Promise.all(tabs.map((tab, index) => worker(tab, index)));
  return results;
}

export async function crawlKeywords({
  keywords,
  baseSiteUrl = "https://www.amazon.com",
  maxPages = 3,
  outputJsonPath,
  concurrency = 1,
  pluginRoot,
} = {}) {
  const normalizedKeywords = (Array.isArray(keywords) ? keywords : [keywords])
    .map((keyword) => String(keyword).trim())
    .filter(Boolean);
  if (normalizedKeywords.length === 0) {
    throw new Error("keywords must contain at least one keyword");
  }

  const results = await runKeywordPool({
    keywords: normalizedKeywords,
    baseSiteUrl,
    maxPages,
    concurrency: Math.max(1, Math.min(concurrency, normalizedKeywords.length)),
    pluginRoot,
  });

  const merged = mergeKeywordResults(results);

  const result = {
    status: merged.status,
    keywords: normalizedKeywords,
    baseSiteUrl,
    maxPages,
    concurrency,
    pagesScanned: merged.pagesScanned,
    perKeywordStats: merged.perKeywordStats,
    issues: merged.issues,
    rows: merged.rows,
    outputJsonPath,
  };
  if (outputJsonPath) {
    fs.writeFileSync(outputJsonPath, JSON.stringify(result, null, 2), "utf8");
  }
  return result;
}

export function mergeKeywordResults(results) {
  const issues = [];
  let pagesScanned = 0;
  const seen = new Set();
  const rows = [];
  const perKeywordStats = [];
  for (const result of results) {
    pagesScanned += result.pagesScanned || 0;
    if (result.status === "blocked" || result.status === "login_required") {
      issues.push({
        keyword: result.keyword,
        status: result.status,
        message: result.message,
        pagesScanned: result.pagesScanned || 0,
      });
    }
    perKeywordStats.push({
      keyword: result.keyword,
      pagesScanned: result.pagesScanned || 0,
      uniqueAsins: result.uniqueAsins || (result.rows ? result.rows.length : 0),
      status: result.status,
    });
  }
  for (const result of results) {
    for (const row of result.rows || []) {
      if (!seen.has(row.ASIN)) {
        seen.add(row.ASIN);
        rows.push(row);
      }
    }
  }

  let status = "ok";
  if (issues.length > 0) {
    const allBlocked = issues.every((issue) => issue.status === "blocked");
    const allLogin = issues.every((issue) => issue.status === "login_required");
    status =
      issues.length === results.length
        ? allBlocked
          ? "blocked"
          : allLogin
            ? "login_required"
            : "partial"
        : "partial";
  }

  return { status, pagesScanned, perKeywordStats, issues, rows };
}

export async function runCrawl(options = {}) {
  const defaults = {
    url: "https://www.amazon.com/s?k=red+light+therapy+mask",
    maxPages: 3,
    outputJsonPath: dateSuffixedPath(
      MODULE_DIR,
      "asin_raw_results",
      "json"
    ),
  };
  return crawlAmazon({ ...defaults, ...options });
}

export async function runCrawlKeywords(options = {}) {
  const defaults = {
    keywords: ["red light therapy mask"],
    baseSiteUrl: "https://www.amazon.com",
    maxPages: 3,
    concurrency: 1,
    outputJsonPath: dateSuffixedPath(
      MODULE_DIR,
      "asin_raw_results",
      "json"
    ),
  };
  return crawlKeywords({ ...defaults, ...options });
}
