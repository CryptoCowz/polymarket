const state = { view: "overview", meta: null, summary: null, board: null, prices: null, backtest: null, paper: null, maker: null, horizon: "all", timer: null };

const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[ch]));

const pct = (value, digits = 1) => (value == null || Number.isNaN(value) ? "—" : `${(value * 100).toFixed(digits)}%`);
const cents = (value) => {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(2)}¢`;
};
const num = (value, digits = 2) => (value == null || Number.isNaN(value) ? "—" : Number(value).toFixed(digits));
const cls = (value) => (value == null || value === 0 ? "" : value > 0 ? "pos" : "neg");
const money = (value) => (value == null ? "—" : `$${Number(value).toFixed(3)}`);

async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function setView(view) {
  state.view = view;
  if (location.hash !== `#${view}`) history.replaceState(null, "", `#${view}`);
  if (state.timer) { clearInterval(state.timer); state.timer = null; }
  for (const button of document.querySelectorAll("#nav button")) {
    button.setAttribute("aria-current", button.dataset.view === view ? "page" : "false");
  }
  const root = document.getElementById("view");
  root.innerHTML = "<p class='note'>Loading…</p>";
  const renderers = {
    overview: renderOverview,
    backtest: renderBacktest,
    leaderboard: renderLeaderboard,
    prices: renderPrices,
    paper: renderPaper,
    maker: renderMaker,
  };
  renderers[view]().catch((error) => {
    root.innerHTML = `<div class="card error">${esc(error.message)}</div>`;
  });
}

function cards(items) {
  return `<div class="grid">${items.map((item) => `
    <article class="card stat">
      <div class="k">${esc(item.k)}</div>
      <div class="v ${esc(item.cls || "")}">${esc(item.v)}</div>
      <div class="sub">${esc(item.sub || "")}</div>
    </article>`).join("")}</div>`;
}

async function renderOverview() {
  if (!state.summary) state.summary = await api("/api/summary");
  const summary = state.summary;
  const stats = [];
  for (const row of summary.selected) {
    stats.push({ k: `${row.minutes}m untouched-test hit`, v: pct(row.hit), sub: `${row.trades.toLocaleString()} trades · z ${num(row.z_vs_50)} vs 50%` });
    stats.push({ k: `${row.minutes}m PnL @ $0.50 + 1¢`, v: cents(row.pnl_1c), sub: "Binance outcome, not a Polymarket fill", cls: cls(row.pnl_1c) });
  }
  for (const row of summary.polymarket_primary) {
    stats.push({
      k: `${row.minutes}m Polymarket PnL/share`,
      v: cents(row.avg_pnl_per_share),
      sub: `${row.n_fire.toLocaleString()} markets · cost ${money(row.avg_cost)} · SE ${cents(row.se).replace("+", "")}`,
      cls: cls(row.avg_pnl_per_share),
    });
  }
  document.getElementById("view").innerHTML = `
    <section class="card">
      <h2>What the study actually found</h2>
      <p class="headline">${esc(summary.headline)}</p>
      <p class="fine">Train ${esc(summary.splits.train)} · validation ${esc(summary.splits.validation)} · untouched test ${esc(summary.splits.test)}. ${esc(summary.n_validation_variants)} validation variants, Bonferroni z = ${num(summary.bonferroni_z)}. Source: ${esc(summary.source)}.</p>
    </section>
    ${cards(stats)}
    <section class="card">
      <h3>Computed from the artifacts</h3>
      <ul class="clean">${summary.sentences.map((line) => `<li>${esc(line)}</li>`).join("")}</ul>
      <p class="fine">${esc(summary.fee_note)} ${esc(summary.outcome)}</p>
    </section>`;
}

