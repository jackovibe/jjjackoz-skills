// TikTok Shop 官方学院（seller-us.tiktok.com）全库索引器 —— BFS 建库
//
// 原理：essay 页 SSR HTML 内嵌本篇所在章节的目录（实测 14–31 个 knowledge_id），
//      不同章节的邻接集合互不重叠（三页两两重叠 0/0/2）→ 可当邻接表做 BFS 扩展。
//      学院首页 /university/home 是 CSR 空壳（innerText=0、knowledge_id 链接 0 个），不能当发现入口。
//
// 跑法（ego lite 自带 nodejs 运行时）：
//   ego-browser nodejs -e "await import('file:///<skill>/scripts/tiktok-catalog.mjs')"
// 配置走包装文件（process.env 不会从 Bash 透传给 ego 的 node）：
//   process.env.TIKTOK_WORKDIR = "<你的工作区绝对路径>";
//   process.env.TIKTOK_MAX = "250";
//   await import("file:///<skill>/scripts/tiktok-catalog.mjs");
//
// 环境变量：
//   TIKTOK_WORKDIR     工作区根目录，默认 process.cwd()
//                      seeds 读 <workdir>/scripts/tiktok-seeds.json
//                      catalog 写 <workdir>/早报状态/tiktok-catalog.json
//   TIKTOK_MAX         本轮最多爬多少「新」页，默认 250（同源 fetch 单篇约 0.5s）
//   TIKTOK_CAP         索引总量硬上限，默认 300。到顶即停，不再向队列要新页
//   TIKTOK_REBUILD_MAX rebuild 模式下最多重走多少已知页，默认 400
//   TIKTOK_RESET       =1 丢弃已存 frontier 与索引，从 seeds 重建
//
// 三种模式（自动判断，日志第一行会打印）：
//   frontier —— 有上次剩下的队列，直接续跑（正常情况）
//   seed     —— 没有队列但有未爬过的 seed，先补种子
//   rebuild  —— 没有队列且 seed 全爬过、却没有 frontier（老版本 catalog 遗留）：
//               重走已知页把邻接表重新算出来，否则会永远停在当前页数不动
//
// 🔴 定位：限容量定向索引，**不做全库**（2026-10-31 定策）。
//    学院全库约 2,600 篇，但早报只需要「近期有更新 + 政策类」这一小块：
//    全库要抓 2,600 页（顺跑约 20 分钟，断网即白跑），落盘的绝大多数是与早报无关的历史文档；
//    正文另存在 tiktok-latest.json（只留近 N 天），索引再全也不会让早报多一条。
//    因此 TIKTOK_CAP（默认 300）是硬上限：known 到顶即停，队列剩余丢弃，日志打 CAP_REACHED。
//    要覆盖新章节 → 往 tiktok-seeds.json 补定向种子，不要靠扩张总量。
//
// ⚠️ 250 页/轮是「每轮预算」，与 CAP 是两件事：预算控制单次运行时长，CAP 控制本地总量。

import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";

const WORKDIR = process.env.TIKTOK_WORKDIR || process.cwd();
const MAX_PAGES = Number(process.env.TIKTOK_MAX || 250);
const CAP = Number(process.env.TIKTOK_CAP || 300);
const REBUILD_MAX = Number(process.env.TIKTOK_REBUILD_MAX || 400);
const RESET = process.env.TIKTOK_RESET === "1";
const SEEDS_FILE = path.join(WORKDIR, "scripts", "tiktok-seeds.json");
const STATE_DIR = path.join(WORKDIR, "早报状态");
const CATALOG = path.join(STATE_DIR, "tiktok-catalog.json");
const ENTRY = "https://seller-us.tiktok.com/university/essay?knowledge_id=";

async function readJson(p, fallback) {
  try {
    return JSON.parse(await readFile(p, "utf8"));
  } catch {
    return fallback;
  }
}

const seeds = await readJson(SEEDS_FILE, []);
if (!Array.isArray(seeds) || seeds.length === 0) {
  console.error("FATAL 找不到 seed：" + SEEDS_FILE + "（应从本 skill 的 scripts/tiktok-seeds.json 复制到工作区 scripts/）");
  process.exit(1);
}

