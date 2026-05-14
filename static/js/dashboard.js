const statusEl = document.getElementById("socket-status");
const socketDot = document.getElementById("socket-dot");
const tableBodyEl = document.getElementById("table-body");
const totalAppsEl = document.getElementById("total-apps");
const macBatchworkerEl = document.getElementById("mac-batchworker");
const winBatchworkerEl = document.getElementById("win-batchworker");
const macStorageEl = document.getElementById("mac-storage");
const winStorageEl = document.getElementById("win-storage");
const macStorageCardEl = document.getElementById("mac-storage-card");
const winStorageCardEl = document.getElementById("win-storage-card");
const macBatchworkerCardEl = document.getElementById("mac-batchworker-card");
const winBatchworkerCardEl = document.getElementById("win-batchworker-card");

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
  const macBatchworkerRunning = payload?.batchworker?.mac_running;
  const winBatchworkerRunning = payload?.batchworker?.win_running;

  totalAppsEl.textContent = String(applications.length);

  if (macBatchworkerRunning === true) {
    macBatchworkerEl.textContent = "ONLINE";
  } else if (macBatchworkerRunning === false) {
    macBatchworkerEl.textContent = "OFFLINE";
  } else {
    macBatchworkerEl.textContent = "UNKNOWN";
  }

  if (winBatchworkerRunning === true) {
    winBatchworkerEl.textContent = "ONLINE";
  } else if (winBatchworkerRunning === false) {
    winBatchworkerEl.textContent = "OFFLINE";
  } else {
    winBatchworkerEl.textContent = "UNKNOWN";
  }

  macStorageEl.textContent = storageText(payload?.storage?.mac);
  winStorageEl.textContent = storageText(payload?.storage?.win);

  const macLowDisk = Boolean(payload?.storage?.mac?.storage?.low_disk);
  const winLowDisk = Boolean(payload?.storage?.win?.storage?.low_disk);

  macStorageCardEl.classList.toggle("storage-alert", macLowDisk);
  winStorageCardEl.classList.toggle("storage-alert", winLowDisk);
  macBatchworkerCardEl.classList.toggle(
    "status-alert",
    macBatchworkerRunning === false,
  );
  winBatchworkerCardEl.classList.toggle(
    "status-alert",
    winBatchworkerRunning === false,
  );
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
