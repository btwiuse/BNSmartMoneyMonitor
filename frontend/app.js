const latestTsEl = document.getElementById("latest-ts");
const symbolCountEl = document.getElementById("symbol-count");
const wsPriceAsOfEl = document.getElementById("ws-price-as-of");
const symbolLastPriceEl = document.getElementById("symbol-last-price");
const latestTableHead = document.querySelector("#latest-table thead");
const latestTableBody = document.querySelector("#latest-table tbody");
const symbolInput = document.getElementById("symbol-input");
const sortFieldInput = document.getElementById("sort-field");
const sortOrderInput = document.getElementById("sort-order");
const minPositionInput = document.getElementById("min-position-input");
const limitInput = document.getElementById("limit-input");
const autoRefreshToggle = document.getElementById("auto-refresh-toggle");
const refreshIntervalInput = document.getElementById("refresh-interval");
const refreshLatestBtn = document.getElementById("refresh-latest");
const loadHistoryBtn = document.getElementById("load-history");
const historyGrid = document.getElementById("history-grid");
const historyTitle = document.getElementById("history-title");
const chartTitle = document.getElementById("chart-title");
const historyChart = document.getElementById("history-chart");
const historyTemplate = document.getElementById("history-card-template");

let autoRefreshTimer = null;

const latestColumns = [
  ["ts_utc", "Timestamp"],
  ["symbol", "Symbol"],
  ["ws_last_price", "WS Last Price"],
  ["trader_long_qty", "Trader Long Qty"],
  ["trader_short_qty", "Trader Short Qty"],
  ["whale_long_qty", "Whale Long Qty"],
  ["whale_short_qty", "Whale Short Qty"],
  ["market_long_short_ratio", "Market L/S"],
  ["trader_long_qty_change_rate", "Trader Long d%"],
  ["whale_long_qty_change_rate", "Whale Long d%"],
];

const seriesConfig = [
  ["trader_long_qty", "#0f766e", "Trader Long Qty"],
  ["trader_short_qty", "#a61b46", "Trader Short Qty"],
  ["whale_long_qty", "#d46b2c", "Whale Long Qty"],
  ["whale_short_qty", "#5b4abf", "Whale Short Qty"],
];

function formatNumber(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  const num = Number(value);
  if (!Number.isFinite(num)) {
    return String(value);
  }
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: num >= 1000 ? 2 : 8,
  }).format(num);
}

function formatTimestamp(ts) {
  if (!ts) {
    return "-";
  }
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) {
    return ts;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  const num = Number(value);
  if (!Number.isFinite(num)) {
    return String(value);
  }
  return `${num >= 0 ? "+" : ""}${(num * 100).toFixed(2)}%`;
}

function renderLatest(rows) {
  latestTableHead.innerHTML = "";
  latestTableBody.innerHTML = "";

  const headRow = document.createElement("tr");
  for (const [, label] of latestColumns) {
    const th = document.createElement("th");
    th.textContent = label;
    headRow.appendChild(th);
  }
  latestTableHead.appendChild(headRow);

  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const [key] of latestColumns) {
      const td = document.createElement("td");
      if (key === "symbol" || key === "ts_utc") {
        td.textContent = key === "ts_utc" ? formatTimestamp(row[key]) : (row[key] ?? "-");
      } else if (key.endsWith("_change_rate")) {
        td.textContent = formatPercent(row[key]);
      } else {
        td.textContent = formatNumber(row[key]);
      }
      tr.appendChild(td);
    }
    tr.addEventListener("click", () => {
      symbolInput.value = row.symbol;
      loadSymbolPanels();
    });
    latestTableBody.appendChild(tr);
  }
}