function formRow() {
  const meta = state.meta;
  const options = meta.signals.map((signal) => `<option value="${esc(signal.id)}">${esc(signal.id)}</option>`).join("");
  return `
    <div class="row">
      <div><label for="signal">Signal</label><select id="signal">${options}</select></div>
      <div><label for="minutes">Window</label>
        <select id="minutes"><option value="5">5 minutes</option><option value="15" selected>15 minutes</option><option value="60">60 minutes</option></select>
      </div>
      <div><label for="start">Start (UTC)</label><input id="start" type="date" value="${esc(meta.suggested_start)}" /></div>
      <div><label for="end">End (UTC, inclusive)</label><input id="end" type="date" value="${esc(meta.suggested_end)}" /></div>
    </div>
    <div class="row" style="margin-top:10px">
      <div><label for="entry">Assumed entry</label><input id="entry" type="number" min="0.01" max="0.99" step="0.01" value="0.50" /></div>
      <div><label for="fee">Fee assumption</label>
        <select id="fee">
          <option value="flat-0.01">Flat 1¢</option>
          <option value="flat-0.03">Flat 3¢</option>
          <option value="polymarket_taker">Polymarket taker 0.07·p·(1−p)</option>
        </select>
      </div>
      <div><label for="spread">Extra spread</label><input id="spread" type="number" min="0" max="0.2" step="0.01" value="0" /></div>
      <div class="actions"><button class="primary" id="run" type="button">Run backtest</button></div>
    </div>
    <p class="fine">The signal is read from the last closed Binance minute before each window. Up means close ≥ open. This does not use a Polymarket fill unless you ask for the separate price sample.</p>`;
}

function backtestBody(result) {
  if (!result) return `<p class="note" id="status"></p>`;
  const published = result.published_polymarket_check;
  const publishedCard = published ? `
    <aside class="card">
      <h3>Published Polymarket check, ${published.minutes}m</h3>
      <p class="warn">${esc(result.published_polymarket_note)}</p>
      <p>Hit ${esc(pct(published.hit))} on ${published.n_fire.toLocaleString()} fired markets. Average cost ${esc(money(published.avg_cost))}. PnL ${esc(cents(published.avg_pnl_per_share))}/share (SE ${esc(cents(published.se))}).</p>
      <p class="fine">Up price when signal was UP ${published.avg_p_up_when_up.toFixed(3)}, DOWN ${published.avg_p_up_when_down.toFixed(3)}, control ${published.avg_p_up_control.toFixed(3)}.</p>
    </aside>` : "";
  return `
    <div class="split">
      <section class="card">
        <h3>Cumulative per-share PnL</h3>
        <canvas class="chart" id="equity"></canvas>
        <p class="fine">${result.trades.toLocaleString()} trades from ${esc(result.eval_start)} to ${esc(result.eval_end)}. Bars actually loaded ${esc(result.data_first)} → ${esc(result.data_last)}.</p>
      </section>
      ${publishedCard}
    </div>
    ${cards([
      { k: "Hit rate", v: pct(result.hit_rate), sub: `Break-even ${pct(result.breakeven_hit_rate)}` },
      { k: "PnL per share", v: cents(result.pnl_per_share), sub: `SE ${cents(result.pnl_se)}`, cls: cls(result.pnl_per_share) },
      { k: "z vs 50%", v: num(result.z_vs_50), sub: `z vs break-even ${num(result.z_vs_breakeven)}` },
    ])}
    <section class="card">
      <h3>Hit rate against this break-even</h3>
      <div id="meter"></div>
      <p>${result.hit_rate > result.breakeven_hit_rate ? "Hit rate is above this break-even under the assumptions of this run." : "Hit rate is below this break-even, so per-share PnL is negative under the assumptions of this run."}</p>
      <p class="fine">${esc(result.z_note)} Simulated bankroll ended at $${num(result.sim_final_bankroll)} after ${result.sim_trades} sized trades${result.sim_killed ? `, and the drawdown stop fired at ${esc(result.sim_killed_at)}` : ""}.</p>
    </section>
    <section class="card">
      <div class="actions">
        <button class="secondary" id="compare" type="button">Compare a sample with public Polymarket prices</button>
        <span class="note">Read-only. Caps at 12 of the most recent fired windows.</span>
      </div>
      <div id="compare-out"></div>
    </section>
    <section class="card">
      <h3>Latest simulated trades in this run</h3>
      <div class="table-wrap"><table>
        <thead><tr><th class="left">Window</th><th>Signal</th><th>Outcome</th><th>PnL/share</th></tr></thead>
        <tbody>${result.recent_trades.map((row) => `<tr>
          <td class="left">${esc(row.t.replace("T", " ").replace("+00:00", "Z"))}</td>
          <td>${esc(row.signal)}</td><td>${esc(row.outcome)}</td>
          <td class="${cls(row.pnl_per_share)}">${esc(cents(row.pnl_per_share))}</td>
        </tr>`).join("")}</tbody>
      </table></div>
      <ul class="clean">${result.assumptions.map((line) => `<li>${esc(line)}</li>`).join("")}</ul>
    </section>
    <p class="note" id="status"></p>`;
}

