const $ = (id) => document.getElementById(id);
const fmt = (n, d=2) => (typeof n === 'number' && isFinite(n)) ? n.toFixed(d) : "-";

// ---- 新增：把時間顯示為台北時間 ----
function toTaipeiTimeStr(data) {
  // 1) 若 updated_at 已含「(台北時間)」字樣就直接顯示
  if (data?.updated_at && /台北時間/.test(data.updated_at)) {
    return data.updated_at;
  }
  // 2) 否則若有 updated_at_utc，轉為台北時區再顯示
  if (data?.updated_at_utc) {
    const d = new Date(data.updated_at_utc);
    if (!isNaN(d)) {
      const tpe = d.toLocaleString("zh-TW", { timeZone: "Asia/Taipei", hour12: false });
      return `${tpe}（台北時間）`;
    }
  }
  // 3) 最後嘗試把 updated_at 當一般日期解析並顯示為台北時區
  if (data?.updated_at) {
    const d = new Date(data.updated_at);
    if (!isNaN(d)) {
      const tpe = d.toLocaleString("zh-TW", { timeZone: "Asia/Taipei", hour12: false });
      return `${tpe}（台北時間）`;
    }
    return data.updated_at; // 解析不了就原樣
  }
  return "—";
}

function colorForDelta(pct){
  // -3% = 紅, 0 = 中性, +3% = 綠（夾在中間做漸層）
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
  const seed = new Date().toISOString().slice(0,10).replace(/-/g,''); // YYYYMMDD
  const idx = parseInt(seed,10) % arr.length;
  return arr[idx];
}

function renderFX(ex, changes){
  // 主要幣別
  const keys = ["USD/TWD","USD/JPY","USD/EUR","USD/GBP","USD/CNY"];
  const labels = {
    "USD/TWD":"USD/TWD", "USD/JPY":"USD/JPY", "USD/EUR":"USD/EUR",
    "USD/GBP":"USD/GBP", "USD/CNY":"USD/CNY"
  };
  const main = keys.map(k=>{
    const v = ex?.[k]; const pct = changes?.[k];
    const sign = (pct>0? "↗️" : (pct<0? "↘️" : "→"));
    return `<div class="box"><div>${labels[k]}</div>
            <div class="muted">現價：<b>${fmt(v,2)}</b></div>
            <div>變化：<b class="${pct>0?'up':pct<0?'down':'flat'}">${fmt(pct,2)}%</b> ${sign}</div></div>`;
  }).join("");
  $("exchange-data").innerHTML = main;

  // 熱度格（更多幣別可自行擴充）
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
      <div class="code">${code}</div>
      <div class="value">變化：<span class="${pct>0?'up':pct<0?'down':'flat'}">${fmt(pct,2)}%</span> ${isNaN(pct)?'':arrow}</div>
    </div>`;
  }).join("");
}

function renderStocks(st){
  if(!st || !Object.keys(st).length){ $("stocks-list").innerText="暫無資料"; return; }
  $("stocks-list").innerHTML = Object.entries(st).map(([name, v])=>{
    const cls = v.change>0?'up':(v.change<0?'down':'flat');
    const arrow = v.change>0?'↗️':(v.change<0?'↘️':'→');
    return `<div>${name}：<b>${fmt(v.price,2)}</b>（<b class="${cls}">${fmt(v.change,2)}%</b>） ${arrow}</div>`;
  }).join("");
}

function renderNews(list){
  $("news-list").innerHTML = (list && list.length)
    ? list.map(a=>`<li><a href="${a.url}" target="_blank" rel="noopener">${a.title}</a></li>`).join("")
    : "<li>暫無資料</li>";
  // 儲存給 TTS
  window.__newsTitles = (list||[]).slice(0,5).map(a=>a.title);
}

async function init(){
  $("year").innerText = new Date().getFullYear();

  // 載入資料
  const data = await loadJSON('data.json').catch(()=>null);
  const quotes = await loadJSON('jewish_quotes.json').catch(()=>[]);

  if(data){
    $("update-time").innerText = toTaipeiTimeStr(data);
    renderFX(data.exchange_rates, data.exchange_changes);
    renderStocks(data.stocks);
    renderNews(data.news);
  }

  // 金句：依日期穩定挑選
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

  // Fallback：用瀏覽器語音朗讀
  $("btn-read").addEventListener('click', ()=>{
    const news = (window.__newsTitles||[]).join("。");
    const summary = (data && data.summary_text) ? data.summary_text : `今日重點新聞：${news}`;
    const u = new SpeechSynthesisUtterance(summary);
    u.lang = "zh-TW";
    speechSynthesis.speak(u);
  });
}

init();