let prev = await readJson(CATALOG, { pages: [], frontier: [] });
if (RESET) prev = { pages: [], frontier: [] };

const known = new Map((prev.pages || []).map(p => [String(p.knowledge_id), p]));
const crawled = new Set(known.keys());
const seedIds = seeds.map(s => String(s.id));

const savedFrontier = (prev.frontier || []).map(String);
let mode = "frontier";
let queue = savedFrontier.filter(id => !crawled.has(id));
if (queue.length === 0) {
  const unknownSeeds = seedIds.filter(id => !crawled.has(id));
  if (unknownSeeds.length > 0) {
    mode = "seed";
    queue = unknownSeeds;
  } else {
    mode = "rebuild";
  }
}

console.log("MODE " + mode + " crawled=" + crawled.size + " max=" + MAX_PAGES + " cap=" + CAP);

if (crawled.size >= CAP) {
  console.log("CAP_REACHED 已有 " + crawled.size + " 篇 >= 上限 " + CAP + "，本脚本不再扩张（不做全库）。");
  console.log("如需覆盖新章节：往 tiktok-seeds.json 补定向种子，或临时提高 TIKTOK_CAP。");
  process.exit(0);
}

const task = await taskSpace("tiktok catalog crawl");
const page = task.page("p1");

async function fetchHtml(url, retries = 2) {
  let lastErr = null;
  for (let i = 0; i < retries; i++) {
    try {
      const r = await page.fetch(url);
      const html = typeof r === "string" ? r : (r && typeof r.text === "function") ? await r.text() : (r && typeof r.body === "string") ? r.body : "";
      if (html && html.length > 0) return html;
      lastErr = new Error("empty");
    } catch (e) {
      lastErr = e;
    }
    // 连续导航偶发返回空壳，隔 1.5s 重试一次
    await new Promise(r => setTimeout(r, 1500));
  }
  throw lastErr || new Error("fetch failed");
}

function neighbours(html) {
  const set = new Set();
  const re = /knowledge_id=(\d+)/g;
  let m;
  while ((m = re.exec(html)) !== null) set.add(m[1]);
  return set;
}

// 先建同源上下文（一次渲染，之后全走 fetch）
// ⚠️ 必须 waitUntil=domcontentloaded：默认等 load 的站必然 15s 超时，超时后页面是空壳（origin=null），
//    后续 page.fetch 会全部因 CORS 被拒（"Request from null failed"），表现为「突然全线抓不到」
async function ensureContext(seedId) {
  const url = ENTRY + seedId + "&lang=en";
  for (let i = 0; i < 3; i++) {
    try {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 25000 });
    } catch (e) {
      console.log("goto retry " + (i + 1) + " : " + String(e).slice(0, 80));
    }
    await new Promise(r => setTimeout(r, 1500));
    try {
      const ok = await page.evaluate(() => ({
        host: location.host,
        len: document.body ? document.body.innerText.length : 0
      }));
      if (ok && ok.host === "seller-us.tiktok.com" && ok.len > 800) {
        console.log("ctx-ready len=" + ok.len);
        return true;
      }
      console.log("ctx weak host=" + (ok && ok.host) + " len=" + (ok && ok.len));
    } catch {}
  }
  return false;
}

const ctxOk = await ensureContext(queue[0] || seedIds[0]);
if (!ctxOk) {
  console.error("FATAL 无法建立 seller-us 同源上下文（goto 超时或页面为空壳）。本轮不写盘，避免把空结果落成索引。");
  console.error("排查顺序：① ego lite 是否在运行、能否打开普通网页；② 本机到 seller-us 的连通性；③ 换 seed id 重试。");
  process.exit(2);
}

