import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import os
import time

import requests
import feedparser
import yfinance as yf

TIMEOUT = 12
DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")
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

# ---------- 匯率 ----------
def get_exchange_rates(prev=None):
    data = safe_get_json("https://open.er-api.com/v6/latest/USD", label="匯率")
    rates = data.get("rates", {})

    # 🧩 新增這段防呆：如果 rates 為空，使用上一版資料
    if not rates:
        print("⚠️ 匯率 API 無法回傳 rates，使用上一版資料。")
        return prev.get("exchange_rates", {}) if prev else {}

    wanted = ["TWD","JPY","EUR","GBP","CNY","AUD","CAD","CHF","HKD","KRW","SGD","INR"]
    out = {}
    for code in wanted:
        if code in rates:
            out[f"USD/{code}"] = round(float(rates[code]), 4)
    return out

# ---------- 指數（含重試、備援、沿用前值） ----------
IDX_TICKERS = {
    "^DJI":"道瓊", "^IXIC":"那斯達克", "^GSPC":"S&P 500", "^N225":"日經225",
    "^GDAXI":"德國DAX", "^FTSE":"英國FTSE", "^HSI":"恆生指數", "^TWII":"台灣加權"
}
def get_stock_indexes(prev=None):
    result = {}
    tickers = " ".join(IDX_TICKERS.keys())
    ok = False
    for attempt in range(3):
        try:
            data = yf.download(tickers, period="6d", interval="1d",
                               progress=False, group_by='ticker', threads=False)
            ok = True
            break
        except Exception as e:
            print(f"⚠️ yfinance 失敗({attempt+1}/3)：{e}")
            time.sleep(2)
    if ok:
        try:
            # yfinance 有兩種結構，統一處理
            for t, name in IDX_TICKERS.items():
                try:
                    close_series = data[t]["Close"] if isinstance(data, dict) and t in data else data["Close"][t]
                except Exception:
                    close_series = data["Close"][t]
                price = float(close_series.tail(1).values[0])
                if len(close_series) >= 2:
                    prev_close = float(close_series.tail(2).values[0])
                    chg = ((price - prev_close) / prev_close) * 100 if prev_close else 0.0
                else:
                    chg = 0.0
                result[name] = {"price": round(price,2), "change": round(chg,2)}
        except Exception as e:
            print(f"⚠️ yfinance 解析失敗：{e}")
    # 抓不到就沿用前值（避免前端空白）
    if not result and prev:
        print("ℹ️ 指數抓取失敗，沿用上一版數據。")
        return prev
    return result

# ---------- 新聞（分三類） ----------
RSS_ECONOMY = [
    "http://feeds.bbci.co.uk/news/business/rss.xml",
    "https://feeds.reuters.com/reuters/businessNews",
    "https://www.ft.com/rss/home/asia",  # FT 全站 RSS，仍能挑到商業經濟
]
RSS_MARKETS = [
    "https://feeds.reuters.com/reuters/marketsNews",
    "https://www.marketwatch.com/feeds/topstories",  # MarketWatch
    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",  # Bloomberg 部分 feed（示意）
]
RSS_AI = [
    "https://feeds.arstechnica.com/arstechnica/technology-lab", # 科技/AI
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.feedburner.com/TechCrunch/"
]

# 🧩 RSS 讀取：加上 User-Agent，避免伺服器拒絕匿名連線
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NightCatMorning/1.0; +https://github.com/HSIUNG-crypto/morning-report)"
}

def fetch_rss_batch(urls, max_items=5):
    items = []
    for url in urls:
        try:
            # ✅ 關鍵修改點：加上 request_headers=HEADERS
            d = feedparser.parse(url, request_headers=HEADERS)
            for e in d.entries[:max_items]:
                title = e.get("title","").strip()
                link = e.get("link","").strip()
                if title and link:
                    items.append({"title": title, "url": link})
        except Exception as ex:
            print(f"⚠️ RSS 讀取失敗：{url} -> {ex}")
    # 去重 + 取前 N
    seen, uniq = set(), []
    for it in items:
        if it["title"] not in seen:
            seen.add(it["title"])
            uniq.append(it)
    return uniq[:max_items]

