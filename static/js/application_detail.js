const summaryGridEl = document.getElementById("summary-grid");
const logsBodyEl = document.getElementById("logs-body");
const pageTitleEl = document.getElementById("page-title");
const refreshBtnEl = document.getElementById("refresh-btn");

function toPill(text, kind) {
  const span = document.createElement("span");
  span.className = `badge ${kind}`;
  span.textContent = text;
  return span;
}

function formatDateTime(value) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString();
}

function addSummaryCard(label, valueNode) {
  const card = document.createElement("article");
  card.className = "panel summary-card";

  const labelEl = document.createElement("p");
  labelEl.className = "label";
  labelEl.textContent = label;

  const valueEl = document.createElement("div");
  valueEl.className = "value";

  if (typeof valueNode === "string") {
    valueEl.textContent = valueNode;
  } else {
    valueEl.appendChild(valueNode);
  }

  card.appendChild(labelEl);
  card.appendChild(valueEl);
  summaryGridEl.appendChild(card);
}

function renderSummary(application) {
  summaryGridEl.innerHTML = "";

  const status = application?.status || {};

  addSummaryCard(
    "Online",
    status.online
      ? toPill("ONLINE", "badge-online")
      : toPill("OFFLINE", "badge-offline"),
  );
  addSummaryCard(
    "Daily Login",
    status.daily_login ? toPill("YES", "badge-yes") : toPill("NO", "badge-no"),
  );
  addSummaryCard(
    "DB Reset",
    status.db_reset ? toPill("YES", "badge-yes") : toPill("NO", "badge-no"),
  );

  let insertMode = "UNKNOWN";
  if (status.insert_mode) {
    insertMode = String(status.insert_mode).toUpperCase();
  }
  addSummaryCard("Insert Mode", insertMode);

  let lowPriorityLogs = "UNKNOWN";
  if (status.low_priority_logs) {
    lowPriorityLogs = String(status.low_priority_logs).toUpperCase();
  }
  addSummaryCard("Low Priority Logs", lowPriorityLogs);

  if (application.redirect_link) {
    const link = document.createElement("a");
    link.href = application.redirect_link;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.className = "link-btn";
    link.textContent = "Open Application";
    addSummaryCard("Dashboard", link);
  } else {
    addSummaryCard("Dashboard", "N/A");
  }
}

function renderLogs(application) {
  logsBodyEl.innerHTML = "";

  const logs = application?.logs || [];

  if (!logs.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 4;
    td.className = "px-4 py-6 text-center text-sm text-slate-500";
    td.textContent = "No logs found.";
    tr.appendChild(td);
    logsBodyEl.appendChild(tr);
    return;
  }

  logs.forEach((log) => {
    const tr = document.createElement("tr");

    const moduleTd = document.createElement("td");
    moduleTd.className = "px-4 py-3 text-sm font-semibold text-slate-700";
    moduleTd.textContent = log.module || "-";

    const activityTd = document.createElement("td");
    activityTd.className = "px-4 py-3 text-sm text-slate-700";
    activityTd.textContent = log.activity || "-";

    const priorityTd = document.createElement("td");
    priorityTd.className = "px-4 py-3 text-sm text-slate-700";
    priorityTd.textContent = log.priority == null ? "-" : String(log.priority);

    const timestampTd = document.createElement("td");
    timestampTd.className = "px-4 py-3 text-sm text-slate-700";
    timestampTd.textContent = formatDateTime(log.timestamp);

    tr.appendChild(moduleTd);
    tr.appendChild(activityTd);
    tr.appendChild(priorityTd);
    tr.appendChild(timestampTd);
    logsBodyEl.appendChild(tr);
  });
}

function applyDetailPayload(payload) {
  const application = payload?.application;

  if (!application) {
    pageTitleEl.textContent = "Application detail unavailable";
    summaryGridEl.innerHTML = "";
    renderLogs({ logs: [] });
    return;
  }

  pageTitleEl.textContent = application.app_name || "Application";
  renderSummary(application);
  renderLogs(application);
}

async function loadDetail() {
  const appId = window.__APP_ID__;
  try {
    const response = await fetch(`/api/applications/${appId}`, {
      method: "GET",
      cache: "no-store",
      headers: {
        "Cache-Control": "no-cache",
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const payload = await response.json();
    applyDetailPayload(payload);
  } catch (_err) {
    applyDetailPayload(null);
  }
}

refreshBtnEl.addEventListener("click", () => {
  loadDetail();
});

loadDetail();
