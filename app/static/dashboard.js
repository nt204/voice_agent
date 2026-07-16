const state = {
  direction: "",
  interest: "",
  query: "",
  selectedId: null,
  selectedDetailStatus: "",
  calls: [],
  orders: [],
  callPage: 1,
  callPageSize: 10,
  orderPage: 1,
  orderPageSize: 8,
  refreshing: false,
};

const callList = document.querySelector("#callList");
const detailPanel = document.querySelector("#detailPanel");
const syncStatus = document.querySelector("#syncStatus");
const orderList = document.querySelector("#orderList");
const outboundCallForm = document.querySelector("#outboundCallForm");
const outboundCallStatus = document.querySelector("#outboundCallStatus");
const startCallButton = document.querySelector("#startCallButton");
const visibleRange = document.querySelector("#visibleRange");
const callPager = document.querySelector("#callPager");
const orderPager = document.querySelector("#orderPager");
const orderRange = document.querySelector("#orderRange");

const escapeHtml = (value = "") => String(value).replace(
  /[&<>"']/g,
  char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[char]
);

const LOCALE = "my-MM";

const formatDate = value => value
  ? new Intl.DateTimeFormat(LOCALE, { dateStyle: "short", timeStyle: "short" }).format(new Date(value))
  : "Not available";

const formatTime = value => value
  ? new Intl.DateTimeFormat(LOCALE, { timeStyle: "short" }).format(new Date(value))
  : "";

const formatDay = value => value
  ? new Intl.DateTimeFormat(LOCALE, { day: "2-digit", month: "2-digit", year: "2-digit" }).format(new Date(value))
  : "";

const formatMoney = value => value
  ? `${Number(value).toLocaleString(LOCALE)} MMK`
  : "Not available";

const formatBytes = value => {
  const bytes = Number(value || 0);
  if (!bytes) return "";
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
};

function interestLabel(status) {
  return {
    needs_consultation: "Needs consultation",
    no_need: "No need",
    unknown: "Unknown",
  }[status] || "Unknown";
}

function intentLabel(status) {
  return {
    ready_to_order: "Ready to order",
    needs_consultation: "Needs consultation",
    considering: "Considering",
    price_checking: "Price checking",
    no_need: "No need",
    unknown: "Unknown",
  }[status] || "Unknown";
}

function orderStatusLabel(status) {
  return {
    ready_to_confirm: "Ready to confirm",
    missing_info: "Missing info",
    draft: "Draft",
    confirmed: "Confirmed",
    cancelled: "Cancelled",
  }[status] || "Draft";
}

function recordingStatusLabel(status) {
  return {
    active: "Recording",
    completed: "Saved",
    failed: "Failed",
  }[status] || "Not available";
}

function directionLabel(direction) {
  return direction === "outbound" ? "Outbound" : "Inbound";
}

function directionIcon(direction) {
  return direction === "outbound" ? "↗" : "↙";
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error("Unable to load data");
  }
  return response.json();
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "Unable to send request");
  }
  return data;
}

async function loadDashboard({ silent = false } = {}) {
  if (state.refreshing) return;
  state.refreshing = true;
  if (!silent) {
    if (syncStatus) syncStatus.textContent = "Loading data";
    callList.innerHTML = document.querySelector("#loadingTemplate").innerHTML;
    if (orderList) {
      orderList.innerHTML = '<div class="request-state">Loading...</div>';
    }
    if (orderRange) orderRange.textContent = "Loading";
    if (orderPager) orderPager.innerHTML = "";
  }

  const params = new URLSearchParams();
  if (state.direction) params.set("direction", state.direction);
  if (state.interest) params.set("interest_status", state.interest);
  if (state.query) params.set("q", state.query);

  try {
    const [summary, listing] = await Promise.all([
      fetchJson("/api/admin/summary"),
      fetchJson(`/api/calls?${params}`),
    ]);
    renderSummary(summary.stats);
    state.calls = listing.calls;
    renderCalls(listing.calls);
    if (shouldRefreshSelectedDetail(listing.calls, { silent })) {
      await loadDetail(state.selectedId, { silent: true });
    }

    fetchJson("/api/orders?limit=100")
      .then(orders => {
        state.orders = recordedOrders(orders.orders || []);
        renderOrders(state.orders);
      })
      .catch(error => {
        state.orders = [];
        if (orderList) {
          orderList.innerHTML = `<div class="request-state error">${escapeHtml(error.message)}</div>`;
        }
        if (orderRange) orderRange.textContent = "0 orders";
        if (orderPager) orderPager.innerHTML = "";
      });

    if (syncStatus) {
      syncStatus.textContent = `Updated ${new Intl.DateTimeFormat(LOCALE, { timeStyle: "short" }).format(new Date())}`;
    }
  } catch (error) {
    if (!silent) {
      if (syncStatus) syncStatus.textContent = "Load error";
      callList.innerHTML = `<div class="error-state">${escapeHtml(error.message)}</div>`;
      if (orderList) {
        orderList.innerHTML = `<div class="request-state error">${escapeHtml(error.message)}</div>`;
      }
      if (orderRange) orderRange.textContent = "0 orders";
      if (orderPager) orderPager.innerHTML = "";
    }
  } finally {
    state.refreshing = false;
  }
}

