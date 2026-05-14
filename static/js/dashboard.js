const statusEl = document.getElementById("socket-status");
const socketDot = document.getElementById("socket-dot");
const tableBodyEl = document.getElementById("table-body");
const totalAppsEl = document.getElementById("total-apps");
const macOnlineEl = document.getElementById("mac-online");
const winOnlineEl = document.getElementById("win-online");
const macStorageEl = document.getElementById("mac-storage");
const winStorageEl = document.getElementById("win-storage");
const macStorageCardEl = document.getElementById("mac-storage-card");
const winStorageCardEl = document.getElementById("win-storage-card");

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

function formatDateTime(value) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString();
}

function storageText(storagePayload) {
  if (!storagePayload || storagePayload.success === false) {
    return "Unavailable";
  }

  const freeGb = storagePayload?.storage?.free_gb;
  const usedPercent = storagePayload?.storage?.used_percent;

  if (freeGb == null || usedPercent == null) {
    return "Unavailable";
  }

  return `${freeGb} GB free (${usedPercent}%)`;
}

function renderOverview(payload) {
  const applications = payload?.applications || [];
  const macApps = applications.filter(
    (app) => String(app?.source || "MAC").toUpperCase() === "MAC",
  );
  const winApps = applications.filter(
    (app) => String(app?.source || "MAC").toUpperCase() === "WIN",
  );

  const macOnline = macApps.filter((app) => Boolean(app.online)).length;
  const winOnline = winApps.filter((app) => Boolean(app.online)).length;

  totalAppsEl.textContent = String(applications.length);
  macOnlineEl.textContent = `${macOnline}/${macApps.length}`;
  winOnlineEl.textContent = `${winOnline}/${winApps.length}`;

  macStorageEl.textContent = storageText(payload?.storage?.mac);
  winStorageEl.textContent = storageText(payload?.storage?.win);

  const macLowDisk = Boolean(payload?.storage?.mac?.storage?.low_disk);
  const winLowDisk = Boolean(payload?.storage?.win?.storage?.low_disk);

  macStorageCardEl.classList.toggle("storage-alert", macLowDisk);
  winStorageCardEl.classList.toggle("storage-alert", winLowDisk);
}

function renderTable(applications) {
  tableBodyEl.innerHTML = "";

  if (!applications.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 5;
    td.className = "px-4 py-6 text-center text-sm text-slate-500";
    td.textContent = "No applications found.";
    tr.appendChild(td);
    tableBodyEl.appendChild(tr);
    return;
  }

  const fragment = document.createDocumentFragment();

  applications.forEach((app) => {
    const tr = document.createElement("tr");
    tr.className = "hover:bg-slate-50/90 clickable-row";

    const source = String(app.source || "MAC").toUpperCase();
    const detailPath =
      source === "WIN"
        ? `/applications/win/${app.app_id}`
        : `/applications/${app.app_id}`;
    tr.addEventListener("click", () => {
      window.location.href = detailPath;
    });

    const sourceTd = document.createElement("td");
    sourceTd.className = "px-4 py-3 text-sm font-semibold text-slate-700";
    sourceTd.textContent = source;
    tr.appendChild(sourceTd);

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
  renderOverview(payload);
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
    // Silent fail - will rely on live socket updates
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
