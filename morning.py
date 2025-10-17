import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import os
import time
import math

import requests
import feedparser
import yfinance as yf

TIMEOUT = 15
DATA_FILE = "data.json"

def safe_get_json(url, label="", params=None, headers=None):
    try:
        r = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"⚠️ {label} 失敗：{e}")
        return {}

# ---------- 匯率 ----------
def get_exchange_rates(prev=None):
    data = safe_get_json("https://open.er-api.com/v6/latest/USD", label="匯率")
    rates = data.get("rates", {})
    if not rates:
        print("⚠️ 匯率 API 無回傳資料，沿用前一版。")
        return (prev or {}).get("exchange_rates", {})

    wanted = ["TWD","JPY","EUR","GBP","CNY","AUD","CAD","CHF","HKD","KRW","SGD","INR"]
    out = {}
    for code in wanted:
        if code in rates:
            out[f"USD/{code}"] = round(float(rates[code]), 4)
    return out

# ---------- 指數（帶重試＋沿用前值） ----------
IDX_TICKERS = {
    "^DJI":"道瓊", "^IXIC":"那斯達克", "^GSPC":"S&P 500", "^N225":"日經225",
    "^GDAXI":"德國DAX", "^FTSE":"英國FTSE", "^HSI":"恆生指數", "^TWII":"台灣加權"
}

def get_stock_indexes(prev=None):
    result = {}
    tickers = " ".join(IDX_TICKERS.keys())
    for attempt in range(3):
        try:
            data = yf.download(tickers, period="6d", interval="1d",
                               progress=False, group_by='ticker', threads=False, auto_adjust=False)
            # yfinance 可能回不同結構，統一處理
            for t, name in IDX_TICKERS.items():
                try:
                    close = data[t]["Close"] if isinstance(data, dict) and t in data else data["Close"][t]
                except Exception:
                    close = data["Close"][t]
                price = float(close.tail(1).values[0])
                if len(close) >= 2:
                    prev_close = float(close.tail(2).values[0])
                    chg = ((price - prev_close) / prev_close * 100) if prev_close else 0.0
                else:
                    chg = 0.0
                if math.isnan(price) or math.isinf(price):
                    continue
                result[name] = {"price": round(price,2), "change": round(chg,2)}
            break
        except Exception as e:
            print(f"⚠️ yfinance 失敗（{attempt+1}/3）：{e}")
            time.sleep(2)

    if not result and prev:
        print("ℹ️ 指數抓不到，沿用上一版。")
        return prev
    return result

# ---------- RSS 新聞 ----------
RSS_ECONOMY = [
    "http://feeds.bbci.co.uk/news/business/rss.xml",
    "https://feeds.reuters.com/reuters/businessNews",
]
RSS_MARKETS = [
    "https://feeds.reuters.com/reuters/marketsNews",
    "https://www.marketwatch.com/feeds/topstories",
]
RSS_AI = [
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://www.theverge.com/rss/index.xml",
]

def fetch_rss_batch(urls, max_items=5):
    items = []
    for url in urls:
        try:
            d = feedparser.parse(url)
            for e in d.entries[:max_items]:
                title = e.get("title","").strip()
                link = e.get("link","").strip()
                if title and link:
                    items.append({"title": title, "url": link})
        except Exception as ex:
            print(f"⚠️ RSS 讀取失敗：{url} -> {ex}")
    # 去重 + 截前 N
    seen, uniq = set(), []
    for it in items:
        if it["title"] not in seen:
            seen.add(it["title"])
            uniq.append(it)
    return uniq[:max_items]

def short_forecast_from_titles(titles, domain):
    text = "、".join(titles[:5]).lower()
    pos = sum(text.count(k) for k in ["growth","rally","recover","optimism","surge","record","beat"])
    neg = sum(text.count(k) for k in ["risk","fall","slump","recession","crisis","cut","miss"])
    if pos == neg:
        sentiment = "偏穩"
    else:
        sentiment = "偏強" if pos > neg else "偏弱"

    if domain=="economy":
        tip = "留意通膨與政策路徑；建議分批佈局、保留現金彈性。"
    elif domain=="markets":
        tip = "關注高流動性資產；嚴設停損、避免槓桿過高。"
    else:
        tip = "雲端與晶片仍是主軸；追蹤監管進展與估值壓力。"
    return f"{domain}情勢{sentiment}，{tip}"

# ---------- 主流程 ----------
def main():
    prev = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE,"r",encoding="utf-8") as f:
                prev = json.load(f)
        except Exception:
            prev = {}

    ex = get_exchange_rates(prev)
    # 漲跌%：若無前值 => null，避免寫入 NaN
    exch = {}
    for k,v in ex.items():
        p = (prev.get("exchange_rates") or {}).get(k)
        if isinstance(v,(int,float)) and isinstance(p,(int,float)) and p:
            exch[k] = round((v - p)/p*100, 2)
        else:
            exch[k] = None

    st = get_stock_indexes(prev=prev.get("stocks"))

    news_economy = fetch_rss_batch(RSS_ECONOMY, 5)
    news_markets = fetch_rss_batch(RSS_MARKETS, 5)
    news_ai      = fetch_rss_batch(RSS_AI, 5)

    forecast_economy = short_forecast_from_titles([n["title"] for n in news_economy], "經濟") if news_economy else ""
    forecast_markets = short_forecast_from_titles([n["title"] for n in news_markets], "市場") if news_markets else ""
    forecast_ai      = short_forecast_from_titles([n["title"] for n in news_ai], "AI") if news_ai else ""

    now_tpe = datetime.now(ZoneInfo("Asia/Taipei"))
    now_utc = datetime.now(timezone.utc)

    result = {
        "updated_at": now_tpe.strftime("%Y-%m-%d %H:%M:%S (台北時間)"),
        "updated_at_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S (UTC)"),
        "exchange_rates": ex,
        "exchange_changes": exch,
        "stocks": st,
        "news_economy": news_economy,
        "news_markets": news_markets,
        "news_ai": news_ai,
        "forecast_economy": forecast_economy,
        "forecast_markets": forecast_markets,
        "forecast_ai": forecast_ai
    }

    with open(DATA_FILE,"w",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print("✅ data.json 更新完成")

if __name__ == "__main__":
    main()