// ── rebuild 前置：重走已知页，把邻接表重新算出来 ─────────────────────────
if (mode === "rebuild") {
  const walk = Array.from(known.keys()).slice(0, REBUILD_MAX);
  console.log("REBUILD 重走 " + walk.length + " 篇已知页以重建邻接表");
  const found = new Set();
  let ok = 0, bad = 0;
  for (const id of walk) {
    try {
      const html = await fetchHtml(ENTRY + id + "&lang=en");
      for (const nb of neighbours(html)) if (!crawled.has(nb)) found.add(nb);
      ok++;
    } catch {
      bad++;
    }
    if (ok % 50 === 0 && ok > 0) console.log("rebuild progress " + ok + "/" + walk.length + " found=" + found.size);
  }
  queue = Array.from(found);
  console.log("REBUILD DONE ok=" + ok + " bad=" + bad + " new_frontier=" + queue.length);
  if (bad > 0 && ok === 0) {
    console.error("FATAL rebuild 全部失败（bad=" + bad + "），fetch 通道已不可用。本轮不写盘。");
    process.exit(3);
  }
}

const queued = new Set(queue);
const fresh = [];
const retried = new Set();
const rejected = { notfound: 0, shell: 0, fetchfail: 0, requeued: 0 };

for (let n = 0; queue.length > 0 && n < MAX_PAGES && crawled.size < CAP; n++) {
  const id = queue.shift();
  queued.delete(id);
  if (crawled.has(id)) continue;

  const url = ENTRY + id + "&lang=en";
  let html = "";
  try {
    html = await fetchHtml(url);
  } catch {
    // 抓取失败 ≠ 该 id 无效：不计入 crawled，放回队列末尾下轮再试（每轮最多重试一次）
    rejected.fetchfail++;
    if (!retried.has(id)) {
      retried.add(id);
      queue.push(id);
      queued.add(id);
      rejected.requeued++;
    }
    continue;
  }
  crawled.add(id);

  const neigh = neighbours(html);
  const h1m = html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i);
  const h1 = h1m ? h1m[1].replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim() : "";
  const dates = html.match(/\d{1,2}\/\d{1,2}\/\d{4}/g) || [];

  const is404 = /^(404|page not found)/i.test(h1) || /Page not found/i.test(h1);
  if (is404) {
    rejected.notfound++;
  } else if (!h1 || html.length < 60000) {
    rejected.shell++;
  } else {
    const row = {
      knowledge_id: id,
      title: h1.slice(0, 120),
      date: dates[0] || "",
      html_len: html.length,
      neighbors: neigh.size,
      url,
      fetched_at: new Date().toISOString()
    };
    fresh.push(row);
    known.set(id, row);
  }

  for (const nb of neigh) {
    if (!crawled.has(nb) && !queued.has(nb)) {
      queue.push(nb);
      queued.add(nb);
    }
  }

  if (fresh.length > 0 && fresh.length % 20 === 0) {
    console.log("progress pages=" + fresh.length + " queue=" + queue.length);
  }
}

const capHit = crawled.size >= CAP;
if (capHit) {
  console.log("CAP_REACHED crawled=" + crawled.size + " cap=" + CAP + " 队列剩余 " + queue.length + " 篇不再扩张（不做全库）");
}

const all = Array.from(known.values()).sort((a, b) => {
  const t = s => { const m = (s || "").match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/); return m ? Number(m[3] + m[1].padStart(2, "0") + m[2].padStart(2, "0")) : 0; };
  return t(b.date) - t(a.date);
});

const catalog = {
  source: "ego-browser (ego lite) -> seller-us.tiktok.com/university/essay",
  built_at: new Date().toISOString(),
  mode,
  scope: "limited-index (不做全库)",
  cap: CAP,
  cap_reached: capHit,
  total: all.length,
  crawled_this_run: fresh.length,
  queue_left: capHit ? 0 : queue.length,
  // 到 CAP 就清空队列：留着会诱导下一轮继续扩张，与「不做全库」的定位冲突
  frontier: capHit ? [] : queue.slice(0, 5000),
  rejected,
  pages: all
};

await mkdir(STATE_DIR, { recursive: true });
await writeFile(CATALOG, JSON.stringify(catalog, null, 2), "utf8");

console.log("DONE mode=" + mode + " crawled=" + fresh.length + " total=" + all.length + " queue_left=" + (capHit ? 0 : queue.length) + (capHit ? " CAP_REACHED" : ""));
console.log("REJECTED " + JSON.stringify(rejected));
console.log("WROTE " + CATALOG);
