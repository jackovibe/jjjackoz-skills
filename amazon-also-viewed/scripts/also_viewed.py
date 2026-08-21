#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
亚马逊 "Customers who viewed this item also viewed" 全量 ASIN 抓取
零第三方依赖（仅 Python 标准库 urllib），任何 agent / 任何环境可直接运行。

用法:
  python also_viewed.py <ASIN>              # 完整跑: ASIN 列表 + 标题/价格/评分/评论
  python also_viewed.py <ASIN> --no-detail  # 只要 ASIN 列表(更快)
  python also_viewed.py <ASIN> --out DIR    # 自定义输出目录

原理:
  1) 请求商品页, 提取内嵌 data-a-carousel-options > ajax.id_list JSON
     (含 carousel 全部推荐 ASIN, 无需浏览器翻页)
  2) 逐个请求移动版 /gp/aw/d/{asin} 补全标题/价格/评分/评论数

输出: {out}/output/{ASIN}_also_viewed.xlsx / .csv（/ .json --json 时 / .html --html 时）
"""
import argparse
import csv
import gzip
import html as htmllib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# ---------- 常量 ----------
UA_DESKTOP = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
UA_MOBILE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")
HOME = os.path.expanduser("~")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


# ---------- HTTP（标准库实现，自动处理 gzip/br） ----------
class _NoRedir(urllib.request.HTTPRedirectHandler):
    """禁止重定向跟随（防止被引到验证页）"""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url, ua, referer=None, timeout=25, allow_redirect=True):
    """GET 请求, 返回 (status, html_text)"""
    headers = {
        "User-Agent": ua,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate",
    }
    if referer:
        headers["Referer"] = referer
    handlers = [urllib.request.HTTPHandler()]
    if not allow_redirect:
        handlers.append(_NoRedir())
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers=headers)
    try:
        with opener.open(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            raw = resp.read()
            # 解压
            if resp.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                try:
                    raw = gzip.decompress(raw)
                except Exception:
                    pass
            text = raw.decode("utf-8", errors="replace")
            return status, text
    except urllib.error.HTTPError as e:
        return e.code, (e.read().decode("utf-8", errors="replace") if e.read else "")
    except Exception as e:
        return 0, str(e)


def get_home_cookie():
    """访问首页获取 cookie（增强后续请求可信度）"""
    try:
        fetch("https://www.amazon.com/", UA_DESKTOP, timeout=15)
    except Exception:
        pass


# ---------- 解析 ----------
def extract_id_list(html):
    """从商品页 HTML 提取 also viewed 模块的完整 ASIN 列表（内嵌 JSON）
    兼容三种编码格式:
      A) "ajax":"{\"id_list\":\"[{\\\"id\\\":\\\"B0...\\\"...}]\"}"  (字符串化)
      B) "ajax":{"id_list":[{"id":"B0...","linkParameters":{...}}]}  (真实数组)
      C) 页面只渲染了部分卡片 (data-asin 属性)
    """
    title_idx = html.find("Customers who viewed this item also viewed")
    if title_idx < 0:
        # 兜底: 页面可能无该模块
        return []
    seg = html[max(0, title_idx - 20000): title_idx + 30000]
    ids = re.findall(r'\\&quot;id\\&quot;:\\&quot;(B0[A-Z0-9]{8})', seg)
    if not ids:
        ids = re.findall(r'&quot;id&quot;:&quot;(B0[A-Z0-9]{8})', seg)
    if not ids:
        ids = re.findall(r'"id"\s*:\s*"(B0[A-Z0-9]{8})"', seg)
    if not ids:
        # 最后兜底: 模块容器内 data-asin
        m = re.search(r'data-a-carousel-options="([^"]*)"', seg)
        if m:
            ids = re.findall(r'data-asin="(B0[A-Z0-9]{8})"', seg)
    return list(dict.fromkeys(ids))


def extract_detail(html):
    """从移动版页面提取商品详情"""
    d = {}
    m = re.search(r'<meta name="title" content="([^"]+)"', html)
    if m:
        d["title"] = htmllib.unescape(m.group(1).replace("Amazon.com: ", "").strip())
    if not d.get("title"):
        m = re.search(r"<title>(.*?)</title>", html, re.S)
        if m:
            d["title"] = htmllib.unescape(m.group(1).replace("Amazon.com: ", "").strip())
    mw = re.search(r'class="a-price-whole">([\d,]+)<', html)
    mf = re.search(r'class="a-price-fraction">(\d+)<', html)
    if mw:
        d["price"] = "$" + mw.group(1) + ("." + mf.group(1) if mf else "")
    mr = re.search(r'([\d.]+) out of 5 stars', html)
    if mr:
        d["rating"] = mr.group(1)
    mc = re.search(r'([\d,]+) ratings', html)
    if mc:
        d["reviews"] = mc.group(1)
    return d


# ---------- 流程 ----------
def enrich(rows, interval=1.0):
    """逐个补详情（移动版）, 带断点续传"""
    get_home_cookie()
    for i, row in enumerate(rows, 1):
        if row.get("title") and row.get("price"):
            continue
        try:
            code, html = fetch(f"https://www.amazon.com/gp/aw/d/{row['asin']}",
                               UA_MOBILE, timeout=20)
            if code == 200 and len(html) > 50000:
                row.update(extract_detail(html))
                print(f"  [{i}/{len(rows)}] {row['asin']} OK | {row.get('price','-')} | {row.get('rating','-')}", flush=True)
            else:
                print(f"  [{i}/{len(rows)}] {row['asin']} HTTP {code}", flush=True)
        except Exception as e:
            print(f"  [{i}/{len(rows)}] {row['asin']} ERR {str(e)[:60]}", flush=True)
        time.sleep(interval)
    return rows


def generate_html_report(rows, asin, out_path, source_url=None):
    """玻璃拟态 HTML 报告生成（纯本地渲染, 单文件, 无外部 CDN）
    rows: [{asin,title,price,rating,reviews}, ...]
    返回 HTML 字符串
    """
    def esc(s):
        return htmllib.escape(str(s), quote=True)

    main_title = rows[0]["title"] if rows and rows[0].get("title") else asin
    source_url = source_url or f"https://www.amazon.com/dp/{asin}"
    n_price = sum(1 for r in rows if r.get("price"))
    n_rating = sum(1 for r in rows if r.get("rating"))

    cards = []
    for i, r in enumerate(rows, 1):
        price = r.get("price") or "-"
        rating = r.get("rating") or "-"
        reviews = r.get("reviews") or "-"
        title = esc(r.get("title", ""))
        link = f"https://www.amazon.com/dp/{r['asin']}"
        try:
            rv = float(rating)
            stars = "\u2605" * int(round(rv)) + "\u2606" * (5 - int(round(rv)))
        except Exception:
            stars = ""
        cards.append(f"""
    <div class="card">
      <div class="card-top">
        <span class="idx">#{i:02d}</span>
        <span class="badge">ASIN</span>
        <span class="asin">{esc(r['asin'])}</span>
      </div>
      <div class="title">{title}</div>
      <div class="meta">
        <span class="price">{esc(price)}</span>
        <span class="rating">{stars} <em>{esc(rating)}</em></span>
        <span class="reviews">{esc(reviews)} \u8bc4\u8bba</span>
      </div>
      <div class="link-row">
        <a href="{link}" target="_blank" rel="noopener">\u67e5\u770b\u5546\u54c1 \u2192</a>
      </div>
    </div>""")

    css = """
  :root{--bg:#0f1220;--card:rgba(255,255,255,0.06);--card-border:rgba(255,255,255,0.12);
    --text:#e8eaf2;--muted:#9aa3b8;--accent:#7c5cff;--accent2:#00d4ff;--red:#ff5c7a}
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:"PingFang SC","Microsoft YaHei","Segoe UI",sans-serif;
    background:radial-gradient(1200px 600px at 10% -10%,rgba(124,92,255,0.18),transparent 60%),
      radial-gradient(1000px 500px at 110% 10%,rgba(0,212,255,0.12),transparent 55%),var(--bg);
    color:var(--text);min-height:100vh;padding:40px 24px}
  .container{max-width:1200px;margin:0 auto}
  .header{background:var(--card);border:1px solid var(--card-border);border-radius:20px;padding:28px 32px;
    backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);margin-bottom:28px;
    box-shadow:0 12px 40px rgba(0,0,0,0.35)}
  .header h1{font-size:22px;font-weight:700;letter-spacing:.5px}
  .header .sub{color:var(--muted);margin-top:8px;font-size:14px;line-height:1.7}
  .header .src{margin-top:12px;font-size:13px}.header .src a{color:var(--accent2);text-decoration:none}
  .stats{display:flex;gap:14px;margin-top:18px;flex-wrap:wrap}
  .stat{flex:1;min-width:130px;background:rgba(124,92,255,0.12);border:1px solid rgba(124,92,255,0.25);
    border-radius:14px;padding:12px 16px;text-align:center}
  .stat b{display:block;font-size:24px;color:var(--accent2)}.stat span{font-size:12px;color:var(--muted)}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px}
  .card{background:var(--card);border:1px solid var(--card-border);border-radius:16px;padding:18px;
    backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);transition:transform .2s,border-color .2s,box-shadow .2s;
    display:flex;flex-direction:column;gap:10px}
  .card:hover{transform:translateY(-3px);border-color:rgba(124,92,255,0.5);box-shadow:0 8px 30px rgba(124,92,255,0.15)}
  .card-top{display:flex;align-items:center;gap:10px}
  .idx{font-size:13px;color:var(--muted);font-weight:700}
  .badge{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;font-size:10px;font-weight:700;
    padding:3px 8px;border-radius:999px;letter-spacing:1px}
  .asin{font-family:Consolas,monospace;font-size:14px;font-weight:700}
  .title{font-size:13px;color:var(--muted);line-height:1.6;min-height:62px;display:-webkit-box;
    -webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
  .meta{display:flex;align-items:center;gap:14px;font-size:13px;flex-wrap:wrap}
  .price{font-size:18px;font-weight:800;color:var(--red)}
  .rating{color:#ffb800}.rating em{color:var(--text);font-style:normal;font-weight:700}
  .reviews{color:var(--muted);font-size:12px}
  .link-row{margin-top:auto}
  .link-row a{display:inline-block;background:linear-gradient(135deg,var(--accent),var(--accent2));
    color:#fff;text-decoration:none;font-size:13px;font-weight:600;padding:8px 16px;border-radius:999px;
    transition:opacity .2s}
  .link-row a:hover{opacity:.85}
  .footer{text-align:center;color:var(--muted);font-size:12px;margin-top:32px}
"""

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Customers Who Viewed This Item Also Viewed — {len(rows)} ASIN</title>
<style>{css}</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>\U0001f6d2 Customers Who Viewed This Item Also Viewed</h1>
    <div class="sub">\u6e90\u5546\u54c1\uff1a{esc(main_title[:90])}...</div>
    <div class="src">\u6570\u636e\u6765\u6e90\uff1a<a href="{source_url}" target="_blank" rel="noopener">{source_url}</a> \u00b7 \u6293\u53d6\u81ea\u9875\u9762\u5185\u5d4c p13n \u63a8\u8350\u6a21\u5757</div>
    <div class="stats">
      <div class="stat"><b>{len(rows)}</b><span>\u63a8\u8350 ASIN</span></div>
      <div class="stat"><b>{n_price}</b><span>\u542b\u4ef7\u683c</span></div>
      <div class="stat"><b>{n_rating}</b><span>\u542b\u8bc4\u5206</span></div>
    </div>
  </div>
  <div class="grid">
    {''.join(cards)}
  </div>
  <div class="footer">Amazon Customers Who Viewed Also Viewed \u00b7 \u6570\u636e\u4ec5\u4f9b\u9009\u54c1\u7814\u7a76\u53c2\u8003</div>
</div>
</body>
</html>"""
    with io.open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)
    return html_doc


def generate_xlsx(rows, out_path):
    """生成 xlsx（纯标准库 zipfile + XML，零第三方依赖，Excel/WPS 可直接打开）
    rows: [{asin,title,price,rating,reviews}, ...]
    """
    import zipfile
    from xml.sax.saxutils import escape

    headers = ["序号", "ASIN", "价格", "评分", "评论数", "标题", "商品链接"]

    def col_letter(i):
        s = ""
        while i > 0:
            i, r = divmod(i - 1, 26)
            s = chr(65 + r) + s
        return s

    sheet_rows = []
    for r_idx, row in enumerate(
        [headers]
        + [
            [str(i), r["asin"], r.get("price", ""), r.get("rating", ""),
             r.get("reviews", ""), r.get("title", ""),
             f"https://www.amazon.com/dp/{r['asin']}"]
            for i, r in enumerate(rows, 1)
        ],
        1,
    ):
        cells = ""
        for c_idx, val in enumerate(row, 1):
            ref = f"{col_letter(c_idx)}{r_idx}"
            cells += f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(str(val))}</t></is></c>'
        sheet_rows.append(f'<row r="{r_idx}">{cells}</row>')

    sheet_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                 '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                 f'<sheetData>{"".join(sheet_rows)}</sheetData></worksheet>')
    workbook_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                    '<sheets><sheet name="AlsoViewed" sheetId="1" r:id="rId1"/></sheets></workbook>')
    rels_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                'Target="xl/workbook.xml"/></Relationships>')
    wb_rels_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                   'Target="worksheets/sheet1.xml"/></Relationships>')
    content_types_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                         '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                         '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                         '<Default Extension="xml" ContentType="application/xml"/>'
                         '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                         '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                         '</Types>')

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return out_path


