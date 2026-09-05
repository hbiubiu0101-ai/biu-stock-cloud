"""Lightweight market-data adapters for Streamlit and scheduled jobs.

Public endpoints are treated as best-effort sources.  Callers must keep the
last persisted snapshot and must never interpret an unavailable endpoint as a
zero price or a trading signal.
"""
from __future__ import annotations

from datetime import datetime
import json
import re
import time
from urllib.parse import quote

import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}

ASHARE_INDICES = {
    "sh000001": "上证指数", "sz399001": "深证成指", "sz399006": "创业板指",
    "sh000300": "沪深300", "sh000905": "中证500", "sh000688": "科创50",
    "bj899050": "北证50",
}

COMMODITIES = {
    "hf_GC": ("COMEX黄金", "美元/盎司"), "hf_SI": ("COMEX白银", "美元/盎司"),
    "hf_CL": ("WTI原油", "美元/桶"), "hf_HG": ("COMEX铜", "美元/磅"),
    "nf_AU0": ("沪金主连", "元/克"), "nf_AG0": ("沪银主连", "元/千克"),
    "nf_CU0": ("沪铜主连", "元/吨"), "nf_AL0": ("沪铝主连", "元/吨"),
    "nf_I0": ("铁矿主连", "元/吨"), "nf_RB0": ("螺纹主连", "元/吨"),
}


def security_type(code: str, name: str = "") -> str:
    code, name = str(code), str(name).upper()
    if code in {s[2:] for s in ASHARE_INDICES}: return "指数"
    if "LOF" in name: return "LOF"
    if "ETF" in name or code.startswith(("15", "16", "50", "51", "52", "53", "56", "58")): return "ETF"
    if code.startswith(("11", "12")): return "可转债"
    return "A股"


def parse_sina_suggestions(body: str, query: str) -> list[dict]:
    import unicodedata
    norm = lambda s: "".join(unicodedata.normalize("NFKC", str(s)).split()).casefold()
    payload = re.search(r'=\s*"([^"\r\n]*)"', body)
    if not payload: return []
    found = {}
    for record in payload.group(1).split(";"):
        fields = record.split(",")
        if len(fields) < 5: continue
        code, symbol, name = fields[2].strip(), fields[3].strip(), fields[4].strip()
        if not re.fullmatch(r"\d{6}", code) or symbol not in ("sh" + code, "sz" + code, "bj" + code): continue
        if not name or norm(query) not in norm(name): continue
        found[code] = {"code": code, "name": name, "type": security_type(code, name)}
    rows = list(found.values())
    exact = [x for x in rows if norm(x["name"]) == norm(query)]
    return (exact or rows)[:30]


def search_security(query: str, timeout: int = 8) -> list[dict]:
    response = requests.get(
        "https://suggest3.sinajs.cn/suggest/type=11,12,13,14,15&key=" + quote(query, safe="") + "&name=suggestvalue",
        headers={"User-Agent": UA["User-Agent"], "Referer": "https://finance.sina.com.cn/"},
        timeout=(4, timeout), allow_redirects=False,
    )
    response.raise_for_status(); response.encoding = "gb18030"
    return parse_sina_suggestions(response.text, query)


def quote_symbol(code: str) -> str:
    if code.startswith(("5", "6", "9")): return "sh" + code
    if code.startswith(("4", "8")): return "bj" + code
    return "sz" + code


def fetch_security_quote(code: str, timeout: int = 6) -> dict | None:
    raw = str(code).strip()
    symbol = raw if re.fullmatch(r'(?:sh|sz|bj)\d{6}', raw) else quote_symbol(raw)
    code = symbol[2:]
    response = requests.get("https://qt.gtimg.cn/q=" + symbol, headers=UA,
                            timeout=(4, timeout), allow_redirects=False)
    response.raise_for_status(); response.encoding = "gb18030"
    match = re.search(r'="([^"]*)"', response.text)
    if not match: return None
    p = match.group(1).split("~")
    if len(p) < 38 or not p[3]: return None
    previous = float(p[4] or 0); latest = float(p[3])
    return {"code": code, "symbol": symbol, "name": p[1] or code,
            "type": security_type(code, p[1]), "close": latest,
            "change_pct": float(p[32]) if p[32] else ((latest / previous - 1) * 100 if previous else 0),
            "volume": float(p[6] or 0), "amount": float(p[37] or 0) * 10000,
            "updated_at": p[30] if len(p) > 30 else "", "source": "腾讯行情"}


