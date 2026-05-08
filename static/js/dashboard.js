const statusEl = document.getElementById("socket-status");
const socketDot = document.getElementById("socket-dot");
const tableBodyEl = document.getElementById("table-body");

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

function renderTable(applications) {
  tableBodyEl.innerHTML = "";

  if (!applications.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 4;
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

    const detailPath = `/applications/${app.app_id}`;
    tr.addEventListener("click", () => {
      window.location.href = detailPath;
    });

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
