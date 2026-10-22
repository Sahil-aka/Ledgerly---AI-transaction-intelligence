const API = "/api";
const TOKEN_KEY = "ledgerly.access-token";
const state = { token: sessionStorage.getItem(TOKEN_KEY), user: null, jobs: [], selected: null, poller: null, authMode: "login" };
const app = document.getElementById("app");

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
}
function money(value, currency = "INR") {
  if (value == null) return "—";
  try { return new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 0 }).format(Number(value)); }
  catch { return `${currency} ${Number(value).toLocaleString()}`; }
}
function date(value) { return value ? new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "—"; }
async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.token) headers.set("Authorization", `Bearer ${state.token}`);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API}${path}`, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401 && state.token) { clearSession(); renderAuth(); }
  if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
  return data;
}
function showToast(message, error = false) {
  document.querySelector(".toast")?.remove();
  const toast = document.createElement("div");
  toast.className = `toast${error ? " error" : ""}`;
  toast.textContent = message;
  document.body.append(toast);
  window.setTimeout(() => toast.remove(), 4200);
}
function clearSession() {
  state.token = null; state.user = null; state.jobs = []; state.selected = null;
  sessionStorage.removeItem(TOKEN_KEY);
  if (state.poller) window.clearInterval(state.poller);
  state.poller = null;
}
function renderAuth(mode = state.authMode) {
  state.authMode = mode;
  const signup = mode === "signup";
  app.innerHTML = `
    <main class="auth-shell">
      <section class="auth-story">
        <div class="brand"><span class="brand-mark">L</span><span>ledgerly<small>TRANSACTION INTELLIGENCE</small></span></div>
        <div class="story-copy"><span class="eyebrow">Clarity in every line item</span><h1>Your money,<br><em>in focus.</em></h1><p>Turn messy transaction files into a clear picture of where money moves, what stands out, and what deserves a closer look.</p></div>
        <div class="story-foot"><span>BUILT FOR BETTER DECISIONS</span><span>01 — 04</span></div>
      </section>
      <section class="auth-panel"><form class="auth-card" id="auth-form">
        <span class="eyebrow">Your workspace</span><h2>${signup ? "Create your account" : "Welcome back"}</h2><p>${signup ? "Set up a private space for your transaction analyses." : "Sign in to pick up where you left off."}</p>
        <div class="auth-tabs"><button type="button" data-mode="login" class="${signup ? "" : "active"}">Sign in</button><button type="button" data-mode="signup" class="${signup ? "active" : ""}">Create account</button></div>
        ${signup ? `<div class="field"><label for="name">Your name</label><input id="name" name="name" autocomplete="name" placeholder="Alex Morgan" required maxlength="100" /></div>` : ""}
        <div class="field"><label for="email">Email address</label><input id="email" name="email" type="email" autocomplete="email" placeholder="you@example.com" required maxlength="320" /></div>
        <div class="field"><label for="password">Password</label><input id="password" name="password" type="password" autocomplete="${signup ? "new-password" : "current-password"}" placeholder="${signup ? "At least 10 characters" : "Your password"}" required minlength="${signup ? "10" : "1"}" maxlength="128" /></div>
        <button class="button auth-submit" type="submit">${signup ? "Create secure account" : "Sign in to Ledgerly"}</button><p class="form-message" id="auth-message" role="status"></p>
        <div class="auth-note">Your analyses are private to your account. Passwords are stored as secure hashes, never as plain text.</div>
      </form></section>
    </main>`;
  app.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", () => renderAuth(button.dataset.mode)));
  app.querySelector("#auth-form").addEventListener("submit", submitAuth);
}
async function submitAuth(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  const message = form.querySelector("#auth-message");
  button.disabled = true; button.innerHTML = '<span class="spinner"></span> Please wait'; message.textContent = "";
  const payload = Object.fromEntries(new FormData(form).entries());
  try {
    const data = await request(`/auth/${state.authMode}`, { method: "POST", body: JSON.stringify(payload) });
    state.token = data.access_token; state.user = data.user; sessionStorage.setItem(TOKEN_KEY, state.token);
    await loadWorkspace();
  } catch (error) {
    message.textContent = error.message;
    button.disabled = false; button.textContent = state.authMode === "signup" ? "Create secure account" : "Sign in to Ledgerly";
  }
}
function statusPill(status) { return `<span class="status-pill ${escapeHtml(status)}">${escapeHtml(status)}</span>`; }
function renderDashboard() {
  const firstName = (state.user?.name || state.user?.email || "there").split(/[\s@]/)[0];
  const totalJobs = state.jobs.length;
  const completed = state.jobs.filter((job) => job.status === "completed").length;
  const processing = state.jobs.filter((job) => ["pending", "processing"].includes(job.status)).length;
  const anomalies = state.jobs.reduce((sum, job) => sum + (job.summary?.anomaly_count || 0), 0);
  const latestAnomalyJob = state.jobs.find((job) => job.status === "completed" && (job.summary?.anomaly_count || 0) > 0);
  const inr = state.jobs.reduce((sum, job) => sum + Number(job.summary?.total_spend_inr || 0), 0);
  app.innerHTML = `
    <div class="workspace">
      <aside class="sidebar">
        <div class="brand"><span class="brand-mark">L</span><span>ledgerly<small>TRANSACTION INTELLIGENCE</small></span></div>
        <div class="nav-label">Workspace</div><button class="nav-item active" data-view="overview"><span class="nav-icon">⌂</span>Overview</button>
        <button class="nav-item" data-view="analyses"><span class="nav-icon">◷</span>Analyses <span class="mono muted">${totalJobs}</span></button>
        <div class="sidebar-spacer"></div>
        <div class="profile"><div class="avatar">${escapeHtml((firstName[0] || "L").toUpperCase())}</div><div class="profile-copy"><div class="profile-name">${escapeHtml(state.user?.name || "Account")}</div><div class="profile-email">${escapeHtml(state.user?.email || "")}</div></div><button id="signout" class="button ghost small" aria-label="Sign out">↗</button></div>
      </aside>
      <main class="main">
        <div class="mobile-top"><div class="brand"><span class="brand-mark">L</span><span>ledgerly</span></div><button id="signout-mobile" class="button secondary small">Sign out</button></div>
        <header class="topbar"><div><span class="eyebrow">Transaction intelligence</span><h1 id="page-title">Overview</h1></div><div class="topbar-right"><span class="date-tag">${new Date().toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}</span><button class="button small" id="new-analysis">＋ New analysis</button></div></header>
        <section class="welcome"><div><span class="eyebrow">Your overview</span><h2>Good ${dayPart()}, ${escapeHtml(firstName)}.</h2><p>A clear view of your transaction activity starts here.</p></div></section>
        <section class="stats">
          <article class="stat-card"><div class="stat-top"><span>Files analyzed</span><span class="stat-icon">↗</span></div><div class="stat-value">${totalJobs}</div><div class="stat-foot">${completed} completed</div></article>
          <article class="stat-card"><div class="stat-top"><span>INR spend reviewed</span><span class="stat-icon">₹</span></div><div class="stat-value">${money(inr, "INR")}</div><div class="stat-foot">Across completed analyses</div></article>
          <article class="stat-card"><div class="stat-top"><span>Anomalies flagged</span><span class="stat-icon">⌁</span></div><div class="stat-value">${anomalies}</div>${latestAnomalyJob ? '<button class="stat-action" id="view-anomalies">View flagged transactions →</button>' : '<div class="stat-foot">No flagged transactions yet</div>'}</article>
          <article class="stat-card"><div class="stat-top"><span>In progress</span><span class="stat-icon">◷</span></div><div class="stat-value">${processing}</div><div class="stat-foot">Jobs being processed</div></article>
        </section>
        <section class="content-grid">
          <article class="panel"><div class="panel-head"><div><h3>Recent analyses</h3><div class="panel-sub">Your latest transaction files</div></div><button class="button ghost small" id="refresh-jobs">↻ Refresh</button></div><div id="jobs-list">${renderJobsTable()}</div></article>
          <article class="panel"><div class="panel-head"><div><h3>Start an analysis</h3><div class="panel-sub">Drop in a CSV to get an instant overview</div></div></div>
            <div class="upload-zone" id="drop-zone"><div class="upload-icon">⇧</div><strong>Bring your transactions into focus</strong><p>CSV files with transaction details · UTF-8</p><div class="upload-actions"><label class="button small" for="csv-file">Choose CSV</label><a class="button secondary small" href="/sample-transactions.csv" download>Sample file</a></div><input id="csv-file" type="file" accept=".csv,text/csv" /><div class="file-name" id="file-name"></div><div class="upload-status" id="upload-status"></div></div>
          </article>
        </section>
        <section class="panel detail-panel" id="job-detail" hidden></section>
      </main>
    </div>`;
  app.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => { app.querySelectorAll("[data-view]").forEach((item) => item.classList.toggle("active", item === button)); document.querySelector("#page-title").textContent = button.dataset.view === "analyses" ? "All analyses" : "Overview"; document.querySelector(".welcome").hidden = button.dataset.view === "analyses"; }));
  ["#signout", "#signout-mobile"].forEach((selector) => app.querySelector(selector)?.addEventListener("click", signout));
  app.querySelector("#new-analysis").addEventListener("click", () => document.querySelector("#csv-file").click());
  app.querySelector("#refresh-jobs").addEventListener("click", refreshJobs);
  app.querySelector("#view-anomalies")?.addEventListener("click", () => showResults(latestAnomalyJob.job_id));
  const fileInput = app.querySelector("#csv-file");
  fileInput.addEventListener("change", () => { const file = fileInput.files[0]; document.querySelector("#file-name").textContent = file ? file.name : ""; if (file) uploadFile(file); });
  const dropZone = app.querySelector("#drop-zone");
  dropZone.addEventListener("dragover", (event) => { event.preventDefault(); dropZone.classList.add("dragging"); });
  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragging"));
  dropZone.addEventListener("drop", (event) => { event.preventDefault(); dropZone.classList.remove("dragging"); const file = event.dataTransfer.files[0]; if (file) { document.querySelector("#file-name").textContent = file.name; uploadFile(file); } });
  app.querySelectorAll("[data-job-id]").forEach((button) => button.addEventListener("click", () => showResults(button.dataset.jobId)));
}
function dayPart() { const hour = new Date().getHours(); return hour < 12 ? "morning" : hour < 17 ? "afternoon" : "evening"; }
function renderJobsTable() {
  if (!state.jobs.length) return '<div class="empty-state"><strong>No analyses yet</strong>Upload a CSV to see your spending patterns here.</div>';
  return `<div class="table-wrap"><table class="jobs-table"><thead><tr><th>File</th><th>Uploaded</th><th>Rows</th><th>Status</th></tr></thead><tbody>${state.jobs.map((job) => `<tr><td><button class="job-open" data-job-id="${escapeHtml(job.job_id)}">${escapeHtml(job.filename)}</button></td><td>${date(job.created_at)}</td><td>${job.row_count_raw ?? "—"}</td><td>${statusPill(job.status)}</td></tr>`).join("")}</tbody></table></div>`;
}
async function loadWorkspace() {
  try { const [user, jobs] = await Promise.all([request("/auth/me"), request("/jobs")]); state.user = user; state.jobs = jobs; renderDashboard(); syncPolling(); }
  catch (error) { if (state.token) { showToast(error.message, true); if (!state.user) { clearSession(); renderAuth(); } } }
}
async function refreshJobs() {
  try { state.jobs = await request("/jobs"); renderDashboard(); syncPolling(); }
  catch (error) { showToast(error.message, true); }
}
function syncPolling() {
  if (state.poller) window.clearInterval(state.poller);
  if (state.jobs.some((job) => ["pending", "processing"].includes(job.status))) state.poller = window.setInterval(refreshJobs, 3500);
}
async function uploadFile(file) {
  const status = document.querySelector("#upload-status");
  if (!file.name.toLowerCase().endsWith(".csv")) { status.textContent = "Choose a .csv file to continue."; return; }
  status.innerHTML = '<span class="spinner"></span> Uploading and starting your analysis…';
  const form = new FormData(); form.append("file", file);
  try { const job = await request("/jobs/upload", { method: "POST", body: form }); status.textContent = `${job.message} We’ll update the status here.`; showToast("Your transaction analysis has started."); await refreshJobs(); }
  catch (error) { status.textContent = error.message; showToast(error.message, true); }
}
async function showResults(jobId) {
  const panel = document.querySelector("#job-detail");
  panel.hidden = false; panel.innerHTML = '<div class="panel-head"><h3>Loading analysis…</h3><span class="spinner"></span></div>'; panel.scrollIntoView({ behavior: "smooth", block: "start" });
  try {
    const data = await request(`/jobs/${encodeURIComponent(jobId)}/results`);
    const summary = data.summary || {};
    const maxCategory = Math.max(1, ...Object.values(data.category_breakdown || {}).map(Number));
    const anomaliesMarkup = data.anomalies.length
      ? '<section class="anomalies-section"><div class="panel-head"><div><h3>Flagged transactions</h3><div class="panel-sub">' + data.anomalies.length + ' transaction(s) matched an anomaly rule. A flag is a prompt to review, not proof of fraud.</div></div></div><div class="anomaly-list">' +
        data.anomalies.map((txn) => '<article class="anomaly-item"><div class="anomaly-item-top"><div><div class="anomaly-date">' + escapeHtml(date(txn.date)) + '</div><h4>' + escapeHtml(txn.merchant || 'Unknown merchant') + '</h4></div><strong class="anomaly-amount">' + money(txn.amount, txn.currency || 'INR') + '</strong></div><p>' + escapeHtml(txn.anomaly_reason || 'Flagged as unusual by the anomaly detector.') + '</p><div class="anomaly-meta">Transaction ' + escapeHtml(txn.txn_id || '—') + ' · ' + escapeHtml(txn.category || 'Uncategorized') + '</div></article>').join('') +
        '</div></section>'
      : '<section class="anomalies-section"><div class="panel-head"><div><h3>Flagged transactions</h3><div class="panel-sub">No transactions triggered the anomaly rules in this file.</div></div></div></section>';
    panel.innerHTML = `<div class="panel-head"><div><span class="eyebrow">Completed analysis</span><h3>${escapeHtml(data.transactions[0]?.merchant ? "Transaction results" : "Analysis results")}</h3><div class="panel-sub">${data.transactions.length} cleaned transactions · ${data.anomalies.length} anomalies</div></div><button class="button ghost small" id="close-detail">Close ×</button></div>
      <div class="summary-grid"><div class="summary-item"><span>INR spend</span><strong>${money(summary.total_spend_inr,"INR")}</strong></div><div class="summary-item"><span>USD spend</span><strong>${money(summary.total_spend_usd,"USD")}</strong></div><div class="summary-item"><span>Anomalies</span><strong>${summary.anomaly_count ?? data.anomalies.length}</strong></div><div class="summary-item"><span>Risk level</span><strong>${escapeHtml(summary.risk_level || "—")}</strong></div></div>
      ${summary.narrative ? `<p class="narrative">${escapeHtml(summary.narrative)}</p>` : ""}
