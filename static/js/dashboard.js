const statusEl = document.getElementById("socket-status");
const socketDot = document.getElementById("socket-dot");
const summaryEl = document.getElementById("summary");
const cardsEl = document.getElementById("cards");
const templateEl = document.getElementById("card-template");
const detailsModal = document.getElementById("details-modal");
const detailsClose = document.getElementById("details-close");

const statLiveEl = document.getElementById("stat-live");
const statWarningEl = document.getElementById("stat-warning");
const statOfflineEl = document.getElementById("stat-offline");
const statUpdatedEl = document.getElementById("stat-updated");
const statMarketEl = document.getElementById("stat-market");

const statusClassMap = {
  LIVE: "bg-emerald-100 text-emerald-700",
  WARNING: "bg-amber-100 text-amber-700",
  OFFLINE: "bg-rose-100 text-rose-700",
};

function formatAgo(seconds) {
  if (seconds === null || seconds === undefined) return "No recent activity";
  const safe = Math.max(0, Number(seconds) || 0);
  if (safe < 60) return `${safe}s`;
  const mins = Math.floor(safe / 60);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
}

function formatDateTime(value) {
  if (!value) return "N/A";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString();
}

function formatPriorityAlerts(count) {
  const n = Number(count ?? 0);
  const noun = n === 1 ? "log" : "logs";
  return `${n} priority ${noun} (priority >= 3 in latest 100 logs)`;
}

function yesNo(value) {
  return value ? "YES" : "NO";
}

function setSocketState(text, isConnected) {
  statusEl.textContent = text;
  socketDot.className = `dot ${isConnected ? "bg-emerald-500" : "bg-amber-400"}`;
}

function updateMetrics(applications, updatedAt, marketStatus) {
  let live = 0;
  let warning = 0;
  let offline = 0;

  for (const app of applications) {
    if (app.status === "LIVE") live += 1;
    else if (app.status === "WARNING") warning += 1;
    else offline += 1;
  }

  statLiveEl.textContent = String(live);
  statWarningEl.textContent = String(warning);
  statOfflineEl.textContent = String(offline);
  statUpdatedEl.textContent = formatDateTime(updatedAt);

  const mStatus = marketStatus || "CLOSED";
  statMarketEl.textContent = mStatus;
  if (mStatus === "OPEN") {
    statMarketEl.className = "metric-value mt-1 text-sm text-emerald-600";
  } else {
    statMarketEl.className = "metric-value mt-1 text-sm text-slate-700";
  }
}

function openDetails(app) {
  document.getElementById("details-title").textContent =
    app.app_name || "Unnamed App";
  document.getElementById("details-status").textContent =
    app.status || "OFFLINE";
  document.getElementById("details-login").textContent = yesNo(app.daily_login);
  document.getElementById("details-reset").textContent = yesNo(app.db_reset);
  document.getElementById("details-insert").textContent =
    app.insert_mode || "UNKNOWN";
  document.getElementById("details-low-logs").textContent = app.low_logs
    ? "ON"
    : "OFF";
  document.getElementById("details-warnings").textContent =
    formatPriorityAlerts(app.warnings);
  document.getElementById("details-last-activity").textContent = formatAgo(
    app.last_activity_seconds,
  );
  document.getElementById("details-refreshed").textContent = formatDateTime(
    app.cache_refreshed_at,
  );

  const urlEl = document.getElementById("details-url");
  urlEl.textContent = app.app_url || "N/A";
  urlEl.href = app.app_url || "#";

  const noLogsNote = app.no_recent_logs
    ? "No new logs recently. App may still be running; status is degraded until fresh logs arrive."
    : "";
  document.getElementById("details-error").textContent =
    app.error || noLogsNote;

  const detailsPayload = {
    ...app,
    priority_alerts: formatPriorityAlerts(app.warnings),
    last_refresh: formatDateTime(app.cache_refreshed_at),
    last_activity: formatAgo(app.last_activity_seconds),
  };

  document.getElementById("details-json").textContent = JSON.stringify(
    detailsPayload,
    null,
    2,
  );

  detailsModal.classList.remove("hidden");
  detailsModal.classList.add("flex");
}

function closeDetails() {
  detailsModal.classList.add("hidden");
  detailsModal.classList.remove("flex");
}

function renderCards(applications) {
  cardsEl.innerHTML = "";
  const frag = document.createDocumentFragment();

  applications.forEach((app, index) => {
    const node = templateEl.content.firstElementChild.cloneNode(true);
    node.style.setProperty("--delay", `${index * 35}ms`);
    node.classList.add(
      "cursor-pointer",
      "hover:-translate-y-0.5",
      "transition",
    );

    const status = app.status || "OFFLINE";
    const statusClasses = statusClassMap[status] || statusClassMap.OFFLINE;

    node.querySelector(".card-app-name").textContent =
      app.app_name || "Unnamed App";
    node.querySelector(".card-last-activity").textContent =
      `Last activity: ${formatAgo(app.last_activity_seconds)}`;

    const cardStatus = node.querySelector(".card-status");
    cardStatus.textContent = status;
    cardStatus.className = `card-status rounded-full px-2.5 py-1 text-xs font-semibold ${statusClasses}`;

    node.querySelector(".card-login").textContent = yesNo(app.daily_login);
    node.querySelector(".card-reset").textContent = yesNo(app.db_reset);
    node.querySelector(".card-insert").textContent =
      app.insert_mode || "UNKNOWN";
    node.querySelector(".card-low-logs").textContent = app.low_logs
      ? "ON"
      : "OFF";

    const errorEl = node.querySelector(".card-error");
    errorEl.textContent = app.error ? "Partial data: source unavailable" : "";

    const openLink = node.querySelector(".card-open");
    openLink.href = app.app_url || "#";
    if (!app.app_url) {
      openLink.classList.add("pointer-events-none", "opacity-50");
    }

    openLink.addEventListener("click", (e) => e.stopPropagation());
    node.addEventListener("click", () => openDetails(app));

    frag.appendChild(node);
  });

  cardsEl.appendChild(frag);
}

detailsClose.addEventListener("click", closeDetails);
detailsModal.addEventListener("click", (e) => {
  if (e.target === detailsModal) closeDetails();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeDetails();
});

const socket = io({
  reconnection: true,
  reconnectionAttempts: Infinity,
  reconnectionDelay: 1000,
  reconnectionDelayMax: 5000,
});

socket.on("connect", () => {
  setSocketState("Connected", true);
  socket.emit("dashboard:subscribe");
});

socket.on("disconnect", () => {
  setSocketState("Disconnected, reconnecting...", false);
});

socket.on("reconnect", () => {
  setSocketState("Reconnected", true);
  socket.emit("dashboard:subscribe");
});

socket.on("dashboard:update", (payload) => {
  const total = payload?.meta?.total ?? 0;
  const failed = payload?.meta?.partial_failure_count ?? 0;
  const refreshed = payload?.meta?.generated_at ?? "-";
  const marketStatus = payload?.meta?.market_status ?? "CLOSED";
  const applications = payload?.applications || [];

  summaryEl.textContent = `Apps ${total} | Partial failures ${failed}`;
  updateMetrics(applications, refreshed, marketStatus);

  requestAnimationFrame(() => {
    renderCards(applications);
  });
});

setSocketState("Connecting...", false);
