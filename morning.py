# -*- coding: utf-8 -*-
"""
morning.py
產生 data.json：匯率 / 指數 / 新聞（3 欄位）/ 短評 / 台北與 UTC 時間
重點修正：
- 防止 NaN/Infinity 進入 JSON（造成前端 SyntaxError）
- yfinance 偶爾缺值時安全處理、必要時沿用上一版
"""

import json
import math
import os
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import feedparser
import requests
import yfinance as yf

TIMEOUT = 12
DATA_FILE = "data.json"

# -------------------------------
# 通用：安全取 JSON
# -------------------------------
def safe_get_json(url, label="", params=None, headers=None):
    try:
        r = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"⚠️ {label} 錯誤：{e}")
        return {}

# -------------------------------
# 匯率
# -------------------------------
def get_exchange_rates(prev=None):
    data = safe_get_json("https://open.er-api.com/v6/latest/USD", label="匯率")
    rates = data.get("rates", {})

    if not rates:
        print("⚠️ 匯率 API 無回傳資料，使用上一版。")
        return (prev or {}).get("exchange_rates", {}) if prev else {}

    wanted = ["TWD","JPY","EUR","GBP","CNY","AUD","CAD","CHF","HKD","KRW","SGD","INR"]
    out = {}
    for code in wanted:
        if code in rates:
            try:
                val = float(rates[code])
                if not math.isfinite(val):
                    val = 0.0
                out[f"USD/{code}"] = round(val, 4)
            except Exception:
                out[f"USD/{code}"] = 0.0
    return out

# -------------------------------
# 指數
# -------------------------------
IDX_TICKERS = {
    "^DJI": "道瓊",
    "^IXIC": "那斯達克",
    "^GSPC": "S&P 500",
    "^N225": "日經225",
    "^GDAXI": "德國DAX",
    "^FTSE": "英國FTSE",
    "^HSI": "恆生指數",
    "^TWII": "台灣加權",
}

def _safe_round_number(x, nd=2, default=0.0):
    try:
        x = float(x)
        if not math.isfinite(x):
            return float(default)
        return round(x, nd)
    except Exception:
        return float(default)

def get_stock_indexes(prev=None):
    """
    回傳：
    { "道瓊": {"price": 123.45, "change": -0.67}, ... }
    任何抓取錯誤會回退上一版（若有）
    """
    result = {}
    tickers_str = " ".join(IDX_TICKERS.keys())

    # yfinance 在網路/來源出問題時容易拋錯或回傳缺欄位，包 try with retry
    last_err = None
    for attempt in range(3):
        try:
            data = yf.download(
                tickers_str,
                period="6d",
                interval="1d",
                progress=False,
                group_by="ticker",
                threads=False,
                auto_adjust=True,  # 新版預設改為 True，明確指定
            )
            last_err = None
            break
        except Exception as e:
            last_err = e
            print(f"⚠️ yfinance 失敗({attempt+1}/3)：{e}")
            time.sleep(2)

    if last_err:
        print("⚠️ yfinance 多次失敗，沿用上一版資料（若有）。")
        return prev or {}

    # yfinance 在單/多標的時的結構不同，統一安全取值
    def get_close_series(df, ticker):
        """容忍多層欄位或單層 MultiIndex 的結構差異"""
        try:
            # 多標的回傳：data["Close"][ticker]
            if "Close" in df:
                s = df["Close"][ticker]
            else:
                # 單標的回傳：data["Close"]
                s = df[ticker]["Close"]
        except Exception:
            try:
                s = df[ticker]["Close"]
            except Exception:
                s = None
        return s

    for t, name in IDX_TICKERS.items():
        try:
            close = get_close_series(data, t)
            if close is None or len(close) == 0:
                raise ValueError("close series empty")

            # 取最後收盤 & 倒數第二天
            price_raw = close.tail(1).values[0]
            prev_raw = close.tail(2).values[0] if len(close) >= 2 else None

            price = _safe_round_number(price_raw, 2, default=0.0)
            if prev_raw is None or not math.isfinite(float(prev_raw)) or float(prev_raw) == 0:
                change = 0.0
            else:
                change_calc = ((float(price_raw) - float(prev_raw)) / float(prev_raw)) * 100.0
                change = _safe_round_number(change_calc, 2, default=0.0)

            result[name] = {"price": price, "change": change}
        except Exception as e:
            print(f"⚠️ 解析 {t} 失敗：{e}")
            # 若單一標的失敗，嘗試使用上一版對應標的
            if prev and name in prev:
                result[name] = prev[name]
            else:
                result[name] = {"price": 0.0, "change": 0.0}

    # 若全部都是 0 且上一版有資料，就沿用上一版（避免整塊空白）
    if not any(v.get("price", 0) for v in result.values()) and prev:
        print("ℹ️ 指數全為 0，沿用上一版資料。")
        return prev

    return result