function selectedCallFrom(calls) {
  return calls.find(call => call.id === state.selectedId) || null;
}

function isActiveCall(call) {
  return call?.status === "active";
}

function isDetailAudioPlaying() {
  return Array.from(detailPanel.querySelectorAll("audio"))
    .some(audio => !audio.paused && !audio.ended);
}

function isTranscriptScrolledAwayFromBottom() {
  const transcript = detailPanel.querySelector(".transcript");
  if (!transcript) return false;
  return transcript.scrollHeight - transcript.clientHeight - transcript.scrollTop > 24;
}

function shouldRefreshSelectedDetail(calls, { silent } = {}) {
  if (!state.selectedId) return false;
  if (!silent) return true;
  if (isDetailAudioPlaying() || isTranscriptScrolledAwayFromBottom()) return false;

  const selectedCall = selectedCallFrom(calls);
  if (!selectedCall) return false;
  if (isActiveCall(selectedCall)) return true;

  // Refresh once when the active call has just finished, then keep completed
  // details stable so playback and transcript reading are not interrupted.
  return state.selectedDetailStatus === "active";
}

function recordedOrders(orders) {
  return orders.filter(order =>
    String(order.customer_phone || "").trim() &&
    String(order.shipping_address || "").trim() &&
    String(order.product_name || "").trim()
  );
}

function renderSummary(stats) {
  const interest = stats.interest_counts || {};
  document.querySelector("#funnelAll").textContent = stats.total_calls || 0;
  document.querySelector("#funnelHot").textContent = interest.needs_consultation || 0;
  document.querySelector("#funnelCold").textContent = interest.no_need || 0;
  document.querySelector("#funnelUnknown").textContent = interest.unknown || 0;
}

function pageSlice(items, page, pageSize) {
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize));
  const currentPage = Math.min(Math.max(page, 1), totalPages);
  const start = (currentPage - 1) * pageSize;
  const end = Math.min(start + pageSize, items.length);
  return {
    items: items.slice(start, end),
    start,
    end,
    page: currentPage,
    totalPages,
  };
}

function renderPager(container, page, totalPages, onPageChange) {
  if (!container) return;
  if (totalPages <= 1) {
    container.innerHTML = "";
    return;
  }
  container.innerHTML = `
    <button type="button" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""} aria-label="Previous page">&lt;</button>
    <span>Page ${page}/${totalPages}</span>
    <button type="button" data-page="${page + 1}" ${page >= totalPages ? "disabled" : ""} aria-label="Next page">&gt;</button>
  `;
  container.querySelectorAll("button").forEach(button => {
    button.addEventListener("click", () => {
      const nextPage = Number(button.dataset.page);
      if (Number.isFinite(nextPage)) onPageChange(nextPage);
    });
  });
}