${anomaliesMarkup}
      <div class="content-grid"><div><div class="panel-head"><h3>Transactions</h3><span class="panel-sub">${data.transactions.length} rows</span></div><div class="table-wrap"><table class="jobs-table"><thead><tr><th>Date</th><th>Merchant</th><th>Amount</th><th>Category</th><th>Flag</th></tr></thead><tbody>${data.transactions.map((t) => `<tr><td>${escapeHtml(t.date || "—")}</td><td>${escapeHtml(t.merchant || "—")}</td><td>${money(t.amount,t.currency || "INR")}</td><td>${escapeHtml(t.category || "—")}</td><td>${t.is_anomaly ? `<span class="anomaly-tag" title="${escapeHtml(t.anomaly_reason)}">Flagged</span>` : "—"}</td></tr>`).join("")}</tbody></table></div></div>
      <div><div class="panel-head"><h3>Category mix</h3></div><div class="category-list">${Object.entries(data.category_breakdown || {}).sort((a,b)=>Number(b[1])-Number(a[1])).map(([name,value]) => `<div class="category-row"><span>${escapeHtml(name)}</span><span>${money(value,"INR")}</span><div class="category-bar"><i style="width:${Math.min(100, Number(value)/maxCategory*100)}%"></i></div></div>`).join("") || '<div class="empty-state">No category totals available.</div>'}</div></div></div>`;
    panel.querySelector("#close-detail").addEventListener("click", () => { panel.hidden = true; });
  } catch (error) { panel.innerHTML = `<div class="panel-head"><h3>Analysis is not ready yet</h3><span>${statusPill("processing")}</span></div><p class="panel-sub">${escapeHtml(error.message)} Refresh the job list when processing completes.</p>`; }
}
function signout() { clearSession(); renderAuth(); }
async function boot() {
  renderAuth();
  if (!state.token) return;
  try { state.user = await request("/auth/me"); await loadWorkspace(); }
  catch { clearSession(); renderAuth(); }
}
boot();