def short_forecast_from_titles(titles, domain):
    """
    超簡短 100 字內「情勢預測」：以關鍵詞方向+保守用語，避免過度武斷。
    domain: 'economy' | 'markets' | 'ai'
    """
    text = "、".join(titles[:5])
    text = text.lower()
    pos = sum(text.count(k) for k in ["growth","expansion","optimism","rally","recover","boom","record","surge"])
    neg = sum(text.count(k) for k in ["slow","recession","decline","fall","slump","risk","crisis","cut"])
    neu = sum(text.count(k) for k in ["flat","mixed","steady","unchanged","pause"])
    sentiment = "偏穩" if max(pos,neg,neu)==neu else ("偏強" if pos>=neg else "偏弱")

    if domain=="economy":
        base = f"整體經濟訊號{sentiment}。"
        tip = "留意通膨與政策路徑，控制部位，遇波動以分批為宜。"
    elif domain=="markets":
        base = f"市場情緒{sentiment}，板塊輪動可能加速。"
        tip = "建議聚焦高流動性資產，嚴設停損與風險限額。"
    else: # ai
        base = f"AI 動能{sentiment}，技術與監管消息交錯。"
        tip = "短期以大型雲/晶片為主軸，留意評價壓力。"
    s = f"{base}{tip}"
    return s[:95] + "…" if len(s)>100 else s

def load_prev():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def calc_changes(curr: dict, prev: dict):
    out = {}
    for k,v in curr.items():
        p = prev.get(k)
        if isinstance(v,(int,float)) and isinstance(p,(int,float)) and p:
            out[k] = round((v - p)/p*100, 2)
        else:
            out[k] = None
    return out

def build_summary(ex, exch, st, news_ec, news_mk, news_ai):
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
    if news_ec:
        parts.append("經濟：" + news_ec[0]["title"])
    return "。".join(parts) if parts else "今日重點已更新，請查看板塊。"

def maybe_make_tts(summary_text:str):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ℹ️ 未設定 OPENAI_API_KEY，跳過 MP3 產生。")
        return
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
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

    ex = get_exchange_rates(prev=prev)
    exch = calc_changes(ex, prev.get("exchange_rates", {}))

    st = get_stock_indexes(prev=prev.get("stocks"))
    news_economy = fetch_rss_batch(RSS_ECONOMY, 5)
    news_markets = fetch_rss_batch(RSS_MARKETS, 5)
    news_ai = fetch_rss_batch(RSS_AI, 5)

    forecast_economy = short_forecast_from_titles([n["title"] for n in news_economy], "economy") if news_economy else ""
    forecast_markets = short_forecast_from_titles([n["title"] for n in news_markets], "markets") if news_markets else ""
    forecast_ai = short_forecast_from_titles([n["title"] for n in news_ai], "ai") if news_ai else ""

    summary_text = build_summary(ex, exch, st, news_economy, news_markets, news_ai)

    now_tpe = datetime.now(ZoneInfo("Asia/Taipei"))
    now_utc = datetime.now(timezone.utc)

    result = {
        "updated_at": now_tpe.strftime("%Y-%m-%d %H:%M:%S") + " (台北時間)",
        "updated_at_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S") + " (UTC)",
        "exchange_rates": ex,
        "exchange_changes": exch,
        "stocks": st,
        "news_economy": news_economy,
        "news_markets": news_markets,
        "news_ai": news_ai,
        "forecast_economy": forecast_economy,
        "forecast_markets": forecast_markets,
        "forecast_ai": forecast_ai,
        "summary_text": summary_text
    }
    with open(DATA_FILE,"w",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print("✅ 今日早報資料已更新完成！")
    maybe_make_tts(summary_text)

if __name__ == "__main__":
    main()
