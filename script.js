const $ = (id) => document.getElementById(id);
const fmt = (n, d=2) => (typeof n === 'number' && isFinite(n)) ? n.toFixed(d) : "-";

// 依貨幣對取國旗
const FLAG = {
  "USD/TWD":"🇺🇸/🇹🇼","USD/JPY":"🇺🇸/🇯🇵","USD/EUR":"🇺🇸/🇪🇺","USD/GBP":"🇺🇸/🇬🇧","USD/CNY":"🇺🇸/🇨🇳",
  "USD/AUD":"🇺🇸/🇦🇺","USD/CAD":"🇺🇸/🇨🇦","USD/CHF":"🇺🇸/🇨🇭","USD/HKD":"🇺🇸/🇭🇰",
  "USD/KRW":"🇺🇸/🇰🇷","USD/SGD":"🇺🇸/🇸🇬","USD/INR":"🇺🇸/🇮🇳"
};

function colorForDelta(pct){
  if (pct === null || pct === undefined || isNaN(pct)) return '#0f1118';
  const clamp = Math.max(-3, Math.min(3, pct));
  const ratio = (clamp + 3) / 6; // 0..1
  const r = Math.round(255*(1-ratio));
  const g = Math.round(109 + (255-109)*ratio);
  const b = Math.round(107*(1-ratio) + 145*ratio);
  return `rgba(${r},${g},${b},0.22)`;
}

async function loadJSON(path){
  const res = await fetch(path, {cache:'no-store'});
  if(!res.ok) throw new Error(`fetch ${path}: ${res.status}`);
  return res.json();
}
function pickDaily(arr){
  if(!arr?.length) return null;
  const seed = new Date().toISOString().slice(0,10).replace(/-/g,'');
  const idx = parseInt(seed,10) % arr.length;
  return arr[idx];
}

// ---- 台北時間顯示 ----
function toTaipeiTimeStr(data) {
  if (data?.updated_at && /台北時間/.test(data.updated_at)) return data.updated_at;
  if (data?.updated_at_utc) {
    const d = new Date(data.updated_at_utc);
    if (!isNaN(d)) {
      const tpe = d.toLocaleString("zh-TW", { timeZone: "Asia/Taipei", hour12: false });
      return `${tpe}（台北時間）`;
    }
  }
  if (data?.updated_at) {
    const d = new Date(data.updated_at);
    if (!isNaN(d)) {
      const tpe = d.toLocaleString("zh-TW", { timeZone: "Asia/Taipei", hour12: false });
      return `${tpe}（台北時間）`;
    }
    return data.updated_at;
  }
  return "—";
}

function renderFX(ex, changes){
  const keys = ["USD/TWD","USD/JPY","USD/EUR","USD/GBP","USD/CNY"];
  const main = keys.map(k=>{
  const flag = FLAG[k] ? `<span class="flag">${FLAG[k]}</span>` : '';
    const v = ex?.[k]; const pct = changes?.[k];
    const sign = (pct>0? "↗️" : (pct<0? "↘️" : "→"));
    return `<div class="box">
              <div>${flag}${k}</div>
              <div class="muted">現價：<b>${fmt(v,2)}</b></div>
              <div>變化：<b class="${pct>0?'up':pct<0?'down':'flat'}">${fmt(pct,2)}%</b> ${sign}</div>
            </div>`;
  }).join("");
  $("exchange-data").innerHTML = main;

  const heatList = [
    ["USD/TWD","TWD"],["USD/JPY","JPY"],["USD/EUR","EUR"],
    ["USD/GBP","GBP"],["USD/CNY","CNY"],["USD/AUD","AUD"],
    ["USD/CAD","CAD"],["USD/CHF","CHF"],["USD/HKD","HKD"],
    ["USD/KRW","KRW"],["USD/SGD","SGD"],["USD/INR","INR"]
  ];
  $("fx-heat").innerHTML = heatList.map(([pair,code])=>{
    const pct = changes?.[pair];
    const bg = colorForDelta(pct);
    const arrow = pct>0?"↗":"↘";
    return `<div class="heat" style="background:${bg}">
      <div class="code">${FLAG[pair]||""} ${code}</div>
      <div class="value">變化：<span class="${pct>0?'up':pct<0?'down':'flat'}">${fmt(pct,2)}%</span> ${isNaN(pct)?'':arrow}</div>
    </div>`;
  }).join("");
}

function renderStocks(st){
  if(!st || !Object.keys(st).length){
  $("stocks-list").innerText="目前無法即時取得股市資料（將沿用上次更新數據）";
  const prev = localStorage.getItem("stocks");
  if (prev) {
    try { st = JSON.parse(prev); } catch {}
  }
}
if(st && Object.keys(st).length){
  localStorage.setItem("stocks", JSON.stringify(st));
}

  $("stocks-list").innerHTML = Object.entries(st).map(([name, v])=>{
    const cls = v.change>0?'up':(v.change<0?'down':'flat');
    const arrow = v.change>0?'↗️':(v.change<0?'↘️':'→');
    return `<div>${name}：<b>${fmt(v.price,2)}</b>（<b class="${cls}">${fmt(v.change,2)}%</b>） ${arrow}</div>`;
  }).join("");
}