function renderCalls(calls) {
  document.querySelector("#resultCount").textContent = `${calls.length} results`;
  if (!calls.length) {
    callList.innerHTML = document.querySelector("#emptyTemplate").innerHTML;
    if (visibleRange) visibleRange.textContent = "Showing 0 results";
    renderPager(callPager, 1, 1, () => {});
    return;
  }

  const page = pageSlice(calls, state.callPage, state.callPageSize);
  state.callPage = page.page;
  if (visibleRange) {
    visibleRange.textContent = `Showing ${page.start + 1}-${page.end} of ${calls.length} results`;
  }

  callList.innerHTML = page.items.map(call => {
    const customer = call.customer || {};
    const title = customer.name || customer.phone || "Unknown customer";
    const need = customer.need || "No need recorded";
    const isSelected = state.selectedId === call.id;
    return `
      <button class="lead-row ${isSelected ? "selected" : ""}" data-id="${escapeHtml(call.id)}" type="button">
        <span class="lead-person">
          <strong><i class="lead-phone-icon" aria-hidden="true">&#9742;</i>${escapeHtml(title)}</strong>
          <small>${escapeHtml(customer.phone || call.id)}</small>
        </span>
        <span class="lead-need" title="${escapeHtml(need)}">${escapeHtml(need)}</span>
        <span class="status-pill ${escapeHtml(call.interest_status)}">${interestLabel(call.interest_status)}</span>
        <span class="lead-time">
          <b>${formatTime(call.started_at)}</b>
          <small>${formatDay(call.started_at)}</small>
        </span>
        <span class="direction-chip ${escapeHtml(call.direction)}">
          <i aria-hidden="true">${directionIcon(call.direction)}</i>
          ${directionLabel(call.direction)}
        </span>
      </button>`;
  }).join("");

  document.querySelectorAll(".lead-row").forEach(button => {
    button.addEventListener("click", () => loadDetail(button.dataset.id));
  });
  renderPager(callPager, page.page, page.totalPages, nextPage => {
    state.callPage = nextPage;
    renderCalls(state.calls);
  });
}

function renderOrders(orders) {
  if (!orderList) return;
  if (!orders.length) {
    orderList.innerHTML = '<div class="request-state">No complete orders yet</div>';
    if (orderRange) orderRange.textContent = "0 orders";
    renderPager(orderPager, 1, 1, () => {});
    return;
  }

  const page = pageSlice(orders, state.orderPage, state.orderPageSize);
  state.orderPage = page.page;
  if (orderRange) {
    orderRange.textContent = `${page.start + 1}-${page.end}/${orders.length} orders`;
  }

  orderList.innerHTML = page.items.map(order => `
    <button class="order-item ${state.selectedId === order.call_id ? "selected" : ""}" data-call-id="${escapeHtml(order.call_id)}" type="button">
      <span>
        <strong>${escapeHtml(order.customer_phone || order.call_id)}</strong>
        <small>${escapeHtml(order.product_name)} · ${order.quantity || 0} boxes</small>
        <small>Created ${formatDate(order.created_at)}</small>
        <small>${escapeHtml(order.shipping_address)}</small>
      </span>
      <span class="order-meta">
        <b>${formatMoney(order.total_price)}</b>
        <em class="order-status ${escapeHtml(order.status)}">${orderStatusLabel(order.status)}</em>
      </span>
    </button>
  `).join("");

  document.querySelectorAll(".order-item").forEach(button => {
    button.addEventListener("click", () => loadDetail(button.dataset.callId));
  });
  renderPager(orderPager, page.page, page.totalPages, nextPage => {
    state.orderPage = nextPage;
    renderOrders(state.orders);
  });
}

function renderComboCard(call) {
  const order = call.order;
  const status = order ? order.status : "missing_info";
  const missing = order?.missing_fields?.length ? order.missing_fields.join(", ") : "None";
  return `
    <div class="combo-card">
      <div class="combo-head">
        <h3>Combo AI</h3>
        <span class="order-status ${escapeHtml(status)}">${order ? orderStatusLabel(status) : "Not created"}</span>
      </div>
      <div class="combo-list">
        <div><span>Product</span><strong>${escapeHtml(order?.product_name || "Not available")}</strong></div>
        <div><span>Quantity</span><strong>${order?.quantity || "Not available"}</strong></div>
        <div><span>Total</span><strong>${formatMoney(order?.total_price)}</strong></div>
        <div><span>Missing</span><strong>${escapeHtml(missing)}</strong></div>
      </div>
    </div>`;
}

