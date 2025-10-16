import json
from datetime import datetime
import os

import requests
import feedparser
import yfinance as yf

TIMEOUT = 12
DATA_FILE = "data.json"
MP3_FILE = "morning.mp3"

def safe_get_json(url, label="", params=None, headers=None):
    try:
        r = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        try:
            return r.json()
        except Exception:
            print(f"⚠️ {label} 回傳非 JSON，略過。")
            return {}
    except requests.RequestException as e:
        print(f"⚠️ {label} 網路/服務錯誤：{e}")
        return {}

# 1) 匯率（USD 基準）
def get_exchange_rates():
    data = safe_get_json("https://open.er-api.com/v6/latest/USD", label="匯率")
    rates = data.get("rates", {})
    wanted = ["TWD","JPY","EUR","GBP","CNY","AUD","CAD","CHF","HKD","KRW","SGD","INR"]
    out = {}
    for code in wanted:
        if code in rates:
            out[f"USD/{code}"] = round(float(rates[code]), 4)
    return out

# 2) 股市：yfinance（不需 key）
def get_stock_indexes():
    tickers = ["^DJI","^IXIC","^GSPC","^N225"]
    result = {}
    try:
        data = yf.download(" ".join(tickers), period="5d", interval="1d", progress=False, group_by='ticker', threads=False)
        for t in tickers:
            try:
                close_series = data[t]["Close"] if isinstance(data, dict) and t in data else data["Close"][t]
            except Exception:
                close_series = data["Close"][t]
            price = float(close_series.tail(1).values[0])
            if len(close_series) >= 2:
                prev = float(close_series.tail(2).values[0])
                chg = ((price - prev) / prev) * 100 if prev else 0.0
            else:
                chg = 0.0
            name_map = {"^DJI":"道瓊","^IXIC":"那斯達克","^GSPC":"S&P 500","^N225":"日經225"}
            result[name_map.get(t,t)] = {"price": round(price,2), "change": round(chg,2)}
    except Exception as e:
        print(f"⚠️ 股市(yfinance) 取得失敗：{e}")
    return result

# 3) 新聞：RSS
RSS_FEEDS = [
    "http://feeds.bbci.co.uk/news/business/rss.xml",
    "https://feeds.reuters.com/reuters/businessNews",
    "https://feeds.reuters.com/Reuters/worldNews"
]
def get_international_news(max_items=6):
    items = []
    for url in RSS_FEEDS:
        try:
            d = feedparser.parse(url)
            for e in d.entries[: max(2, max_items // len(RSS_FEEDS) + 1)]:
                title = e.get("title","").strip()
                link = e.get("link","").strip()
                if title and link:
                    items.append({"title": title, "url": link})
        except Exception as ex:
            print(f"⚠️ RSS 讀取失敗：{url} -> {ex}")
    # 去重
    seen, uniq = set(), []
    for it in items:
        if it["title"] not in seen:
            seen.add(it["title"])
            uniq.append(it)
    return uniq[:max_items]

def load_prev():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def calc_changes(curr: dict, prev: dict):
    """計算相對昨日的 % 變化（同一貨幣對）"""
    out = {}
    for k,v in curr.items():
        p = prev.get(k)
        if isinstance(v,(int,float)) and isinstance(p,(int,float)) and p:
            out[k] = round((v - p)/p*100, 2)
        else:
            out[k] = None
    return out

def build_summary(ex, exch, st, news):
    parts = []
    if ex:
        fx_line = []
        for k in ["USD/TWD","USD/JPY","USD/EUR"]:
            if k in ex:
                delta = exch.get(k)
                fx_line.append(f"{k.replace('USD/','')} {ex[k]}({'' if delta is None else ('+' if delta>0 else '')}{'' if delta is None else delta}%)")
        if fx_line:
            parts.append("匯率：" + "，".join(fx_line))
    if st:
        best = sorted(st.items(), key=lambda kv: kv[1].get("change",0), reverse=True)
        top = best[0] if best else None
        if top:
            parts.append(f"股市：{top[0]} 變動 {top[1]['change']}%。")
    if news:
        parts.append("頭條：" + news[0]["title"])
    return "。".join(parts) if parts else "今日重點已更新，請查看板塊。"

def maybe_make_tts(summary_text:str):
    """
    若設定 OPENAI_API_KEY，且安裝 openai 套件，嘗試產生 MP3。
    失敗不影響主流程。
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ℹ️ 未設定 OPENAI_API_KEY，跳過 MP3 產生。")
        return
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        # 使用 TTS 模型（依你的帳戶可用資源微調）
        speech = client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=summary_text
        )
        with open(MP3_FILE,"wb") as f:
            f.write(speech.read())
        print("🎧 已產生晨讀 MP3。")
    except Exception as e:
        print(f"⚠️ MP3 產生失敗：{e}（將使用瀏覽器朗讀 fallback）")

def main():
    prev = load_prev()
    ex = get_exchange_rates()
    exch = calc_changes(ex, prev.get("exchange_rates", {}))
    st = get_stock_indexes()
    nw = get_international_news()

    summary_text = build_summary(ex, exch, st, nw)

    result = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "exchange_rates": ex,
        "exchange_changes": exch,  # 相對昨日%
        "stocks": st,
        "news": nw,
        "summary_text": summary_text
    }
    with open(DATA_FILE,"w",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print("✅ 今日早報資料已更新完成！")
    # 可選：產生 MP3
    maybe_make_tts(summary_text)

if __name__ == "__main__":
    main()