async function renderBacktest() {
  if (!state.meta) state.meta = await api("/api/meta");
  document.getElementById("view").innerHTML = `
    <section class="card"><h2>Backtest a signal</h2>${formRow()}<p class="note" id="status"></p></section>
    <div id="results">${state.backtest ? backtestBody(state.backtest) : ""}</div>`;
  document.getElementById("signal").value = state.meta.default_signal;
  document.getElementById("run").onclick = runBacktest;
  if (state.backtest) bindBacktestExtras(state.backtest);
}

function bindBacktestExtras(result) {
  const canvas = document.getElementById("equity");
  if (canvas) drawSeries(canvas, result.equity || [], "cum_pnl_per_share");
  const meter = document.getElementById("meter");
  if (meter) meter.innerHTML = zoomMeter(result.hit_rate, result.breakeven_hit_rate);
  const compare = document.getElementById("compare");
  if (compare) compare.onclick = runCompare;
}

async function runBacktest() {
  const button = document.getElementById("run");
  const status = document.getElementById("status");
  button.disabled = true;
  status.textContent = "Fetching public BTC data if it is not cached, then computing…";
  const fee = document.getElementById("fee").value;
  const body = {
    signal: document.getElementById("signal").value,
    minutes: Number(document.getElementById("minutes").value),
    start: document.getElementById("start").value,
    end: document.getElementById("end").value,
    entry: Number(document.getElementById("entry").value),
    spread: Number(document.getElementById("spread").value),
    fee_model: fee.startsWith("flat") ? "flat" : "polymarket_taker",
    flat_fee: fee.startsWith("flat") ? Number(fee.split("-")[1]) : 0.01,
  };
  try {
    state.backtest = await api("/api/backtest", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    document.getElementById("results").innerHTML = backtestBody(state.backtest);
    bindBacktestExtras(state.backtest);
    status.textContent = "";
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function runCompare() {
  const button = document.getElementById("compare");
  const out = document.getElementById("compare-out");
  button.disabled = true;
  out.innerHTML = "<p class='note'>Reading public gamma and prices-history…</p>";
  const fee = document.getElementById("fee").value;
  const body = {
    signal: document.getElementById("signal").value,
    minutes: Number(document.getElementById("minutes").value),
    start: document.getElementById("start").value,
    end: document.getElementById("end").value,
    max_markets: 12,
    spread: Number(document.getElementById("spread").value),
    taker_fee_rate: 0.07,
  };
  if (fee === "flat-0.03") body.taker_fee_rate = 0.07;
  try {
    const data = await api("/api/pm-compare", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const summary = data.summary ? `<p>Sample hit ${esc(pct(data.summary.hit))}, average cost ${esc(money(data.summary.avg_cost))}, PnL ${esc(cents(data.summary.avg_pnl_per_share))}/share on ${data.summary.n} resolved markets.</p>` : "<p>No resolved priced markets in the sample.</p>";
    out.innerHTML = `<p class="fine">${esc(data.note)}</p>${summary}
      <div class="table-wrap"><table><thead><tr><th class="left">Window</th><th>Signal</th><th>Cost</th><th>PnL/share</th></tr></thead>
      <tbody>${data.rows.map((row) => `<tr><td class="left">${esc(row.window)}</td><td>${esc(row.signal)}</td><td>${row.cost == null ? "—" : esc(money(row.cost))}</td><td class="${cls(row.pnl_per_share)}">${esc(cents(row.pnl_per_share))}</td></tr>`).join("")}</tbody></table></div>`;
  } catch (error) {
    out.innerHTML = `<p class="error">${esc(error.message)}</p>`;
  } finally {
    button.disabled = false;
  }
}

function zoomMeter(hit, breakeven) {
  const lo = 0.45;
  const hi = 0.65;
  const place = (value) => Math.max(0, Math.min(100, ((value - lo) / (hi - lo)) * 100));
  return `<div class="meter"><div class="fill" style="width:${place(hit)}%"></div><div class="be" style="left:${place(breakeven)}%"></div></div>
    <div class="meter-scale"><span>45%</span><span>hit ${esc(pct(hit))} · break-even ${esc(pct(breakeven))}</span><span>65%</span></div>`;
}

function drawSeries(canvas, points, key, options = {}) {
  const zero = options.zero !== false;
  const format = options.format || cents;
  const width = canvas.clientWidth || 640;
  const height = 280;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#fffdf8";
  ctx.fillRect(0, 0, width, height);
  if (!points.length) {
    ctx.fillStyle = "#5f564a";
    ctx.fillText("No trades in this range.", 16, 28);
    return;
  }
  const values = points.map((point) => point[key]);
  let min = zero ? Math.min(0, ...values) : Math.min(...values);
  let max = zero ? Math.max(0, ...values) : Math.max(...values);
  if (min === max) { min -= 1; max += 1; }
  const pad = 16;
  const x = (i) => pad + (i / Math.max(points.length - 1, 1)) * (width - pad * 2);
  const y = (value) => pad + (1 - (value - min) / (max - min)) * (height - pad * 2);
  if (zero) {
    ctx.strokeStyle = "#d9cdb6";
    ctx.beginPath();
    ctx.moveTo(pad, y(0));
    ctx.lineTo(width - pad, y(0));
    ctx.stroke();
  }
  ctx.strokeStyle = values[values.length - 1] >= 0 ? "#1e3d34" : "#7d2424";
  ctx.lineWidth = 2;
  ctx.beginPath();
  values.forEach((value, i) => (i === 0 ? ctx.moveTo(x(i), y(value)) : ctx.lineTo(x(i), y(value))));
  ctx.stroke();
  ctx.fillStyle = "#5f564a";
  ctx.font = "12px ui-monospace, Menlo, monospace";
  ctx.fillText(format(values[0]), pad, Math.min(height - 8, Math.max(14, y(values[0]) - 6)));
  ctx.fillText(format(values[values.length - 1]), width - 110, 20);
}

async function renderLeaderboard() {
  if (!state.board) state.board = await api("/api/leaderboard");
  const board = state.board;
  const horizons = ["all", 5, 15, 60];
  const selected = board.selected.map((row) => `<tr>
    <td class="left">${row.minutes}m</td>
    <td class="left">${esc(row.signal)}<div class="fine">${esc(row.description)}</div></td>
    <td>${esc(pct(row.val_hit))}<div class="fine">${row.val_trades.toLocaleString()} · z ${num(row.val_z)}</div></td>
    <td>${row.passes_bonferroni ? "yes" : "no"}</td>
    <td>${row.trades.toLocaleString()}</td>
    <td>${esc(pct(row.hit))}</td>
    <td>${num(row.z_vs_50)}</td>
    <td class="${cls(row.pnl_1c)}">${esc(cents(row.pnl_1c))}</td>
    <td class="${cls(row.pnl_3c)}">${esc(cents(row.pnl_3c))}</td>
  </tr>`).join("");
  const validation = board.validation.filter((row) => state.horizon === "all" || row.minutes === Number(state.horizon));
  document.getElementById("view").innerHTML = `
    <section class="card">
      <h2>Signal leaderboard</h2>
      <p>${esc(board.selection_rule)}</p>
      <p class="warn">${esc(board.multiple_testing_note)}</p>
    </section>
    <section class="card">
      <h3>Untouched test — one precommitted signal per horizon</h3>
      <div class="table-wrap"><table>
        <thead><tr><th class="left">Window</th><th class="left">Signal</th><th>Validation</th><th>Bonferroni</th><th>Test n</th><th>Test hit</th><th>Test z</th><th>PnL @1¢</th><th>PnL @3¢</th></tr></thead>
        <tbody>${selected}</tbody>
      </table></div>
      <p class="fine">PnL columns assume a $0.50 entry on the Binance outcome. They are not Polymarket fills. The 60-minute rule can win the selection rule and still miss the Bonferroni screen.</p>
    </section>
    <section class="card">
      <h3>Validation set, 2025</h3>
      <div class="actions">${horizons.map((horizon) => `<button type="button" class="chip" data-h="${horizon}" aria-pressed="${String(state.horizon) === String(horizon)}">${horizon === "all" ? "All" : `${horizon}m`}</button>`).join("")}</div>
      <div class="table-wrap"><table>
        <thead><tr><th class="left">Window</th><th class="left">Signal</th><th>Train hit</th><th>Val hit</th><th>Val n</th><th>Val z</th><th>Screen</th><th>Picked</th></tr></thead>
        <tbody>${validation.map((row) => `<tr>
          <td class="left">${row.minutes}m</td>
          <td class="left">${esc(row.signal)}</td>
          <td>${esc(pct(row.train_hit))}</td>
          <td>${esc(pct(row.hit))}</td>
          <td>${row.trades.toLocaleString()}</td>
          <td>${num(row.z_vs_50)}</td>
          <td>${row.passes_bonferroni ? "pass" : "no"}</td>
          <td>${row.selected ? "yes" : ""}</td>
        </tr>`).join("")}</tbody>
      </table></div>
    </section>
    <details class="card">
      <summary>Post-hoc 2026 results for every variant</summary>
      <p class="warn">These rows were computed after the test period was already visible. They are not a clean out-of-sample test.</p>
      <div class="table-wrap"><table>
        <thead><tr><th class="left">Window</th><th class="left">Signal</th><th>Hit</th><th>n</th><th>z</th><th>PnL @1¢</th></tr></thead>
        <tbody>${board.posthoc.map((row) => `<tr>
          <td class="left">${row.minutes}m</td><td class="left">${esc(row.signal)}${row.selected ? " · selected" : ""}</td>
          <td>${esc(pct(row.hit))}</td><td>${row.trades.toLocaleString()}</td><td>${num(row.z_vs_50)}</td>
          <td class="${cls(row.pnl_1c)}">${esc(cents(row.pnl_1c))}</td>
        </tr>`).join("")}</tbody>
      </table></div>
    </details>`;
  for (const button of document.querySelectorAll(".chip")) {
    button.onclick = () => { state.horizon = button.dataset.h === "all" ? "all" : Number(button.dataset.h); renderLeaderboard(); };
  }
}

async function renderPrices() {
  if (!state.prices) state.prices = await api("/api/pm-check");
  document.getElementById("view").innerHTML = `
    <section class="card">
      <h2>Real Polymarket prices</h2>
      <p>${esc(state.prices.note)}</p>
    </section>
    <section class="card"><div class="table-wrap"><table>
      <thead><tr>
        <th class="left">Window</th><th class="left">Price</th><th>Spread</th><th>Fired</th><th>Hit</th><th>Avg cost</th><th>PnL/share</th><th>SE</th><th>Up|UP</th><th>Up|DOWN</th><th>Up control</th>
      </tr></thead>
      <tbody>${state.prices.rows.map((row) => `<tr>
        <td class="left">${row.minutes}m${row.primary ? " · primary" : ""}</td>
        <td class="left">${esc(row.price)}</td>
        <td>${esc(cents(row.extra_spread))}</td>
        <td>${row.n_fire.toLocaleString()}</td>
        <td>${esc(pct(row.hit))}</td>
        <td>${esc(money(row.avg_cost))}</td>
        <td class="${cls(row.avg_pnl_per_share)}">${esc(cents(row.avg_pnl_per_share))}</td>
        <td>${esc(cents(row.se))}</td>
        <td>${row.avg_p_up_when_up.toFixed(3)}</td>
        <td>${row.avg_p_up_when_down.toFixed(3)}</td>
        <td>${row.avg_p_up_control.toFixed(3)}</td>
      </tr>`).join("")}</tbody>
    </table></div></section>`;
}

async function renderPaper() {
  if (!state.meta) state.meta = await api("/api/meta");
  const snap = await api("/api/paper/snapshot?minutes=15");
  state.paper = await api("/api/paper/log");
  const options = state.meta.signals.map((signal) => `<option value="${esc(signal.id)}">${esc(signal.id)}</option>`).join("");
  const rsi = snap.signals.find((row) => row.id === "rsi_mr_30_70");
  document.getElementById("view").innerHTML = `
    <section class="card">
      <h2>Paper tape</h2>
      <p class="warn">The button writes a simulated decision to a local log. It does not send an order. Auto-log stays off until you turn it on.</p>
      <div class="grid">
        <article class="stat"><div class="k">BTC (last closed minute)</div><div class="v">${num(snap.btc, 1)}</div><div class="sub">${esc(snap.feature_asof)}</div></article>
        <article class="stat"><div class="k">RSI(14)</div><div class="v">${num(snap.rsi, 1)}</div><div class="sub">${esc(rsi ? rsi.side : "")}</div></article>
        <article class="stat"><div class="k">15m window left</div><div class="v">${Math.floor(snap.seconds_left / 60)}m</div><div class="sub">${esc(snap.window_start)}</div></article>
      </div>
      <canvas class="chart" id="spark" style="margin-top:12px"></canvas>
    </section>
    <section class="card">
      <div class="row">
        <div><label for="psig">Signal to log</label><select id="psig">${options}</select></div>
        <div><label for="pmin">Window</label><select id="pmin"><option value="5">5 minutes</option><option value="15" selected>15 minutes</option><option value="60">60 minutes</option></select></div>
        <div><label for="pentry">Simulated entry</label><select id="pentry"><option value="polymarket_print">Public print at the open</option><option value="half">Assume $0.50</option></select></div>
        <div><label for="pfee">Fee</label><select id="pfee"><option value="polymarket_taker">Taker formula</option><option value="flat">Flat 1¢</option></select></div>
      </div>
      <div class="actions">
        <button class="primary" id="tick" type="button">Log this window</button>
        <label><input id="auto" type="checkbox" /> Auto-log every 30s</label>
        <span class="note" id="pstatus"></span>
      </div>
    </section>
    <section class="card" id="plog"></section>`;
  document.getElementById("psig").value = "rsi_mr_30_70";
  drawSpark(document.getElementById("spark"), snap.spark);
  paintLog(state.paper);
  document.getElementById("tick").onclick = () => logPaper(false);
  document.getElementById("pmin").onchange = async () => {
    const minutes = document.getElementById("pmin").value;
    const next = await api(`/api/paper/snapshot?minutes=${minutes}`);
    drawSpark(document.getElementById("spark"), next.spark);
  };
  document.getElementById("auto").onchange = (event) => {
    if (state.timer) clearInterval(state.timer);
    state.timer = event.target.checked ? setInterval(() => logPaper(true), 30000) : null;
  };
}

function paintLog(payload) {
  const summary = payload.summary || {};
  const host = document.getElementById("plog");
  if (!host) return;
  host.innerHTML = `
    <h3>Local simulated log</h3>
    <p>Settled ${summary.settled ?? 0} · open ${summary.open ?? 0} · skips ${summary.skips ?? 0} · hit ${esc(pct(summary.hit_rate))} · avg ${esc(cents(summary.avg_pnl_per_share))}/share. Sized bankroll $${num(summary.sim_final_bankroll)} ${summary.sim_killed ? "(drawdown stop fired)" : ""}.</p>
    <div class="table-wrap"><table>
      <thead><tr><th class="left">Window</th><th>Side</th><th>Entry</th><th>Fee</th><th>Status</th><th>PnL/share</th></tr></thead>
      <tbody>${(payload.rows || []).slice().reverse().map((row) => `<tr>
        <td class="left">${esc(row.window_start)}<div class="fine">${esc(row.signal_name)} · ${row.minutes}m</div></td>
        <td>${esc(row.signal)}</td>
        <td>${row.entry == null ? "—" : esc(money(row.entry))}<div class="fine">${esc(row.entry_source || "")}</div></td>
        <td>${row.fee == null ? "—" : esc(cents(row.fee))}</td>
        <td>${esc(row.status)}</td>
        <td class="${cls(row.pnl_per_share)}">${esc(cents(row.pnl_per_share))}</td>
      </tr>`).join("") || "<tr><td class='left' colspan='6'>No paper decisions yet.</td></tr>"}</tbody>
    </table></div>`;
}

async function logPaper() {
  const status = document.getElementById("pstatus");
  const button = document.getElementById("tick");
  if (button) button.disabled = true;
  if (status) status.textContent = "Recording a simulated decision…";
  try {
    const data = await api("/api/paper/tick", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        signal: document.getElementById("psig").value,
        minutes: Number(document.getElementById("pmin").value),
        entry_mode: document.getElementById("pentry").value,
        fee_model: document.getElementById("pfee").value,
        flat_fee: 0.01,
      }),
    });
    state.paper = data;
    paintLog(data);
    if (status) status.textContent = data.decision.status === "skip" ? "Signal was neutral. Logged a skip." : `Logged ${data.decision.status}.`;
  } catch (error) {
    if (status) status.textContent = error.message;
  } finally {
    if (button) button.disabled = false;
  }
}

function drawSpark(canvas, values) {
  drawSeries(
    canvas,
    (values || []).map((value) => ({ price: value })),
    "price",
    { zero: false, format: (value) => num(value, 0) },
  );
}

function makerTable(result) {
  if (!result) return "";
  const summary = result.summary || {};
  return `
    <p>Resting orders ${summary.orders_resting ?? 0}, filled ${summary.filled ?? 0}, fill rate ${esc(pct(summary.fill_rate))}. Average PnL on settled fills ${esc(cents(summary.avg_pnl_per_filled_share))}/share. If unfilled resolved orders count as zero, ${esc(cents(summary.avg_pnl_per_posted_order_unfilled_as_zero))}/order. Marketable quotes excluded: ${summary.marketable_skipped ?? 0}.</p>
    <div class="table-wrap"><table>
      <thead><tr><th class="left">Window</th><th>Signal</th><th>Limit</th><th>Min print</th><th>Status</th><th>PnL/share</th></tr></thead>
      <tbody>${result.rows.map((row) => `<tr>
        <td class="left">${esc((row.window || "").replace("T", " ").replace("+00:00", "Z"))}<div class="fine">${esc(row.slug || row.note || "")}</div></td>
        <td>${esc(row.signal || "—")}</td>
        <td>${row.limit == null ? "—" : esc(money(row.limit))}</td>
        <td>${row.min_print == null ? "—" : esc(money(row.min_print))}</td>
        <td>${esc(row.status)}</td>
        <td class="${cls(row.pnl_per_share)}">${esc(cents(row.pnl_per_share))}</td>
      </tr>`).join("")}</tbody>
    </table></div>
    <ul class="clean">${(result.assumptions || []).map((line) => `<li>${esc(line)}</li>`).join("")}</ul>`;
}

async function renderMaker() {
  if (!state.meta) state.meta = await api("/api/meta");
  const options = state.meta.signals.map((signal) => `<option value="${esc(signal.id)}">${esc(signal.id)}</option>`).join("");
  document.getElementById("view").innerHTML = `
    <section class="card">
      <h2>Maker paper test</h2>
      <p>When RSI (or another signal) fires, this posts a hypothetical bid shaded below the public print and checks whether a later prices-history trade would have filled it. Nothing is sent.</p>
      <div class="row">
        <div><label for="msig">Signal</label><select id="msig">${options}</select></div>
        <div><label for="mmin">Window</label><select id="mmin"><option value="5">5 minutes</option><option value="15" selected>15 minutes</option><option value="60">60 minutes</option></select></div>
        <div><label for="mshade">Shade (dollars)</label><input id="mshade" type="number" min="0" max="0.2" step="0.01" value="0.02" /></div>
        <div><label for="manchor">Anchor</label><select id="manchor"><option value="open_print">Last print minus shade</option><option value="half">$0.50 minus shade</option></select></div>
      </div>
      <div class="row" style="margin-top:10px">
        <div><label for="mn">Completed windows</label><input id="mn" type="number" min="4" max="48" value="16" /></div>
        <div><label for="mcap">Max markets to fetch</label><input id="mcap" type="number" min="1" max="24" value="12" /></div>
        <div><label for="mrebate">Rebate / share (default 0)</label><input id="mrebate" type="number" min="0" max="0.05" step="0.001" value="0" /></div>
        <div class="actions"><button class="primary" id="mrun" type="button">Run maker replay</button></div>
      </div>
      <p class="note" id="mstatus"></p>
    </section>
    <section class="card" id="mout">${state.maker ? makerTable(state.maker) : "<p class='note'>No replay yet. The assumptions are applied when the run returns, and they are listed under the table.</p>"}</section>`;
  document.getElementById("msig").value = "rsi_mr_30_70";
  document.getElementById("mrun").onclick = runMaker;
}

async function runMaker() {
  const button = document.getElementById("mrun");
  const status = document.getElementById("mstatus");
  button.disabled = true;
  status.textContent = "Loading BTC bars and public Polymarket prints…";
  try {
    state.maker = await api("/api/maker/replay", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        signal: document.getElementById("msig").value,
        minutes: Number(document.getElementById("mmin").value),
        n_windows: Number(document.getElementById("mn").value),
        max_markets: Number(document.getElementById("mcap").value),
        shade: Number(document.getElementById("mshade").value),
        anchor: document.getElementById("manchor").value,
        rebate: Number(document.getElementById("mrebate").value),
      }),
    });
    document.getElementById("mout").innerHTML = makerTable(state.maker);
    status.textContent = "Replay stored in data/maker_log.jsonl.";
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

document.querySelectorAll("#nav button").forEach((button) => {
  button.onclick = () => setView(button.dataset.view);
});
const initial = (location.hash || "#overview").slice(1);
setView(["overview", "backtest", "leaderboard", "prices", "paper", "maker"].includes(initial) ? initial : "overview");
