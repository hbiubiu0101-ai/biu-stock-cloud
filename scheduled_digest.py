"""20:30 Asia/Shanghai holdings digest. Run by GitHub Actions, not Streamlit."""
from __future__ import annotations
import base64, hashlib, hmac, json, os, time
from datetime import datetime
from urllib.parse import quote_plus
import requests
from zoneinfo import ZoneInfo

from cloud_backend import CloudStore, CloudError
from market_data import fetch_security_quote, fetch_index_quotes, fetch_commodity_quotes


def feishu_send(webhook: str, secret: str, text: str):
    payload = {"msg_type": "text", "content": {"text": text}}
    if secret:
        stamp = str(int(time.time()))
        sign = base64.b64encode(hmac.new((stamp + "\n" + secret).encode(), digestmod=hashlib.sha256).digest()).decode()
        payload.update(timestamp=stamp, sign=sign)
    response = requests.post(webhook, json=payload, timeout=(5, 15)); response.raise_for_status()
    body = response.json()
    if body.get("code", body.get("StatusCode", 0)) != 0: raise RuntimeError("飞书拒绝发送")


def news_for(name: str) -> list[str]:
    """Best-effort public news; failure produces no fabricated headline."""
    try:
        r = requests.get("https://searchapi.eastmoney.com/bussiness/Web/GetSearchList",
            params={"keyword": name, "type": "701", "pageindex": 1, "pagesize": 5},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://so.eastmoney.com/"}, timeout=(4, 8))
        r.raise_for_status(); data = r.json().get("Data") or []
        return [str(x.get("Title") or x.get("title") or "").strip() for x in data if x.get("Title") or x.get("title")][:5]
    except Exception: return []


def ai_summary(lines: list[str]) -> str:
    if not lines: return "今日未取得可靠的新消息，未进行利好/利空判断。"
    prompt = "你是谨慎的中文证券信息整理助手。只根据输入标题，去重后用120字内总结；标注利好/利空/中性和重要性；不预测股价，不编造。\n" + "\n".join(lines)
    providers = []
    if os.getenv("SILICONFLOW_API_KEY"):
        providers.append(("https://api.siliconflow.cn/v1/chat/completions", os.environ["SILICONFLOW_API_KEY"],
                          os.getenv("SILICONFLOW_MODEL", "Qwen/Qwen2.5-7B-Instruct")))
    if os.getenv("OPENROUTER_API_KEY"):
        providers.append(("https://openrouter.ai/api/v1/chat/completions", os.environ["OPENROUTER_API_KEY"], "openrouter/free"))
    for url, key, model in providers:
        try:
            r = requests.post(url, headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 300}, timeout=(5, 30))
            r.raise_for_status(); return r.json()["choices"][0]["message"]["content"].strip()
        except Exception: continue
    words = " ".join(lines)
    bad = ("减持", "处罚", "亏损", "下修", "立案", "终止"); good = ("增持", "回购", "预增", "中标", "分红")
    mood = "偏利空" if any(x in words for x in bad) else "偏利好" if any(x in words for x in good) else "中性"
    return f"规则初判：{mood}。" + "；".join(lines[:3])


def is_trade_day(now: datetime) -> bool:
    if now.weekday() >= 5: return False
    try:
        import akshare as ak
        dates = set(str(x)[:10] for x in ak.tool_trade_date_hist_sina()["trade_date"])
        return now.strftime("%Y-%m-%d") in dates
    except Exception:
        return True  # weekday fallback; message states actual data freshness.


def run():
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    if not is_trade_day(now): return
    store = CloudStore(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])
    webhook, secret = os.environ["FEISHU_WEBHOOK"], os.getenv("FEISHU_SIGN_SECRET", "")
    index_rows, commodity_rows = fetch_index_quotes(), fetch_commodity_quotes()
    market = "大盘：" + "，".join(f'{x["name"]}{x["change_pct"]:+.2f}%' for x in index_rows[:4])
    goods = "商品：" + "，".join(f'{x["name"]}{x["change_pct"]:+.2f}%' for x in commodity_rows[:5])
    for profile in store.profiles():
        scoped = CloudStore(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"], profile_id=profile["id"])
        if scoped.state("feishu_enabled", False) is not True: continue
        holdings = scoped.lists()["holdings"]
        detail, headlines = [], []
        for code in holdings:
            try:
                q = fetch_security_quote(code)
                if not q: raise ValueError()
                detail.append(f'{q["name"]}（{code}） {q["close"]:.2f} {q["change_pct"]:+.2f}%')
                headlines.extend([q["name"] + "：" + h for h in news_for(q["name"])])
            except Exception: detail.append(code + "：数据待补")
        digest = (f'📊 {profile["name"]}｜{now:%Y-%m-%d} 收盘汇总\n' + ("\n".join(detail) if detail else "暂无持仓股") +
                  "\n\n" + market + "\n" + goods + "\n\n📰 消息面\n" + ai_summary(headlines) +
                  "\n\n仅作数据整理，不构成投资建议。")
        identity = hashlib.sha256((profile["id"] + now.strftime("%Y%m%d") + "close-digest-v1").encode()).hexdigest()
        if scoped.reserve_notification(identity, "000000", now.strftime("%Y-%m-%d"), "buy"):
            try: feishu_send(webhook, secret, digest); scoped.finish_notification(identity, "sent")
            except Exception: scoped.finish_notification(identity, "failed"); raise


if __name__ == "__main__": run()
