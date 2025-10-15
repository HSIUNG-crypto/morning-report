// 讀取 data.json 並更新畫面
async function loadData() {
  try {
    const res = await fetch('data.json', { cache: 'no-store' });
    const data = await res.json();

    // 更新時間
    document.getElementById("update-time").innerText = data.updated_at || "—";

    // 匯率
    const ex = data.exchange_rates || {};
    document.getElementById("exchange-data").innerHTML = `
      USD/TWD：${ex["USD/TWD"] ?? "-"}<br>
      USD/JPY：${ex["USD/JPY"] ?? "-"}<br>
      USD/EUR：${ex["USD/EUR"] ?? "-"}
    `;

    // 新聞
    const list = (data.news || []).map(a =>
      `<li><a href="${a.url}" target="_blank" rel="noopener">${a.title}</a></li>`
    ).join("") || "<li>暫無資料</li>";
    document.getElementById("news-list").innerHTML = list;

    // 股票
    const stocks = data.stocks || {};
    const sKeys = Object.keys(stocks);
    document.getElementById("stocks-list").innerHTML = sKeys.length
      ? sKeys.map(k => {
          const v = stocks[k] || {};
          const ch = (v.change ?? 0);
          const sign = ch > 0 ? "↗️" : (ch < 0 ? "↘️" : "→");
          return `<div>${k}：${v.price ?? "-"}（${(ch ?? 0).toFixed(2)}%） ${sign}</div>`;
        }).join("")
      : "暫無資料";

    // 存起來給語音用
    window.__newsTitles = (data.news || []).map(a => a.title);
  } catch (e) {
    document.getElementById("exchange-data").innerText = "讀取失敗，稍後重試";
    document.getElementById("news-list").innerHTML = "<li>讀取失敗</li>";
    document.getElementById("stocks-list").innerText = "讀取失敗";
    console.error(e);
  }
}

// 語音晨讀
function readMorningNews() {
  const news = window.__newsTitles || [];
  const msg = new SpeechSynthesisUtterance();
  msg.lang = "zh-TW";
  msg.text = `今天的國際早報。重點新聞：${news.slice(0, 5).join("。")}`;
  speechSynthesis.speak(msg);
}

loadData();
