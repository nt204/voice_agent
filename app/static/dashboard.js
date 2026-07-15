const state = {
  direction: "",
  interest: "",
  query: "",
  selectedId: null,
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

const formatDate = value => value
  ? new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" }).format(new Date(value))
  : "Chưa có";

const formatTime = value => value
  ? new Intl.DateTimeFormat("vi-VN", { timeStyle: "short" }).format(new Date(value))
  : "";

const formatDay = value => value
  ? new Intl.DateTimeFormat("vi-VN", { day: "2-digit", month: "2-digit", year: "2-digit" }).format(new Date(value))
  : "";

const formatMoney = value => value
  ? `${Number(value).toLocaleString("vi-VN")} đ`
  : "Chưa có";

function interestLabel(status) {
  return {
    needs_consultation: "Cần tư vấn",
    no_need: "Chưa có nhu cầu",
    unknown: "Chưa xác định",
  }[status] || "Chưa xác định";
}

function intentLabel(status) {
  return {
    ready_to_order: "Sẵn sàng mua",
    needs_consultation: "Cần tư vấn",
    considering: "Đang phân vân",
    price_checking: "Hỏi giá",
    no_need: "Chưa có nhu cầu",
    unknown: "Chưa rõ",
  }[status] || "Chưa rõ";
}

function orderStatusLabel(status) {
  return {
    ready_to_confirm: "Chờ xác nhận",
    missing_info: "Thiếu thông tin",
    draft: "Đơn nháp",
    confirmed: "Đã xác nhận",
    cancelled: "Đã hủy",
  }[status] || "Đơn nháp";
}

function directionLabel(direction) {
  return direction === "outbound" ? "Gọi ra" : "Gọi vào";
}

function directionIcon(direction) {
  return direction === "outbound" ? "↗" : "↙";
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error("Không thể tải dữ liệu");
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
    throw new Error(data.detail || "Không thể gửi yêu cầu");
  }
  return data;
}

