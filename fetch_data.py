import json
from datetime import datetime
import requests
import feedparser
import yfinance as yf

TIMEOUT = 12

def safe_get_json(url, headers=None, params=None, label=""):
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        # 某些服務不標 JSON header，但內容是 JSON，容錯處理
        try:
            return resp.json()
        except Exception:
            print(f"⚠️ {label} 回傳非標準 JSON，略過解析。前200字：{resp.text[:200]!r}")
            return {}
    except requests.RequestException as e:
        print(f"⚠️ {label} 網路/服務錯誤：{e}")
        return {}

# 1) 匯率（穩定免費源）
def get_exchange_rates():
    url = "https://open.er-api.com/v6/latest/USD"
    data = safe_get_json(url, label="匯率")
    rates = data.get("rates", {})
    if not rates:
        return {}
    return {
        "USD/TWD": round(rates.get("TWD", 0), 2),
        "USD/JPY": round(rates.get("JPY", 0), 2),
        "USD/EUR": round(rates.get("EUR", 0), 2),
    }

# 2) 股市：使用 yfinance（不需 API key）
# 指數代號：
#   ^DJI (道瓊) ^IXIC (那斯達克) ^GSPC (S&P 500) ^N225 (日經225)
def get_stock_indexes():
    tickers = ["^DJI", "^IXIC", "^GSPC", "^N225"]
    result = {}
    try:
        data = yf.download(tickers=" ".join(tickers), period="1d", interval="1d", progress=False, group_by='ticker', threads=False)
        # yfinance 的結構可能因多 ticker 變化，這裡簡單處理收盤價與漲跌%（相對前一日）
        for t in tickers:
            try:
                # 嘗試從單一欄位結構讀
                close_series = data[t]["Close"] if isinstance(data, dict) and t in data else data["Close"][t]
                # 只有1天資料時取最後一筆
                price = float(close_series.tail(1).values[0])
                # 取前一筆做漲跌百分比（若沒有就 0）
                if len(close_series) >= 2:
                    prev = float(close_series.tail(2).values[0])
                    change_pct = ((price - prev) / prev) * 100 if prev else 0.0
                else:
                    change_pct = 0.0
                name_map = {
                    "^DJI": "道瓊",
                    "^IXIC": "那斯達克",
                    "^GSPC": "S&P 500",
                    "^N225": "日經225"
                }
                result[name_map.get(t, t)] = {"price": round(price, 2), "change": round(change_pct, 2)}
            except Exception as e:
                print(f"⚠️ 股市({t}) 解析失敗：{e}")
                continue
    except Exception as e:
        print(f"⚠️ 股市(yfinance) 取得失敗：{e}")
    return result

# 3) 新聞：RSS（不需金鑰）
RSS_FEEDS = [
    "http://feeds.bbci.co.uk/news/business/rss.xml",
    "https://feeds.reuters.com/reuters/businessNews",
    "https://feeds.reuters.com/news/wealth",      # 財富/市場觀察
    "https://www.ft.com/world?format=rss",        # FT World（有時候會跳轉，取決於地區）
]

def get_international_news(max_items=6):
    items = []
    for url in RSS_FEEDS:
        try:
            d = feedparser.parse(url)
            for e in d.entries[: max(2, max_items // len(RSS_FEEDS) + 1)]:
                title = e.get("title", "").strip()
                link = e.get("link", "").strip()
                if title and link:
                    items.append({"title": title, "url": link})
        except Exception as ex:
            print(f"⚠️ RSS 讀取失敗：{url} -> {ex}")
    # 去重與截斷
    seen = set()
    uniq = []
    for it in items:
        if it["title"] not in seen:
            seen.add(it["title"])
            uniq.append(it)
    return uniq[:max_items] if uniq else []

def main():
    result = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "exchange_rates": get_exchange_rates(),
        "stocks": get_stock_indexes(),
        "news": get_international_news()
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("✅ 今日早報資料已更新完成！")

if __name__ == "__main__":
    main()