function renderHistory(rows, symbol) {
  historyGrid.innerHTML = "";
  historyTitle.textContent = symbol ? `${symbol} 历史聚合快照` : "输入 symbol 后查看按时间桶聚合的 trader / whale 多空 qty、变化率与多空比。";

  if (!rows.length) {
    const empty = document.createElement("p");
    empty.textContent = "No rows found.";
    historyGrid.appendChild(empty);
    return;
  }

  for (const row of rows) {
    const fragment = historyTemplate.content.cloneNode(true);
    const article = fragment.querySelector(".history-card");
    fragment.querySelector(".timestamp").textContent = formatTimestamp(row.ts_utc);
    fragment.querySelector(".ratio-chip").textContent = `Market L/S ${formatNumber(row.market_long_short_ratio)}`;
    fragment.querySelector(".trader-long-position").textContent = formatNumber(row.trader_long_qty);
    fragment.querySelector(".trader-short-position").textContent = formatNumber(row.trader_short_qty);
    fragment.querySelector(".trader-ratio").textContent = formatNumber(row.trader_long_short_ratio);
    fragment.querySelector(".trader-change").textContent = formatPercent(row.trader_long_qty_change_rate);
    fragment.querySelector(".whale-long-position").textContent = formatNumber(row.whale_long_qty);
    fragment.querySelector(".whale-short-position").textContent = formatNumber(row.whale_short_qty);
    fragment.querySelector(".whale-ratio").textContent = formatNumber(row.whale_long_short_ratio);
    fragment.querySelector(".whale-change").textContent = formatPercent(row.whale_long_qty_change_rate);
    article.title = row.symbol;
    historyGrid.appendChild(fragment);
  }
}