function renderRecordingCard(call) {
  const recording = call.recording || null;
  if (call.status !== "completed") {
    return `
      <div class="recording-card empty-recording">
        <div class="recording-head">
          <h3>Call recording</h3>
          <span>${escapeHtml(recordingStatusLabel("active"))}</span>
        </div>
        <p>The recording will appear after the call ends.</p>
      </div>`;
  }

  const files = recording?.files || {};
  const tracks = [
    { key: "mixed", label: "Full call", file: files.mixed },
    { key: "inbound", label: "Customer", file: files.inbound },
    { key: "outbound", label: "AI consultant", file: files.outbound },
  ].filter(track => track.file && track.file.url);
  const status = recording?.status || "completed";

  if (!tracks.length) {
    return `
      <div class="recording-card empty-recording">
        <div class="recording-head">
          <h3>Call recording</h3>
          <span>${escapeHtml(recordingStatusLabel(status))}</span>
        </div>
        <p>No recording file is available for this call.</p>
      </div>`;
  }

  const primary = tracks.find(track => track.key === "mixed") || tracks[0];
  const secondary = tracks.filter(track => track !== primary);
  return `
    <div class="recording-card">
      <div class="recording-head">
        <h3>Call recording</h3>
        <span>${escapeHtml(recordingStatusLabel(status))}</span>
      </div>
      <div class="recording-player">
        <div>
          <strong>${escapeHtml(primary.label)}</strong>
          ${primary.file.bytes ? `<small>${escapeHtml(formatBytes(primary.file.bytes))}</small>` : ""}
        </div>
        <audio controls preload="metadata" src="${escapeHtml(primary.file.url)}"></audio>
      </div>
      ${secondary.length ? `
        <div class="recording-tracks">
          ${secondary.map(track => `
            <div class="recording-track">
              <span>${escapeHtml(track.label)}</span>
              <audio controls preload="metadata" src="${escapeHtml(track.file.url)}"></audio>
            </div>
          `).join("")}
        </div>
      ` : ""}
    </div>`;
}

async function loadDetail(callId, { silent = false } = {}) {
  const previousTranscript = detailPanel.querySelector(".transcript");
  const previousScrollTop = previousTranscript?.scrollTop || 0;
  const wasNearBottom = previousTranscript
    ? previousTranscript.scrollHeight - previousTranscript.clientHeight - previousScrollTop < 24
    : true;
  state.selectedId = callId;
  document.querySelectorAll(".lead-row").forEach(row => {
    row.classList.toggle("selected", row.dataset.id === callId);
  });
  document.querySelectorAll(".order-item").forEach(row => {
    row.classList.toggle("selected", row.dataset.callId === callId);
  });
  if (!silent) {
    detailPanel.innerHTML = '<div class="empty-state"><p>Loading details...</p></div>';
  }
  try {
    renderDetail(await fetchJson(`/api/calls/${encodeURIComponent(callId)}`), {
      scrollTop: previousScrollTop,
      wasNearBottom,
    });
  } catch (error) {
    if (!silent) {
      detailPanel.innerHTML = `<div class="error-state">${escapeHtml(error.message)}</div>`;
    }
  }
}

