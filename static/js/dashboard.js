const statusEl = document.getElementById("socket-status");
const socketDot = document.getElementById("socket-dot");
const tableBodyEl = document.getElementById("table-body");

const statTotalEl = document.getElementById("stat-total");
const statOnlineEl = document.getElementById("stat-online");
const statOfflineEl = document.getElementById("stat-offline");
const statUpdatedEl = document.getElementById("stat-updated");

function setSocketState(text, connected) {
  statusEl.textContent = text;
  socketDot.className = connected
    ? "h-2.5 w-2.5 rounded-full bg-emerald-500"
    : "h-2.5 w-2.5 rounded-full bg-amber-400";
}

function toYesNoPill(value) {
  const span = document.createElement("span");
  span.className = `badge ${value ? "badge-yes" : "badge-no"}`;
  span.textContent = value ? "YES" : "NO";
  return span;
}

function toOnlinePill(value) {
  const span = document.createElement("span");
  span.className = `badge ${value ? "badge-online" : "badge-offline"}`;
  span.textContent = value ? "ONLINE" : "OFFLINE";
  return span;
}

function toLowPriorityPill(value) {
  const normalized = String(value || "UNKNOWN").toUpperCase();
  const span = document.createElement("span");

  if (normalized === "ENABLED") {
    span.className = "badge badge-yes";
    span.textContent = "ENABLED";
    return span;
  }

  if (normalized === "DISABLED") {
    span.className = "badge badge-no";
    span.textContent = "DISABLED";
    return span;
  }

  span.className = "badge bg-slate-200 text-slate-700";
  span.textContent = "UNKNOWN";
  return span;
}

function formatDateTime(value) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString();
}

function updateStats(applications, generatedAt) {
  let online = 0;
  for (const app of applications) {
    if (app.online) online += 1;
  }

  const total = applications.length;
  const offline = total - online;

  statTotalEl.textContent = String(total);
  statOnlineEl.textContent = String(online);
  statOfflineEl.textContent = String(offline);
  statUpdatedEl.textContent = formatDateTime(generatedAt);
}

function renderTable(applications) {
  tableBodyEl.innerHTML = "";

  if (!applications.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 7;
    td.className = "px-4 py-6 text-center text-sm text-slate-500";
    td.textContent = "No applications found.";
    tr.appendChild(td);
    tableBodyEl.appendChild(tr);
    return;
  }

  const fragment = document.createDocumentFragment();

  applications.forEach((app) => {
    const tr = document.createElement("tr");
    tr.className = "hover:bg-slate-50/90";

    const appNameTd = document.createElement("td");
    appNameTd.className = "px-4 py-3 text-sm font-semibold text-slate-800";
    appNameTd.textContent = app.app_name || "Unnamed App";
    tr.appendChild(appNameTd);

    const dailyTd = document.createElement("td");
    dailyTd.className = "px-4 py-3 text-sm";
    dailyTd.appendChild(toYesNoPill(Boolean(app.daily_login)));
    tr.appendChild(dailyTd);

    const resetTd = document.createElement("td");
    resetTd.className = "px-4 py-3 text-sm";
    resetTd.appendChild(toYesNoPill(Boolean(app.db_reset)));
    tr.appendChild(resetTd);

    const linkTd = document.createElement("td");
    linkTd.className = "px-4 py-3 text-sm";
    if (app.redirect_link) {
      const link = document.createElement("a");
      link.className = "link-btn";
      link.href = app.redirect_link;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "Open";
      linkTd.appendChild(link);
    } else {
      linkTd.textContent = "N/A";
      linkTd.classList.add("text-slate-500");
    }
    tr.appendChild(linkTd);

    const modeTd = document.createElement("td");
    modeTd.className = "px-4 py-3 text-sm font-semibold text-slate-700";
    modeTd.textContent = app.insert_mode || "UNKNOWN";
    tr.appendChild(modeTd);

    const lowLogsTd = document.createElement("td");
    lowLogsTd.className = "px-4 py-3 text-sm";
    lowLogsTd.appendChild(toLowPriorityPill(app.low_priority_logs));
    tr.appendChild(lowLogsTd);

    const onlineTd = document.createElement("td");
    onlineTd.className = "px-4 py-3 text-sm";
    onlineTd.appendChild(toOnlinePill(Boolean(app.online)));
    tr.appendChild(onlineTd);

    fragment.appendChild(tr);
  });

  tableBodyEl.appendChild(fragment);
}

function applyPayload(payload) {
  const applications = payload?.applications || [];
  const generatedAt = payload?.meta?.generated_at || null;

  updateStats(applications, generatedAt);
  renderTable(applications);
}

async function initialLoad() {
  try {
    const res = await fetch("/api/dashboard", {
      method: "GET",
      cache: "no-store",
      headers: {
        "Cache-Control": "no-cache",
      },
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const payload = await res.json();
    applyPayload(payload);
  } catch (_err) {
    console.log("Initial load failed, will rely on live updates. Error:", _err);
  }
}

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
  window.requestAnimationFrame(() => {
    applyPayload(payload);
  });
});

setSocketState("Connecting...", false);
initialLoad();
