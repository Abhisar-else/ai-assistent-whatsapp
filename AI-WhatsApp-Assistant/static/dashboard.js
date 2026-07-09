const KEY_STORAGE = "pw_admin_key";
const $ = (sel) => document.querySelector(sel);

function getKey() {
  return localStorage.getItem(KEY_STORAGE) || "";
}

function setKey(k) {
  localStorage.setItem(KEY_STORAGE, k);
}

async function apiGet(path) {
  const res = await fetch(path, { headers: { "X-Admin-Key": getKey() } });
  if (res.status === 401) throw new Error("unauthorized");
  if (!res.ok) throw new Error(`request failed: ${res.status}`);
  return res.json();
}

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function timeAgo(ts) {
  if (!ts) return "";
  const then = new Date(ts.replace(" ", "T") + "Z");
  const diffMin = Math.round((Date.now() - then.getTime()) / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  return `${Math.round(diffHr / 24)}d ago`;
}

const PROVIDER_TIERS = [
  { key: "gemini", label: "Gemini" },
  { key: "groq", label: "Groq" },
  { key: "openrouter", label: "OpenRouter" },
  { key: "heuristic", label: "Heuristic" },
];

async function loadStats() {
  const stats = await apiGet("/admin/stats");

  $("#stat-conversations").textContent = stats.total_conversations;
  $("#stat-users").textContent = stats.total_users;
  $("#stat-meetings").textContent = stats.total_meetings;
  const pendingIntents = stats.by_intent?.meeting || 0;
  $("#stat-meeting-msgs").textContent = pendingIntents;

  const byProvider = stats.by_provider || {};
  // 'rule' = meeting-flow responses, not an LLM tier — keep the relay focused on the LLM chain.
  const llmTotal = PROVIDER_TIERS.reduce((sum, t) => sum + (byProvider[t.key] || 0), 0) || 1;
  const maxCount = Math.max(1, ...PROVIDER_TIERS.map((t) => byProvider[t.key] || 0));

  const chain = $("#relay-chain");
  chain.innerHTML = "";
  PROVIDER_TIERS.forEach((tier, i) => {
    const count = byProvider[tier.key] || 0;
    const isActive = count > 0 && count === maxCount;
    const node = document.createElement("div");
    node.className = "relay-node" + (isActive ? " active" : "");
    node.innerHTML = `
      <div class="tier">${tier.label}</div>
      <div class="count">${count}</div>
      <div class="bar"><div class="bar-fill" style="width:${(count / llmTotal) * 100}%"></div></div>
    `;
    chain.appendChild(node);
    if (i < PROVIDER_TIERS.length - 1) {
      const arrow = document.createElement("div");
      arrow.className = "relay-arrow";
      arrow.textContent = "→";
      chain.appendChild(arrow);
    }
  });
}

async function loadConversations() {
  const query = $("#conv-search").value.trim();
  const params = new URLSearchParams({ limit: "50" });
  if (query) params.set("query", query);
  const data = await apiGet(`/admin/conversations?${params}`);
  const tbody = $("#conv-body");
  tbody.innerHTML = "";

  if (!data.results.length) {
    tbody.innerHTML = `<tr><td colspan="4" class="empty">No conversations yet — messages will appear here as they come in.</td></tr>`;
    return;
  }

  for (const row of data.results) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="mono">${escapeHtml(row.user_number)}</td>
      <td class="msg-cell">
        <div class="msg-user">${escapeHtml(row.user_message)}</div>
        <div class="msg-ai">${escapeHtml(row.ai_response)}</div>
      </td>
      <td><span class="badge ${escapeHtml(row.intent || "general")}">${escapeHtml(row.intent || "general")}</span></td>
      <td class="mono">${timeAgo(row.timestamp)}</td>
    `;
    tbody.appendChild(tr);
  }
}

async function loadMeetings() {
  const status = $("#meeting-filter").value;
  const params = status ? `?status=${status}` : "";
  const data = await apiGet(`/admin/meetings${params}`);
  const tbody = $("#meeting-body");
  tbody.innerHTML = "";

  if (!data.results.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty">No meeting requests yet.</td></tr>`;
    return;
  }

  for (const row of data.results) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(row.name || "—")}</td>
      <td class="mono">${escapeHtml(row.user_number)}</td>
      <td>${escapeHtml(row.preferred_date || "—")} · ${escapeHtml(row.preferred_time || "—")}</td>
      <td>${escapeHtml(row.purpose || "—")}</td>
      <td><span class="badge ${escapeHtml(row.status)}">${escapeHtml(row.status)}</span></td>
    `;
    tbody.appendChild(tr);
  }
}

async function refreshAll() {
  try {
    await Promise.all([loadStats(), loadConversations(), loadMeetings()]);
    $("#lock-screen").style.display = "none";
    $("#app-body").style.display = "block";
    $(".status-dot").classList.add("live");
  } catch (err) {
    $(".status-dot").classList.remove("live");
    if (err.message === "unauthorized") {
      $("#lock-screen").style.display = "block";
      $("#app-body").style.display = "none";
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  $("#key-input").value = getKey();

  $("#key-save").addEventListener("click", () => {
    setKey($("#key-input").value.trim());
    refreshAll();
  });
  $("#key-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("#key-save").click();
  });

  $("#conv-search").addEventListener("input", debounce(loadConversations, 300));
  $("#meeting-filter").addEventListener("change", loadMeetings);
  $("#refresh-btn").addEventListener("click", refreshAll);

  $("#kb-reload-btn").addEventListener("click", async () => {
    const btn = $("#kb-reload-btn");
    btn.disabled = true;
    btn.textContent = "Reloading…";
    try {
      const res = await fetch("/admin/knowledge-base/reload", {
        method: "POST",
        headers: { "X-Admin-Key": getKey() },
      });
      const data = await res.json();
      btn.textContent = `Reloaded (${data.entries} entries)`;
    } catch {
      btn.textContent = "Reload failed";
    } finally {
      setTimeout(() => { btn.textContent = "Reload knowledge base"; btn.disabled = false; }, 2000);
    }
  });

  $("#export-btn").addEventListener("click", () => {
    const url = "/admin/export/conversations";
    fetch(url, { headers: { "X-Admin-Key": getKey() } })
      .then((r) => r.blob())
      .then((blob) => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "conversations_export.csv";
        a.click();
      });
  });

  refreshAll();
  setInterval(refreshAll, 15000);
});

function debounce(fn, wait) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), wait);
  };
}