function renderNews2x3(data){
  const fill = (listId, arr) => {
    $(listId).innerHTML = (arr && arr.length)
      ? arr.map(a=>`<li><a href="${a.url}" target="_blank" rel="noopener">${a.title}</a></li>`).join("")
      : "<li>暫無資料</li>";
  };
  fill("news-eco", data.news_economy);
  fill("news-mkt", data.news_markets);
  fill("news-ai", data.news_ai);
  $("fx-eco").innerText = data.forecast_economy || "暫無";
  $("fx-mkt").innerText = data.forecast_markets || "暫無";
  $("fx-ai").innerText = data.forecast_ai || "暫無";

  // 給 TTS 用
  window.__eco = (data.news_economy||[]).map(x=>x.title);
  window.__mkt = (data.news_markets||[]).map(x=>x.title);
  window.__ai  = (data.news_ai||[]).map(x=>x.title);
}

async function renderMap(changes){
  // 🧩 防呆：若沒資料就顯示提示文字
  if(!changes || Object.keys(changes).length === 0){
    const cache = localStorage.getItem("fx_changes");
    if(cache){
      console.warn("🌍 使用上次的匯率變化資料。");
      changes = JSON.parse(cache);
    } else {
      $("map").outerHTML = "<div style='text-align:center;color:#999;padding:20px'>🌍 匯率地圖暫無資料</div>";
      return;
    }
  } else {
    localStorage.setItem("fx_changes", JSON.stringify(changes));
  }

  try {
    const res = await fetch("https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json");
    const world = await res.json();
    const {features} = ChartGeo.topojson.features(world, world.objects.countries);

    // 映射主要幣別到國家中點（簡化示意）
    const countryCenter = {
      "TWD":[120.97,23.97], "JPY":[138,36], "EUR":[10,51], "GBP":[-2,54], "CNY":[104,35],
      "AUD":[134,-25], "CAD":[-100,57], "CHF":[8,47], "HKD":[114,22], "KRW":[127,36],
      "SGD":[103.8,1.35], "INR":[79,22]
    };

    const dataPoints = Object.entries(countryCenter).map(([code, [lon,lat]])=>{
      const pair = "USD/"+code;
      const v = changes?.[pair];
      return {latitude: lat, longitude: lon, value: isNaN(v)?0:v};
    });

    const ctx = $("map").getContext("2d");
    new Chart(ctx, {
      type: 'bubbleMap',
      data: {
        labels: dataPoints.map(()=> ''),
        datasets: [{
          outline: features,
          showOutline: true,
          backgroundColor: ctx => ctx.raw.value >= 0 ? 'rgba(61,220,145,0.45)' : 'rgba(255,107,107,0.45)',
          data: dataPoints.map(p => ({...p, r: Math.max(2, Math.min(18, Math.abs(p.value) * 3))}))
        }]
      },
      options: {
        plugins: { legend: { display: false } },
        scales: { xy: { projection: 'equalEarth' } }
      }
    });
  } catch (e) {
    console.warn("地圖載入失敗：", e);
  }
}

async function init(){
  $("year").innerText = new Date().getFullYear();

  // 先試 GitHub Pages，再退回本地 data.json
// 決定使用哪個來源：
// - 若網站是在 GitHub Pages (hostname 含 github.io)，走同源 data.json
// - 若在本機測試 (localhost)，走遠端網址
const isPages = location.hostname.endsWith("github.io");
let dataUrl = isPages 
  ? "data.json?v=" + Date.now() 
  : "https://hsiung-crypto.github.io/morning-report/data.json?v=" + Date.now();

let data = await loadJSON(dataUrl).catch(err => {
  console.warn("❌ 載入 data.json 失敗，來源:", dataUrl, err);
  return null;
});

// 若主要來源抓不到，再換備援來源
if (!data) {
  const altUrl = isPages
    ? "https://hsiung-crypto.github.io/morning-report/data.json?v=" + Date.now()
    : "data.json?v=" + Date.now();
  console.log("⚠️ 嘗試備援來源:", altUrl);
  data = await loadJSON(altUrl).catch(() => null);
}

console.log("✅ data.json 來源：", isPages ? "同源 (GitHub Pages)" : "遠端/本地");

  const quotes = await loadJSON('jewish_quotes.json').catch(()=>[]);

  if(data){
    $("update-time").innerText = toTaipeiTimeStr(data);
    renderFX(data.exchange_rates, data.exchange_changes);
    renderStocks(data.stocks);
    renderNews2x3(data);
    renderMap(data.exchange_changes);
  }

  const q = pickDaily(quotes) || {text:"今天就從紀律開始。", note:"規則讓你更自由。"};
  $("quote-text").innerText = `「${q.text}」`;
  $("quote-note").innerText = q.note || "";

  // MP3（若 Actions 產生了就用）
  fetch('morning.mp3', {method:'HEAD'}).then(r=>{
    if(r.ok){
      const audio = $("mp3");
      audio.src = 'morning.mp3';
      audio.style.display = 'block';
      $("tts-fallback").style.display = 'none';
    }
  }).catch(()=>{});

  // 朗讀順序：經濟→股市→AI（各 5 則標題）
      // 朗讀順序：經濟→股市→AI（各 5 則標題）
  $("btn-read").addEventListener('click', ()=>{
    const makeText = (arr, label)=>{
      return (arr||[]).slice(0,5).map(a=>{
        if(typeof a==="string") return a;
        return `${a.title||""}。${a.summary||""}`;
      }).join("。");
    };
    const eco = makeText(window.__eco, "經濟");
    const mkt = makeText(window.__mkt, "股市");
    const ai  = makeText(window.__ai, "AI");
    const text = `今日重點新聞。全球經濟：${eco}。全球股市：${mkt}。AI 智慧：${ai}。`;

    const u = new SpeechSynthesisUtterance(text);
    u.lang = "zh-TW";
    speechSynthesis.speak(u);
  }); // ← 關閉事件監聽器

} // ← 關閉 init 函式

init(); // ← 呼叫初始化