def main():
    ap = argparse.ArgumentParser(description="亚马逊 also viewed 全量 ASIN 抓取")
    ap.add_argument("asin", help="源商品 ASIN, 如 B0EXAMPLE123")
    ap.add_argument("--no-detail", action="store_true", help="跳过详情补全, 只要 ASIN 列表")
    ap.add_argument("--html", action="store_true", help="额外生成玻璃拟态 HTML 报告（默认只输出 CSV）")
    ap.add_argument("--json", action="store_true", help="额外生成 JSON 文件（默认只输出 CSV）")
    ap.add_argument("--interval", type=float, default=1.0, help="详情请求间隔秒数")
    ap.add_argument("--out", default=OUTPUT_DIR, help="输出目录")
    args = ap.parse_args()

    asin = args.asin.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{10}", asin):
        print(f"[!] ASIN 格式异常: {asin}")
        sys.exit(2)

    url = f"https://www.amazon.com/dp/{asin}"
    print(f"[1] 请求商品页 {url} ...")
    get_home_cookie()
    code, html = fetch(url, UA_DESKTOP, allow_redirect=False)
    if code != 200:
        print(f"[!] 商品页 HTTP {code}, 可能被反爬拦截, 15 秒后重试...")
        time.sleep(15)
        code, html = fetch(url, UA_DESKTOP, allow_redirect=False)
    print(f"    状态 {code}, 页面 {len(html)/1024:.0f} KB")

    # 反爬降级检测: 页面带验证横幅且无推荐模块时, 冷却重试（最多 3 次）
    asins = extract_id_list(html)
    retry = 0
    while not asins and retry < 3 and "Continue shopping" in html:
        retry += 1
        wait = 30 * retry
        print(f"[!] 页面被验证降级(无推荐模块), {wait} 秒后第 {retry}/3 次重试...")
        time.sleep(wait)
        code, html = fetch(url, UA_DESKTOP, allow_redirect=False)
        print(f"    重试状态 {code}, 页面 {len(html)/1024:.0f} KB")
        asins = extract_id_list(html)

    print("[2] 提取 also viewed 内嵌 id_list ...")
    if not asins:
        print("[!] 未提取到 id_list (页面被验证拦截或该 ASIN 无推荐模块)")
        sys.exit(3)
    print(f"    提取到 {len(asins)} 个推荐 ASIN")

    rows = [{"asin": a, "title": "", "price": "", "rating": "", "reviews": ""} for a in asins]

    if not args.no_detail:
        print("[3] 移动版补全详情 ...")
        rows = enrich(rows, interval=args.interval)

    os.makedirs(args.out, exist_ok=True)
    base = os.path.join(args.out, f"{asin}_also_viewed")
    if args.json:
        with io.open(base + ".json", "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
    with io.open(base + ".csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["序号", "ASIN", "价格", "评分", "评论数", "标题", "商品链接"])
        for i, r in enumerate(rows, 1):
            w.writerow([i, r["asin"], r.get("price", ""), r.get("rating", ""),
                        r.get("reviews", ""), r.get("title", ""),
                        f"https://www.amazon.com/dp/{r['asin']}"])
    generate_xlsx(rows, base + ".xlsx")
    print(f"\n===== 完成: {len(rows)} 个 ASIN =====")
    for r in rows:
        print(f"{r['asin']} | {r.get('price') or '-':>10} | {r.get('rating') or '-':>4} | {r.get('reviews') or '-':>6} | {r.get('title','')[:55]}")

    # 玻璃拟态 HTML 报告（仅 --html 时生成）
    if args.html:
        html_path = base + ".html"
        generate_html_report(rows, asin, html_path, source_url=url)
        print(f"[4] HTML 报告: {html_path}")
    files_txt = [base + ".csv", base + ".xlsx"]
    if args.html:
        files_txt.append(base + ".html")
    if args.json:
        files_txt.append(base + ".json")
    print(f"\n输出: {' / '.join(files_txt)}")


if __name__ == "__main__":
    main()