function renderChart(rows, symbol) {
  chartTitle.textContent = symbol ? `${symbol} 多空 Qty 时间序列` : "点击表格行或输入 symbol 以加载 qty 曲线。";
  historyChart.innerHTML = "";

  if (!rows.length) {
    return;
  }

  const width = 960;
  const height = 320;
  const padding = { top: 24, right: 16, bottom: 32, left: 56 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const values = rows.flatMap((row) => seriesConfig.map(([key]) => Number(row[key] ?? 0)));
  const maxValue = Math.max(...values, 1);

  const svgNs = "http://www.w3.org/2000/svg";
  const group = document.createElementNS(svgNs, "g");
  group.setAttribute("transform", `translate(${padding.left},${padding.top})`);
  historyChart.appendChild(group);

  for (let i = 0; i <= 4; i += 1) {
    const y = (innerHeight / 4) * i;
    const line = document.createElementNS(svgNs, "line");
    line.setAttribute("x1", "0");
    line.setAttribute("x2", String(innerWidth));
    line.setAttribute("y1", String(y));
    line.setAttribute("y2", String(y));
    line.setAttribute("stroke", "rgba(31,26,22,0.12)");
    line.setAttribute("stroke-width", "1");
    group.appendChild(line);
  }

  seriesConfig.forEach(([key, color]) => {
    const points = rows.map((row, index) => {
      const x = rows.length === 1 ? innerWidth / 2 : (innerWidth / (rows.length - 1)) * index;
      const raw = Number(row[key] ?? 0);
      const y = innerHeight - (raw / maxValue) * innerHeight;
      return `${x},${y}`;
    });

    const path = document.createElementNS(svgNs, "polyline");
    path.setAttribute("points", points.join(" "));
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", color);
    path.setAttribute("stroke-width", "3");
    path.setAttribute("stroke-linejoin", "round");
    path.setAttribute("stroke-linecap", "round");
    group.appendChild(path);
  });

  const firstLabel = document.createElementNS(svgNs, "text");
  firstLabel.setAttribute("x", String(padding.left));
  firstLabel.setAttribute("y", String(height - 8));
  firstLabel.setAttribute("fill", "#6e665e");
  firstLabel.setAttribute("font-size", "12");
  firstLabel.textContent = formatTimestamp(rows[0].ts_utc);
  historyChart.appendChild(firstLabel);

  const lastLabel = document.createElementNS(svgNs, "text");
  lastLabel.setAttribute("x", String(width - padding.right));
  lastLabel.setAttribute("y", String(height - 8));
  lastLabel.setAttribute("text-anchor", "end");
  lastLabel.setAttribute("fill", "#6e665e");
  lastLabel.setAttribute("font-size", "12");
  lastLabel.textContent = formatTimestamp(rows[rows.length - 1].ts_utc);
  historyChart.appendChild(lastLabel);

  const maxLabel = document.createElementNS(svgNs, "text");
  maxLabel.setAttribute("x", "6");
  maxLabel.setAttribute("y", String(padding.top + 6));
  maxLabel.setAttribute("fill", "#6e665e");
  maxLabel.setAttribute("font-size", "12");
  maxLabel.textContent = formatNumber(maxValue);
  historyChart.appendChild(maxLabel);
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

async function loadMeta() {
  const payload = await fetchJson("/api/meta");
  latestTsEl.textContent = formatTimestamp(payload.latest_ts);
  symbolCountEl.textContent = payload.symbol_count ?? "-";
  wsPriceAsOfEl.textContent = formatTimestamp(payload.ws_price_as_of);
}

function buildLatestParams() {
  const params = new URLSearchParams();
  const symbol = symbolInput.value.trim().toUpperCase();
  const limit = limitInput.value.trim();
  const minPosition = minPositionInput.value.trim();

  if (symbol) {
    params.set("symbol", symbol);
  }
  if (limit) {
    params.set("limit", limit);
  }
  if (minPosition) {
    params.set("min_position_qty", minPosition);
  }
  params.set("sort_by", sortFieldInput.value);
  params.set("sort_order", sortOrderInput.value);
  return params;
}

async function loadLatest() {
  const payload = await fetchJson(`/api/latest?${buildLatestParams().toString()}`);
  if (payload.latest_ts) {
    latestTsEl.textContent = payload.latest_ts;
  }
  renderLatest(payload.rows ?? []);
}

async function loadHistorySeries(symbol) {
  const params = new URLSearchParams({
    symbol,
    limit: String(Math.max(12, Number(limitInput.value || 30))),
  });
  const payload = await fetchJson(`/api/history-series?${params.toString()}`);
  const rows = payload.rows ?? [];
  renderChart(rows, symbol);
  renderHistory(rows, symbol);
}

async function loadSymbolPrice(symbol) {
  if (!symbol) {
    symbolLastPriceEl.textContent = "-";
    return;
  }
  const payload = await fetchJson(`/api/price?symbol=${encodeURIComponent(symbol)}`);
  symbolLastPriceEl.textContent = payload.last_price === null || payload.last_price === undefined
    ? "-"
    : `${formatNumber(payload.last_price)} (${formatTimestamp(payload.as_of)})`;
}

async function loadSymbolPanels() {
  const symbol = symbolInput.value.trim().toUpperCase();
  if (!symbol) {
    renderHistory([], "");
    renderChart([], "");
    symbolLastPriceEl.textContent = "-";
    return;
  }
  await Promise.all([loadHistorySeries(symbol), loadSymbolPrice(symbol)]);
}

function resetAutoRefresh() {
  if (autoRefreshTimer) {
    clearInterval(autoRefreshTimer);
    autoRefreshTimer = null;
  }
  if (!autoRefreshToggle.checked) {
    return;
  }
  const interval = Math.max(5000, Number(refreshIntervalInput.value || 30000));
  autoRefreshTimer = setInterval(() => {
    Promise.all([loadMeta(), loadLatest(), loadSymbolPanels()]).catch(console.error);
  }, interval);
}

refreshLatestBtn.addEventListener("click", () => {
  Promise.all([loadMeta(), loadLatest()]).catch(console.error);
});

loadHistoryBtn.addEventListener("click", () => {
  loadSymbolPanels().catch(console.error);
});

[sortFieldInput, sortOrderInput, minPositionInput, limitInput].forEach((element) => {
  element.addEventListener("change", () => {
    loadLatest().catch(console.error);
  });
});

autoRefreshToggle.addEventListener("change", resetAutoRefresh);
refreshIntervalInput.addEventListener("change", resetAutoRefresh);

symbolInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    loadSymbolPanels().catch(console.error);
  }
});

window.addEventListener("load", async () => {
  await Promise.all([loadMeta(), loadLatest()]);
  resetAutoRefresh();
});