# -------------------------------
# 新聞 RSS
# -------------------------------
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
            for e in d.entries[: max_items]:
                title = (e.get("title") or "").strip()
                link = (e.get("link") or "").strip()
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
    100 字內情勢簡評（保守用語），避免武斷。
    domain: 'economy' | 'markets' | 'ai'
    """
    text = "、".join(titles[:5]).lower()
    pos = sum(text.count(k) for k in ["growth","rally","recover","optimism","surge","record","boom"])
    neg = sum(text.count(k) for k in ["risk","fall","slump","recession","crisis","cut","slow"])
    if pos == neg:
        sentiment = "偏穩"
    else:
        sentiment = "偏強" if pos > neg else "偏弱"

    if domain == "economy":
        tip = "留意通膨與政策路徑，控制部位，遇波動以分批為宜。"
    elif domain == "markets":
        tip = "聚焦高流動性資產，嚴設停損與風險限額。"
    else:
        tip = "短期以大型雲/晶片為主軸，留意評價壓力。"
    s = f"{sentiment}。{tip}"
    return s if len(s) <= 100 else (s[:95] + "…")

# -------------------------------
# 主流程
# -------------------------------
def main():
    prev = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                prev = json.load(f)
        except Exception as e:
            print(f"⚠️ 讀取舊 data.json 失敗：{e}")
            prev = {}

    # 匯率 & 漲跌%
    ex = get_exchange_rates(prev)
    exch = {}
    for k, v in ex.items():
        pv = (prev.get("exchange_rates") or {}).get(k)
        if isinstance(v, (int, float)) and isinstance(pv, (int, float)) and pv:
            delta = (v - pv) / pv * 100.0
            exch[k] = _safe_round_number(delta, 2, default=0.0)
        else:
            exch[k] = 0.0

    # 指數
    st = get_stock_indexes(prev.get("stocks"))

    # 新聞
    news_economy = fetch_rss_batch(RSS_ECONOMY, 5)
    news_markets = fetch_rss_batch(RSS_MARKETS, 5)
    news_ai = fetch_rss_batch(RSS_AI, 5)

    forecast_economy = short_forecast_from_titles([n["title"] for n in news_economy], "economy") if news_economy else ""
    forecast_markets = short_forecast_from_titles([n["title"] for n in news_markets], "markets") if news_markets else ""
    forecast_ai = short_forecast_from_titles([n["title"] for n in news_ai], "ai") if news_ai else ""

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
        "forecast_ai": forecast_ai,
    }

    # 最後一層保險：把所有數值確保為有限數
    def sanitize_numbers(obj):
        if isinstance(obj, dict):
            return {k: sanitize_numbers(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [sanitize_numbers(v) for v in obj]
        if isinstance(obj, float):
            return float(obj) if math.isfinite(obj) else 0.0
        return obj

    result = sanitize_numbers(result)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("✅ data.json 更新完成")

if __name__ == "__main__":
    main()
