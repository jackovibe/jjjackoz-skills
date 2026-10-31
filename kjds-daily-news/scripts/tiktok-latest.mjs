// 从 TikTok 学院索引（tiktok-catalog.json）里筛出最近 N 天的政策/指南更新，逐篇取正文
//
// 跑法：
//   ego-browser nodejs -e "await import('file:///<skill>/scripts/tiktok-latest.mjs')"
//
// 环境变量：
//   TIKTOK_WORKDIR  工作区根目录，默认 process.cwd()
//   TIKTOK_DAYS     回看天数，默认 3（早报 lookback 是 2 天，留 1 天余量）
//   TIKTOK_BODY     每篇保留正文字符数，默认 2600
//   TIKTOK_MAX_ITEMS 单轮最多取多少篇正文，默认 40（官方集中更新日防爆量）
//
// 落盘口径（**不囤正文**）：
//   本文件每次全量重写，只含「近 TIKTOK_DAYS 天内发布」的条目，窗口外的正文随下一次运行消失。
//   catalog 只存元数据（id/title/date/url），正文永远不进 catalog。
//
// 输出：<workdir>/早报状态/tiktok-latest.json
//   items[].change = NEW_ID（上期没有）| DATE_CHANGED（有但页面日期变了）| SAME
//   → 早报步骤 3/4 只需读这个文件，不必再实时访问网络

import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";

const WORKDIR = process.env.TIKTOK_WORKDIR || process.cwd();
const DAYS_BACK = Number(process.env.TIKTOK_DAYS || 3);
const BODY_CHARS = Number(process.env.TIKTOK_BODY || 2600);
const MAX_ITEMS = Number(process.env.TIKTOK_MAX_ITEMS || 40);
const STATE_DIR = path.join(WORKDIR, "早报状态");
const CATALOG = path.join(STATE_DIR, "tiktok-catalog.json");
const OUT = path.join(STATE_DIR, "tiktok-latest.json");

function textOf(html) {
  let s = html.replace(/<script[\s\S]*?<\/script>/gi, " ").replace(/<style[\s\S]*?<\/style>/gi, " ");
  s = s.replace(/<[^>]+>/g, " ").replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/&#x27;/g, "'").replace(/&quot;/g, '"');
  return s.replace(/\s+/g, " ").trim();
}

function parseDate(s) {
  const m = (s || "").match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (!m) return null;
  return new Date(Number(m[3]), Number(m[1]) - 1, Number(m[2]));
}

const cat = JSON.parse(await readFile(CATALOG, "utf8"));
let prevItems = [];
try {
  prevItems = JSON.parse(await readFile(OUT, "utf8")).items || [];
} catch {}

const cutoff = new Date();
cutoff.setHours(0, 0, 0, 0);
cutoff.setDate(cutoff.getDate() - DAYS_BACK);

const targets = (cat.pages || []).filter(p => {
  const d = parseDate(p.date);
  return d && d >= cutoff;
}).sort((a, b) => (parseDate(b.date) || 0) - (parseDate(a.date) || 0));  // 新的优先

console.log("cutoff=" + cutoff.toISOString().slice(0, 10) + " targets=" + targets.length);

let picked = targets;
if (targets.length > MAX_ITEMS) {
  picked = targets.slice(0, MAX_ITEMS);
  console.log("TRUNC 命中 " + targets.length + " 篇 > 上限 " + MAX_ITEMS + "，按日期取最新 " + MAX_ITEMS + " 篇（不囤正文）");
}

const task = await taskSpace("tiktok latest fetch");
const page = task.page("p1");

// 建同源上下文：必须 waitUntil=domcontentloaded，否则默认等 load 会 15s 超时，
// 页面留空壳（origin=null）→ 后续 page.fetch 全部 CORS 失败
async function ensureContext(url, tries = 3) {
  for (let i = 0; i < tries; i++) {
    try {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 25000 });
    } catch (e) {
      console.log("goto retry " + (i + 1) + " : " + String(e).slice(0, 80));
    }
    await new Promise(r => setTimeout(r, 1500));
    try {
      const ok = await page.evaluate(() => ({ host: location.host, len: document.body ? document.body.innerText.length : 0 }));
      if (ok && ok.host === "seller-us.tiktok.com" && ok.len > 800) {
        console.log("ctx-ready len=" + ok.len);
        return true;
      }
    } catch {}
  }
  return false;
}

const ctxOk = await ensureContext((picked[0] || targets[0] || {}).url || "https://seller-us.tiktok.com/university/essay?knowledge_id=2084805237114630&lang=en");
if (!ctxOk) {
  console.error("FATAL 无法建立同源上下文，本轮不写盘（保留上期 tiktok-latest.json）");
  process.exit(2);
}

const prevMap = new Map(prevItems.map(i => [String(i.knowledge_id), i]));
const rows = [];

for (const t of picked) {
  let html = "";
  try {
    const r = await page.fetch(t.url);
    if (typeof r === "string") html = r;
    else if (r && typeof r.text === "function") html = await r.text();
    else if (r && typeof r.body === "string") html = r.body;
  } catch {
    console.log("FAIL " + t.knowledge_id);
    continue;
  }

  const txt = textOf(html);
  if (txt.length < 800) {
    // 抓空不覆盖：沿用上期正文
    const old = prevMap.get(String(t.knowledge_id));
    if (old) {
      rows.push({ ...old, change: "SAME", fetched_at: new Date().toISOString() });
      console.log("KEEP_OLD " + t.knowledge_id + "（本次抓空 " + txt.length + " 字符）");
    } else {
      console.log("EMPTY " + t.knowledge_id + "（本次抓空且无旧数据）");
    }
    continue;
  }

  let start = txt.indexOf("US Academy ›");
  if (start < 0) {
    const last = txt.lastIndexOf(t.title);
    start = last >= 0 ? last : Math.floor(txt.length / 2);
  }
  const body = txt.slice(start, start + BODY_CHARS);

  const old = prevMap.get(String(t.knowledge_id));
  const change = !old ? "NEW_ID" : (old.date && t.date && old.date !== t.date) ? "DATE_CHANGED" : "SAME";

  rows.push({
    knowledge_id: t.knowledge_id,
    title: t.title,
    date: t.date,
    url: t.url,
    section: (body.match(/US Academy › ([^0-9]{0,80})/) || [])[1] || "",
    body,
    change,
    fetched_at: new Date().toISOString()
  });
  console.log("OK " + change + " " + t.date + " | " + t.title.slice(0, 52));
}

await mkdir(STATE_DIR, { recursive: true });
await writeFile(OUT, JSON.stringify({
  fetched_at: new Date().toISOString(),
  days_back: DAYS_BACK,
  count: rows.length,
  changed: rows.filter(r => r.change !== "SAME").length,
  items: rows
}, null, 2), "utf8");

console.log("WROTE " + OUT + " rows=" + rows.length + " changed=" + rows.filter(r => r.change !== "SAME").length);