function renderDetail(call, { scrollTop = 0, wasNearBottom = true } = {}) {
  const customer = call.customer || {};
  state.selectedDetailStatus = call.status || "";
  const field = value => escapeHtml(value || "Not provided");
  const transcript = call.transcript && call.transcript.length
    ? call.transcript.map(item => {
        const isCustomer = item.speaker === "customer";
        const timestamp = item.created_at || item.timestamp || item.time || "";
        return `
        <div class="message ${isCustomer ? "customer" : "agent"}">
          <div class="message-head"><i aria-hidden="true">${isCustomer ? "&#128100;" : "&#10022;"}</i><span>${isCustomer ? "Customer" : "AI consultant"}</span></div>
          <p dir="auto">${escapeHtml(item.text)}</p>
          ${timestamp ? `<time>${escapeHtml(formatTime(timestamp))}</time>` : ""}
        </div>`;
      }).join("")
    : '<div class="list-state">No transcript yet.</div>';

  detailPanel.innerHTML = `
    <div class="detail-top">
      <div class="detail-identity">
        <i class="detail-call-icon" aria-hidden="true">&#9742;</i>
        <div>
          <span class="status-pill ${escapeHtml(call.interest_status)}">${interestLabel(call.interest_status)}</span>
          <h2>${field(customer.name || customer.phone || "Customer")}</h2>
          <p>${directionLabel(call.direction)} | ${escapeHtml(call.provider)} | ${formatTime(call.started_at)} | ${formatDay(call.started_at)}</p>
        </div>
      </div>
      <div class="detail-actions">
        <button class="detail-action redial-button" data-phone="${escapeHtml(customer.phone)}" type="button">&#9742; Redial</button>
        <button class="detail-action icon-only" type="button" aria-label="More actions">&#8942;</button>
      </div>
    </div>

    <div class="info-grid detail-stats">
      <div><span>Phone</span><strong>${field(customer.phone)}</strong></div>
      <div><span>Time</span><strong>${formatTime(call.started_at)}<small>${formatDay(call.started_at)}</small></strong></div>
      <div><span>Call type</span><strong>${directionLabel(call.direction)}</strong></div>
      <div><span>Status</span><strong><em class="status-pill ${escapeHtml(call.interest_status)}">${interestLabel(call.interest_status)}</em></strong></div>
    </div>

    <div class="detail-tabs" role="tablist" aria-label="Lead details">
      <button class="detail-tab active" data-detail-tab="info" type="button" role="tab">Info</button>
      <button class="detail-tab" data-detail-tab="transcript" type="button" role="tab">Transcript</button>
    </div>

    <div class="detail-content">
      <div class="detail-summary">
        <div class="detail-note"><span>Need</span><strong>${field(customer.need)}</strong></div>
        <div class="detail-note"><span>Address</span><strong>${field(customer.address)}</strong></div>
        ${renderRecordingCard(call)}
        ${renderComboCard(call)}
      </div>

      <section class="transcript-panel">
        <h3 class="section-title">Transcript</h3>
        <div class="transcript">${transcript}</div>
      </section>
    </div>`;
  requestAnimationFrame(() => {
    const transcriptEl = detailPanel.querySelector(".transcript");
    if (transcriptEl) {
      transcriptEl.scrollTop = wasNearBottom ? transcriptEl.scrollHeight : scrollTop;
    }
    detailPanel.querySelectorAll(".detail-tab").forEach(button => {
      button.addEventListener("click", () => {
        detailPanel.querySelectorAll(".detail-tab").forEach(tab => tab.classList.toggle("active", tab === button));
        detailPanel.classList.toggle("show-transcript", button.dataset.detailTab === "transcript");
      });
    });
    detailPanel.querySelector(".redial-button")?.addEventListener("click", event => {
      const phone = event.currentTarget.dataset.phone;
      const input = document.querySelector("#toNumberInput");
      if (phone && input) {
        input.value = phone;
        outboundCallForm?.requestSubmit();
      }
    });
  });
}

document.querySelectorAll(".funnel-item").forEach(button => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".funnel-item").forEach(item => item.classList.remove("active"));
    button.classList.add("active");
    state.interest = button.dataset.interest;
    state.callPage = 1;
    loadDashboard();
  });
});

document.querySelectorAll(".segment").forEach(button => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".segment").forEach(item => item.classList.remove("active"));
    button.classList.add("active");
    state.direction = button.dataset.direction;
    state.callPage = 1;
    loadDashboard();
  });
});

let searchTimer;
document.querySelector("#searchInput").addEventListener("input", event => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.query = event.target.value.trim();
    state.callPage = 1;
    loadDashboard();
  }, 250);
});

outboundCallForm?.addEventListener("submit", async event => {
  event.preventDefault();
  const formData = new FormData(outboundCallForm);
  const toNumber = String(formData.get("to_number") || "").trim();
  if (!toNumber) {
    outboundCallStatus.textContent = "Enter a customer phone number.";
    outboundCallStatus.className = "form-status error";
    return;
  }

  startCallButton.disabled = true;
  outboundCallStatus.textContent = "Sending call request...";
  outboundCallStatus.className = "form-status";
  try {
    await postJson("/telnyx/outbound/call", { to_number: toNumber });
    outboundCallStatus.textContent = "Call request sent to Telnyx.";
    outboundCallStatus.className = "form-status success";
    outboundCallForm.reset();
    await loadDashboard();
  } catch (error) {
    outboundCallStatus.textContent = error.message;
    outboundCallStatus.className = "form-status error";
    await loadDashboard();
  } finally {
    startCallButton.disabled = false;
  }
});

document.querySelector("#refreshButton")?.addEventListener("click", loadDashboard);
const refreshDashboardSilently = () => {
  if (!document.hidden) loadDashboard({ silent: true });
};
setInterval(refreshDashboardSilently, 3000);
document.addEventListener("visibilitychange", refreshDashboardSilently);
window.addEventListener("focus", refreshDashboardSilently);
loadDashboard();