async function loadDashboard({ silent = false } = {}) {
  if (state.refreshing) return;
  state.refreshing = true;
  if (!silent) {
    if (syncStatus) syncStatus.textContent = "Đang tải dữ liệu";
    callList.innerHTML = document.querySelector("#loadingTemplate").innerHTML;
    if (orderList) {
      orderList.innerHTML = '<div class="request-state">Đang tải...</div>';
    }
    if (orderRange) orderRange.textContent = "Đang tải";
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
    if (state.selectedId) {
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
        if (orderRange) orderRange.textContent = "0 đơn";
        if (orderPager) orderPager.innerHTML = "";
      });

    if (syncStatus) {
      syncStatus.textContent = `Cập nhật ${new Intl.DateTimeFormat("vi-VN", { timeStyle: "short" }).format(new Date())}`;
    }
  } catch (error) {
    if (!silent) {
      if (syncStatus) syncStatus.textContent = "Lỗi tải dữ liệu";
      callList.innerHTML = `<div class="error-state">${escapeHtml(error.message)}</div>`;
      if (orderList) {
        orderList.innerHTML = `<div class="request-state error">${escapeHtml(error.message)}</div>`;
      }
      if (orderRange) orderRange.textContent = "0 đơn";
      if (orderPager) orderPager.innerHTML = "";
    }
  } finally {
    state.refreshing = false;
  }
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
    <button type="button" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""} aria-label="Trang trước">&lt;</button>
    <span>Trang ${page}/${totalPages}</span>
    <button type="button" data-page="${page + 1}" ${page >= totalPages ? "disabled" : ""} aria-label="Trang sau">&gt;</button>
  `;
  container.querySelectorAll("button").forEach(button => {
    button.addEventListener("click", () => {
      const nextPage = Number(button.dataset.page);
      if (Number.isFinite(nextPage)) onPageChange(nextPage);
    });
  });
}

function renderCalls(calls) {
  document.querySelector("#resultCount").textContent = `${calls.length} kết quả`;
  if (!calls.length) {
    callList.innerHTML = document.querySelector("#emptyTemplate").innerHTML;
    if (visibleRange) visibleRange.textContent = "Hiển thị 0 kết quả";
    renderPager(callPager, 1, 1, () => {});
    return;
  }

  const page = pageSlice(calls, state.callPage, state.callPageSize);
  state.callPage = page.page;
  if (visibleRange) {
    visibleRange.textContent = `Hiển thị ${page.start + 1} đến ${page.end} của ${calls.length} kết quả`;
  }

  callList.innerHTML = page.items.map(call => {
    const customer = call.customer || {};
    const title = customer.name || customer.phone || "Khách hàng chưa xác định";
    const need = customer.need || "Chưa ghi nhận nhu cầu";
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
    orderList.innerHTML = '<div class="request-state">Chưa có đơn đủ thông tin</div>';
    if (orderRange) orderRange.textContent = "0 đơn";
    renderPager(orderPager, 1, 1, () => {});
    return;
  }

  const page = pageSlice(orders, state.orderPage, state.orderPageSize);
  state.orderPage = page.page;
  if (orderRange) {
    orderRange.textContent = `${page.start + 1}-${page.end}/${orders.length} đơn`;
  }

  orderList.innerHTML = page.items.map(order => `
    <button class="order-item ${state.selectedId === order.call_id ? "selected" : ""}" data-call-id="${escapeHtml(order.call_id)}" type="button">
      <span>
        <strong>${escapeHtml(order.customer_phone || order.call_id)}</strong>
        <small>${escapeHtml(order.product_name)} · ${order.quantity || 0} hộp</small>
        <small>Tạo ${formatDate(order.created_at)}</small>
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
  const missing = order?.missing_fields?.length ? order.missing_fields.join(", ") : "Không";
  return `
    <div class="combo-card">
      <div class="combo-head">
        <h3>Combo AI</h3>
        <span class="order-status ${escapeHtml(status)}">${order ? orderStatusLabel(status) : "Chưa tạo"}</span>
      </div>
      <div class="combo-list">
        <div><span>Sản phẩm</span><strong>${escapeHtml(order?.product_name || "Chưa có")}</strong></div>
        <div><span>Số lượng</span><strong>${order?.quantity || "Chưa có"}</strong></div>
        <div><span>Tổng tiền</span><strong>${formatMoney(order?.total_price)}</strong></div>
        <div><span>Thiếu</span><strong>${escapeHtml(missing)}</strong></div>
      </div>
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
    detailPanel.innerHTML = '<div class="empty-state"><p>Đang tải chi tiết...</p></div>';
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
  const field = value => escapeHtml(value || "Chưa cung cấp");
  const transcript = call.transcript && call.transcript.length
    ? call.transcript.map(item => {
        const isCustomer = item.speaker === "customer";
        const timestamp = item.created_at || item.timestamp || item.time || "";
        return `
        <div class="message ${isCustomer ? "customer" : "agent"}">
          <div class="message-head"><i aria-hidden="true">${isCustomer ? "&#128100;" : "&#10022;"}</i><span>${isCustomer ? "Khách hàng" : "AI tư vấn"}</span></div>
          <p dir="auto">${escapeHtml(item.text)}</p>
          ${timestamp ? `<time>${escapeHtml(formatTime(timestamp))}</time>` : ""}
        </div>`;
      }).join("")
    : '<div class="list-state">Chưa có transcript.</div>';

  detailPanel.innerHTML = `
    <div class="detail-top">
      <div class="detail-identity">
        <i class="detail-call-icon" aria-hidden="true">&#9742;</i>
        <div>
          <span class="status-pill ${escapeHtml(call.interest_status)}">${interestLabel(call.interest_status)}</span>
          <h2>${field(customer.name || customer.phone || "Khách hàng")}</h2>
          <p>${directionLabel(call.direction)} | ${escapeHtml(call.provider)} | ${formatTime(call.started_at)} | ${formatDay(call.started_at)}</p>
        </div>
      </div>
      <div class="detail-actions">
        <button class="detail-action redial-button" data-phone="${escapeHtml(customer.phone)}" type="button">&#9742; Gọi lại</button>
        <button class="detail-action icon-only" type="button" aria-label="Thêm thao tác">&#8942;</button>
      </div>
    </div>

    <div class="info-grid detail-stats">
      <div><span>Số điện thoại</span><strong>${field(customer.phone)}</strong></div>
      <div><span>Thời gian</span><strong>${formatTime(call.started_at)}<small>${formatDay(call.started_at)}</small></strong></div>
      <div><span>Loại cuộc gọi</span><strong>${directionLabel(call.direction)}</strong></div>
      <div><span>Trạng thái</span><strong><em class="status-pill ${escapeHtml(call.interest_status)}">${interestLabel(call.interest_status)}</em></strong></div>
    </div>

    <div class="detail-tabs" role="tablist" aria-label="Chi tiết lead">
      <button class="detail-tab active" data-detail-tab="info" type="button" role="tab">Thông tin</button>
      <button class="detail-tab" data-detail-tab="transcript" type="button" role="tab">Transcript</button>
    </div>

    <div class="detail-content">
      <div class="detail-summary">
        <div class="detail-note"><span>Nhu cầu</span><strong>${field(customer.need)}</strong></div>
        <div class="detail-note"><span>Địa chỉ</span><strong>${field(customer.address)}</strong></div>
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
    outboundCallStatus.textContent = "Vui lòng nhập số cần gọi.";
    outboundCallStatus.className = "form-status error";
    return;
  }

  startCallButton.disabled = true;
  outboundCallStatus.textContent = "Đang gửi yêu cầu gọi...";
  outboundCallStatus.className = "form-status";
  try {
    await postJson("/telnyx/outbound/call", { to_number: toNumber });
    outboundCallStatus.textContent = "Đã gửi yêu cầu sang Telnyx.";
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