def fetch_minute_kline(code: str, scale: int = 30, count: int = 640, timeout: int = 10) -> pd.DataFrame:
    if scale not in (1, 5, 15, 30, 60): raise ValueError("分钟周期仅支持1/5/15/30/60")
    symbol, key = quote_symbol(code), "m" + str(scale)
    # Historical minute bars first; same-day minute/query is requested only
    # when the first endpoint returns no rows, avoiding a duplicate request.
    fq = requests.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
        params={"param": f"{symbol},{key},,,{min(count, 1000)},qfq"}, headers=UA,
        timeout=(4, timeout), allow_redirects=False)
    rows = []
    if fq.status_code == 200:
        node = fq.json().get("data", {}).get(symbol, {})
        raw = node.get(key) or node.get("qfq" + key) or []
        for item in raw:
            p = item.split(",") if isinstance(item, str) else item
            if len(p) >= 6:
                rows.append({"date": p[0], "open": p[1], "close": p[2], "high": p[3], "low": p[4], "volume": p[5],
                             "amount": p[6] if len(p) > 6 else 0})
    if not rows:
        response = requests.get("https://web.ifzq.gtimg.cn/appstock/app/minute/query",
            params={"code": symbol, "r": int(time.time())}, headers=UA,
            timeout=(4, timeout), allow_redirects=False)
    if not rows and response.status_code == 200:
        data = response.json().get("data", {}).get(symbol, {}).get("data", {})
        date = data.get("date") or datetime.now().strftime("%Y%m%d")
        for item in data.get("data", []):
            p = item.split(" ")
            if len(p) >= 4:
                rows.append({"date": f"{date} {p[0]}", "open": p[1], "high": p[1], "low": p[1], "close": p[1],
                             "volume": p[2], "amount": p[3]})
    frame = pd.DataFrame(rows)
    if frame.empty: return frame
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    for col in ("open", "high", "low", "close", "volume", "amount"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["date", "open", "high", "low", "close"]).drop_duplicates("date").sort_values("date")
    frame.attrs.update(source="腾讯/mootdx思路备用", period=str(scale), adjustment="qfq")
    return frame.reset_index(drop=True)


def fetch_index_quotes() -> list[dict]:
    rows = []
    for symbol, name in ASHARE_INDICES.items():
        try:
            q = fetch_security_quote(symbol)
            if q: q.update(name=name, symbol=symbol, type="指数"); rows.append(q)
        except Exception: pass
    return rows


def fetch_commodity_quotes(timeout: int = 8) -> list[dict]:
    symbols = ",".join(COMMODITIES)
    response = requests.get("https://hq.sinajs.cn/list=" + symbols,
        headers={"User-Agent": UA["User-Agent"], "Referer": "https://finance.sina.com.cn/"},
        timeout=(4, timeout), allow_redirects=False)
    response.raise_for_status(); response.encoding = "gb18030"
    rows = []
    for symbol, payload in re.findall(r'var hq_str_([^=]+)="([^"]*)"', response.text):
        p = payload.split(","); meta = COMMODITIES.get(symbol)
        if not meta or len(p) < 2: continue
        nums = []
        for value in p:
            try: nums.append(float(value))
            except ValueError: nums.append(None)
        current = next((x for x in nums[0:4] if x and x > 0), None)
        previous = next((x for x in nums[4:10] if x and x > 0), None)
        if current is None: continue
        rows.append({"symbol": symbol, "name": meta[0], "unit": meta[1], "close": current,
                     "change_pct": (current / previous - 1) * 100 if previous else 0,
                     "updated_at": datetime.now().isoformat(timespec="seconds"), "source": "新浪期货"})
    return rows


def bubble_html(rows: list[dict], title: str) -> str:
    safe = lambda s: re.sub(r"[^\w\u4e00-\u9fff.%+\-/]", "", str(s))
    items = []
    for i, row in enumerate(rows):
        change = float(row.get("change_pct", 0) or 0); cls = "up" if change > 0 else "down" if change < 0 else "flat"
        size = 94 + min(34, abs(change) * 5)
        items.append(f'<div class="market-bubble {cls}" style="width:{size}px;height:{size}px"><b>{safe(row.get("name"))}</b><span>{change:+.2f}%</span><small>{safe(row.get("close"))}</small></div>')
    return '<section class="bubble-field" aria-label="' + safe(title) + '">' + "".join(items) + "</section>"
