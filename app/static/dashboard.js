const state = {
  direction: "",
  interest: "",
  query: "",
  selectedId: null,
  selectedDetailStatus: "",
  calls: [],
  orders: [],
  products: [],
  productId: "",
  editingProductId: null,
  callPage: 1,
  callPageSize: 10,
  orderPage: 1,
  orderPageSize: 8,
  refreshing: false,
  activeCallSid: "",
};

const callList = document.querySelector("#callList");
const detailPanel = document.querySelector("#detailPanel");
const syncStatus = document.querySelector("#syncStatus");
const orderList = document.querySelector("#orderList");
const outboundCallForm = document.querySelector("#outboundCallForm");
const outboundCallStatus = document.querySelector("#outboundCallStatus");
const startCallButton = document.querySelector("#startCallButton");
const endCallButton = document.querySelector("#endCallButton");
const visibleRange = document.querySelector("#visibleRange");
const callPager = document.querySelector("#callPager");
const orderPager = document.querySelector("#orderPager");
const orderRange = document.querySelector("#orderRange");
const productFilter = document.querySelector("#productFilter");
const outboundProduct = document.querySelector("#outboundProduct");
const productManager = document.querySelector("#productManager");
const productList = document.querySelector("#productList");
const productForm = document.querySelector("#productForm");
const offerList = document.querySelector("#offerList");
const productFormStatus = document.querySelector("#productFormStatus");

const escapeHtml = (value = "") => String(value).replace(
  /[&<>"']/g,
  char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[char]
);

const LOCALE = "vi-VN";

const formatDate = value => value
  ? new Intl.DateTimeFormat(LOCALE, { dateStyle: "short", timeStyle: "short" }).format(new Date(value))
  : "Chưa có";

const formatTime = value => value
  ? new Intl.DateTimeFormat(LOCALE, { timeStyle: "short" }).format(new Date(value))
  : "";

const formatDay = value => value
  ? new Intl.DateTimeFormat(LOCALE, { day: "2-digit", month: "2-digit", year: "2-digit" }).format(new Date(value))
  : "";

const formatMoney = value => value
  ? `${Number(value).toLocaleString(LOCALE)} MMK`
  : "Chưa có";

const formatBytes = value => {
  const bytes = Number(value || 0);
  if (!bytes) return "";
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
};

function interestLabel(status) {
  return {
    needs_consultation: "Cần tư vấn",
    no_need: "Không có nhu cầu",
    unknown: "Chưa xác định",
  }[status] || "Chưa xác định";
}

function intentLabel(status) {
  return {
    ready_to_order: "Sẵn sàng đặt hàng",
    needs_consultation: "Cần tư vấn",
    considering: "Đang cân nhắc",
    price_checking: "Đang hỏi giá",
    no_need: "Không có nhu cầu",
    unknown: "Chưa xác định",
  }[status] || "Chưa xác định";
}

function orderStatusLabel(status) {
  return {
    ready_to_confirm: "Chờ xác nhận",
    missing_info: "Thiếu thông tin",
    draft: "Bản nháp",
    confirmed: "Đã xác nhận",
    cancelled: "Đã hủy",
  }[status] || "Bản nháp";
}

function recordingStatusLabel(status) {
  return {
    active: "Đang ghi âm",
    completed: "Đã lưu",
    failed: "Ghi âm lỗi",
  }[status] || "Chưa có";
}

function directionLabel(direction) {
  return direction === "outbound" ? "Gọi đi" : "Gọi đến";
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

function setActiveCall(callSid = "") {
  state.activeCallSid = callSid;
  startCallButton.hidden = Boolean(callSid);
  endCallButton.hidden = !callSid;
  endCallButton.disabled = false;
}

function syncActiveCallControl(calls) {
  if (!state.activeCallSid) return;
  const activeCall = calls.find(call => call.id === state.activeCallSid);
  if (activeCall && activeCall.status !== "active") setActiveCall();
}

async function writeJson(url, method, body) {
  const response = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "Không thể lưu sản phẩm");
  }
  return data;
}

async function loadProducts({ preserveSelection = true } = {}) {
  const previousFilter = preserveSelection ? state.productId : "";
  const previousOutbound = outboundProduct?.value || "";
  const data = await fetchJson("/api/products");
  state.products = data.products || [];
  const activeProducts = state.products.filter(product => product.active);
  const defaultProduct = activeProducts.find(product => product.is_default) || activeProducts[0];

  if (productFilter) {
    productFilter.innerHTML = '<option value="">Tất cả sản phẩm</option>' + state.products.map(product => `
      <option value="${product.id}">${escapeHtml(product.name)}${product.active ? "" : " (tạm ngưng)"}</option>
    `).join("");
    state.productId = state.products.some(product => String(product.id) === String(previousFilter))
      ? String(previousFilter)
      : "";
    productFilter.value = state.productId;
  }

  if (outboundProduct) {
    outboundProduct.innerHTML = activeProducts.length
      ? activeProducts.map(product => `<option value="${product.id}">${escapeHtml(product.name)}</option>`).join("")
      : '<option value="">Chưa có sản phẩm hoạt động</option>';
    const preferred = activeProducts.some(product => String(product.id) === String(previousOutbound))
      ? previousOutbound
      : defaultProduct?.id || "";
    outboundProduct.value = String(preferred);
  }
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
  if (state.productId) params.set("product_id", state.productId);

  try {
    const [summary, listing] = await Promise.all([
      fetchJson(`/api/admin/summary${state.productId ? `?product_id=${encodeURIComponent(state.productId)}` : ""}`),
      fetchJson(`/api/calls?${params}`),
    ]);
    renderSummary(summary.stats);
    state.calls = listing.calls;
    syncActiveCallControl(listing.calls);
    renderCalls(listing.calls);
    if (shouldRefreshSelectedDetail(listing.calls, { silent })) {
      await loadDetail(state.selectedId, { silent: true });
    }

    fetchJson(`/api/orders?limit=100${state.productId ? `&product_id=${encodeURIComponent(state.productId)}` : ""}`)
      .then(orders => {
        state.orders = recordedOrders(orders.orders || []);
        renderOrders(state.orders);
      })
      .catch(error => {
        state.orders = [];
        if (orderList) {
          orderList.innerHTML = `<div class="request-state error">${escapeHtml(error.message)}</div>`;
        }
        if (orderRange) orderRange.textContent = "0 đơn hàng";
        if (orderPager) orderPager.innerHTML = "";
      });

    if (syncStatus) {
      syncStatus.textContent = `Đã cập nhật ${new Intl.DateTimeFormat(LOCALE, { timeStyle: "short" }).format(new Date())}`;
    }
  } catch (error) {
    if (!silent) {
      if (syncStatus) syncStatus.textContent = "Lỗi tải dữ liệu";
      callList.innerHTML = `<div class="error-state">${escapeHtml(error.message)}</div>`;
      if (orderList) {
        orderList.innerHTML = `<div class="request-state error">${escapeHtml(error.message)}</div>`;
      }
      if (orderRange) orderRange.textContent = "0 đơn hàng";
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
    if (visibleRange) visibleRange.textContent = "Đang hiển thị 0 kết quả";
    renderPager(callPager, 1, 1, () => {});
    return;
  }

  const page = pageSlice(calls, state.callPage, state.callPageSize);
  state.callPage = page.page;
  if (visibleRange) {
    visibleRange.textContent = `Hiển thị ${page.start + 1}-${page.end} trong ${calls.length} kết quả`;
  }

  callList.innerHTML = page.items.map(call => {
    const customer = call.customer || {};
    const displayPhone = customer.phone || call.dialed_phone || "";
    const title = customer.name || displayPhone || "Khách chưa xác định";
    const need = customer.need || "Chưa ghi nhận nhu cầu";
    const isSelected = state.selectedId === call.id;
    return `
      <button class="lead-row ${isSelected ? "selected" : ""}" data-id="${escapeHtml(call.id)}" type="button">
        <span class="lead-person">
          <strong><i class="lead-phone-icon" aria-hidden="true">&#9742;</i>${escapeHtml(title)}</strong>
          <small>${escapeHtml(displayPhone || call.id)}${call.product?.name ? ` | ${escapeHtml(call.product.name)}` : ""}</small>
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
    orderList.innerHTML = '<div class="request-state">Chưa có đơn hàng đủ thông tin</div>';
    if (orderRange) orderRange.textContent = "0 đơn hàng";
    renderPager(orderPager, 1, 1, () => {});
    return;
  }

  const page = pageSlice(orders, state.orderPage, state.orderPageSize);
  state.orderPage = page.page;
  if (orderRange) {
    orderRange.textContent = `${page.start + 1}-${page.end}/${orders.length} đơn hàng`;
  }

  orderList.innerHTML = page.items.map(order => `
    <button class="order-item ${state.selectedId === order.call_id ? "selected" : ""}" data-call-id="${escapeHtml(order.call_id)}" type="button">
      <span>
        <strong>${escapeHtml(order.customer_phone || order.call_id)}</strong>
        <small>${escapeHtml(order.product_name)} | ${order.quantity || 0} hộp</small>
        ${order.product?.name ? `<small>Sản phẩm: ${escapeHtml(order.product.name)}</small>` : ""}
        <small>Tạo lúc ${formatDate(order.created_at)}</small>
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

function renderOrderCard(call) {
  const customer = call.customer || {};
  const order = call.order || null;
  const dialedPhone = call.dialed_phone || "";
  const phone = customer.phone || dialedPhone || "";
  const name = customer.name || "";
  const address = customer.address || "";
  const status = order ? order.status : "missing_info";
  const missing = order?.missing_fields?.length ? order.missing_fields.join(", ") : "Không";
  const field = value => escapeHtml(value || "Chưa cung cấp");

  return `
    <div class="combo-card order-info-card">
      <div class="combo-head">
        <h3>Thông tin đơn hàng</h3>
        <span class="order-status ${escapeHtml(status)}">${order ? orderStatusLabel(status) : "Chưa tạo"}</span>
      </div>
      <div class="combo-list">
        <div><span>Tên khách hàng</span><strong>${field(name)}</strong></div>
        <div><span>Số điện thoại</span><strong>${field(phone)}</strong></div>
        <div><span>Địa chỉ</span><strong>${field(address)}</strong></div>
        <div><span>Gói / Combo</span><strong>${escapeHtml(order?.product_name || call.product?.name || "Chưa có")}${order?.quantity ? ` (${order.quantity} hộp)` : ""}</strong></div>
        <div><span>Tổng tiền</span><strong>${formatMoney(order?.total_price)}</strong></div>
        ${order?.missing_fields?.length ? `<div><span>Còn thiếu</span><strong style="color:var(--warning);">${escapeHtml(missing)}</strong></div>` : ""}
      </div>
    </div>`;
}

function renderRecordingCard(call) {
  const recording = call.recording || null;
  if (call.status !== "completed") {
    return `
      <div class="recording-card empty-recording">
        <div class="recording-head">
          <h3>Bản ghi cuộc gọi</h3>
          <span>${escapeHtml(recordingStatusLabel("active"))}</span>
        </div>
        <p>Bản ghi sẽ xuất hiện sau khi cuộc gọi kết thúc.</p>
      </div>`;
  }

  const files = recording?.files || {};
  const tracks = [
    { key: "mixed", label: "Toàn bộ cuộc gọi", file: files.mixed },
    { key: "inbound", label: "Khách hàng", file: files.inbound },
    { key: "outbound", label: "Tư vấn viên", file: files.outbound },
  ].filter(track => track.file && track.file.url);
  const status = recording?.status || "completed";

  if (!tracks.length) {
    return `
      <div class="recording-card empty-recording">
        <div class="recording-head">
          <h3>Bản ghi cuộc gọi</h3>
          <span>${escapeHtml(recordingStatusLabel(status))}</span>
        </div>
        <p>Cuộc gọi này chưa có tệp ghi âm.</p>
      </div>`;
  }

  const primary = tracks.find(track => track.key === "mixed") || tracks[0];
  const secondary = tracks.filter(track => track !== primary);
  return `
    <div class="recording-card">
      <div class="recording-head">
        <h3>Bản ghi cuộc gọi</h3>
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
  const dialedPhone = call.dialed_phone || "";
  const redialPhone = dialedPhone || customer.phone || "";
  state.selectedDetailStatus = call.status || "";
  const field = value => escapeHtml(value || "Chưa cung cấp");
  const transcript = call.transcript && call.transcript.length
    ? call.transcript.map(item => {
        const isCustomer = item.speaker === "customer";
        const timestamp = item.created_at || item.timestamp || item.time || "";
        return `
        <div class="message ${isCustomer ? "customer" : "agent"}">
          <div class="message-head"><i aria-hidden="true">${isCustomer ? "&#128100;" : "&#10022;"}</i><span>${isCustomer ? "Khách hàng" : "Tư vấn viên"}</span></div>
          <p dir="auto">${escapeHtml(item.text)}</p>
          ${timestamp ? `<time>${escapeHtml(formatTime(timestamp))}</time>` : ""}
        </div>`;
      }).join("")
    : '<div class="list-state">Chưa có nội dung hội thoại.</div>';

  detailPanel.innerHTML = `
    <div class="detail-top">
      <div class="detail-identity">
        <i class="detail-call-icon" aria-hidden="true">&#9742;</i>
        <div>
          <span class="status-pill ${escapeHtml(call.interest_status)}">${interestLabel(call.interest_status)}</span>
          <h2>${field(customer.name || customer.phone || dialedPhone || "Khách hàng")}</h2>
          <p>${directionLabel(call.direction)} | ${escapeHtml(call.provider)} | ${formatTime(call.started_at)} | ${formatDay(call.started_at)}</p>
        </div>
      </div>
      <div class="detail-actions">
        <button class="detail-action redial-button" data-phone="${escapeHtml(redialPhone)}" data-product-id="${call.product?.id || ""}" type="button">&#9742; Gọi lại</button>
        <button class="detail-action icon-only" type="button" aria-label="Thêm thao tác">&#8942;</button>
      </div>
    </div>

    <div class="info-grid detail-stats">
      <div><span>Sản phẩm</span><strong>${field(call.product?.name)}</strong></div>
      <div><span>Số đã gọi</span><strong>${field(dialedPhone)}</strong></div>
      <div><span>Số khách cung cấp</span><strong>${field(customer.phone)}</strong></div>
      <div><span>Thời gian</span><strong>${formatTime(call.started_at)}<small>${formatDay(call.started_at)}</small></strong></div>
      <div><span>Loại cuộc gọi</span><strong>${directionLabel(call.direction)}</strong></div>
      <div><span>Trạng thái</span><strong><em class="status-pill ${escapeHtml(call.interest_status)}">${interestLabel(call.interest_status)}</em></strong></div>
    </div>

    <div class="detail-tabs" role="tablist" aria-label="Chi tiết khách hàng">
      <button class="detail-tab active" data-detail-tab="info" type="button" role="tab">Thông tin</button>
      <button class="detail-tab" data-detail-tab="transcript" type="button" role="tab">Hội thoại</button>
    </div>

    <div class="detail-content">
      <div class="detail-summary">
        ${renderOrderCard(call)}
        ${renderRecordingCard(call)}
      </div>

      <section class="transcript-panel">
        <h3 class="section-title">Nội dung hội thoại</h3>
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
        if (event.currentTarget.dataset.productId && outboundProduct) {
          outboundProduct.value = event.currentTarget.dataset.productId;
        }
        outboundCallForm?.requestSubmit();
      }
    });
  });
}

function renderProductManager() {
  if (!productList) return;
  if (!state.products.length) {
    productList.innerHTML = '<div class="request-state">Chưa có sản phẩm. Hãy thêm sản phẩm đầu tiên để bắt đầu.</div>';
    return;
  }
  productList.innerHTML = state.products.map(product => `
    <button class="product-list-item ${Number(state.editingProductId) === Number(product.id) ? "selected" : ""}" data-product-id="${product.id}" type="button">
      <strong>${escapeHtml(product.name)}</strong>
      <span class="product-state ${product.active ? "" : "inactive"}">${product.is_default ? "Sản phẩm mặc định" : product.active ? "Đang hoạt động" : "Tạm ngưng"}</span>
      <small>${escapeHtml(product.phone_number || "Chưa cấu hình số điện thoại")}</small>
      <small>${product.offers?.length || 0} gói bán</small>
    </button>
  `).join("");
  productList.querySelectorAll(".product-list-item").forEach(button => {
    button.addEventListener("click", () => editProduct(Number(button.dataset.productId)));
  });
}

function renderOfferRows(offers = []) {
  if (!offerList) return;
  if (!offers.length) {
    offerList.innerHTML = '<div class="empty-offers">Chưa có gói bán. Hãy thêm giá bán lẻ hoặc combo.</div>';
    return;
  }
  offerList.innerHTML = offers.map((offer, index) => `
    <div class="offer-row" data-offer-index="${index}">
      <label class="offer-field"><span>Tên gói bán</span><input data-offer="name" value="${escapeHtml(offer.name || "")}" required></label>
      <label class="offer-field"><span>Số lượng</span><input data-offer="quantity" type="number" min="1" value="${Number(offer.quantity || 1)}" required></label>
      <label class="offer-field"><span>Đơn giá</span><input data-offer="unit_price" type="number" min="1" value="${Number(offer.unit_price || 1)}" required></label>
      <label class="offer-field"><span>Tổng giá</span><input data-offer="total_price" type="number" min="1" value="${Number(offer.total_price || 1)}" required></label>
      <label class="offer-field"><span>Vận chuyển</span><input data-offer="shipping_policy" value="${escapeHtml(offer.shipping_policy || "")}" placeholder="Miễn phí giao hàng"></label>
      <button class="remove-offer-button" type="button" aria-label="Xóa ${escapeHtml(offer.name || "gói bán")}">&#10005;</button>
    </div>
  `).join("");
  offerList.querySelectorAll(".remove-offer-button").forEach(button => {
    button.addEventListener("click", () => {
      button.closest(".offer-row")?.remove();
      if (!offerList.querySelector(".offer-row")) renderOfferRows([]);
    });
  });
}

function blankProductForm() {
  state.editingProductId = null;
  productForm?.reset();
  document.querySelector("#productId").value = "";
  document.querySelector("#productActive").checked = true;
  document.querySelector("#productActive").disabled = false;
  document.querySelector("#productLanguage").value = "my-MM";
  document.querySelector("#productVoice").value = "Aoede";
  document.querySelector("#productEditorTitle").textContent = "Thêm sản phẩm";
  document.querySelector("#productEditorHint").textContent = "Thiết lập số điện thoại và nội dung tư vấn riêng cho sản phẩm.";
  document.querySelector("#setDefaultProductButton").hidden = true;
  productFormStatus.textContent = "";
  productFormStatus.className = "form-status";
  renderOfferRows([]);
  renderProductManager();
  document.querySelector("#productName")?.focus();
}

function editProduct(productId) {
  const product = state.products.find(item => Number(item.id) === Number(productId));
  if (!product) return;
  state.editingProductId = product.id;
  document.querySelector("#productId").value = product.id;
  document.querySelector("#productName").value = product.name || "";
  document.querySelector("#productPhone").value = product.phone_number || "";
  document.querySelector("#productSlug").value = product.slug || "";
  document.querySelector("#productTexmlApp").value = product.texml_app_id || "";
  document.querySelector("#productInboundGreeting").value = product.inbound_greeting || "";
  document.querySelector("#productOutboundGreeting").value = product.outbound_greeting || "";
  document.querySelector("#productSystemPrompt").value = product.system_prompt || "";
  document.querySelector("#productKnowledge").value = product.knowledge || "";
  document.querySelector("#productLanguage").value = product.language_code || "my-MM";
  document.querySelector("#productVoice").value = product.voice_name || "Aoede";
  const activeInput = document.querySelector("#productActive");
  activeInput.checked = Boolean(product.active);
  activeInput.disabled = Boolean(product.is_default);
  document.querySelector("#productEditorTitle").textContent = product.name;
  document.querySelector("#productEditorHint").textContent = product.is_default
    ? "Đây là sản phẩm mặc định. Hãy chọn sản phẩm mặc định khác trước khi tạm ngưng."
    : "Thay đổi chỉ áp dụng cho cuộc gọi mới. Đơn hàng cũ vẫn giữ nguyên giá đã lưu.";
  document.querySelector("#setDefaultProductButton").hidden = Boolean(product.is_default || !product.active);
  productFormStatus.textContent = "";
  productFormStatus.className = "form-status";
  renderOfferRows(product.offers || []);
  renderProductManager();
}

function collectOffers() {
  return Array.from(offerList?.querySelectorAll(".offer-row") || []).map(row => ({
    name: row.querySelector('[data-offer="name"]').value.trim(),
    quantity: Number(row.querySelector('[data-offer="quantity"]').value),
    unit_price: Number(row.querySelector('[data-offer="unit_price"]').value),
    total_price: Number(row.querySelector('[data-offer="total_price"]').value),
    shipping_policy: row.querySelector('[data-offer="shipping_policy"]').value.trim(),
    active: true,
  }));
}

function productPayload() {
  return {
    name: document.querySelector("#productName").value.trim(),
    phone_number: document.querySelector("#productPhone").value.trim(),
    slug: document.querySelector("#productSlug").value.trim(),
    texml_app_id: document.querySelector("#productTexmlApp").value.trim(),
    inbound_greeting: document.querySelector("#productInboundGreeting").value.trim(),
    outbound_greeting: document.querySelector("#productOutboundGreeting").value.trim(),
    system_prompt: document.querySelector("#productSystemPrompt").value.trim(),
    knowledge: document.querySelector("#productKnowledge").value.trim(),
    language_code: document.querySelector("#productLanguage").value.trim(),
    voice_name: document.querySelector("#productVoice").value.trim(),
    active: document.querySelector("#productActive").checked,
    offers: collectOffers(),
  };
}

function openProductManager() {
  productManager.hidden = false;
  document.body.classList.add("product-manager-open");
  const defaultProduct = state.products.find(product => product.is_default) || state.products[0];
  if (defaultProduct) editProduct(state.editingProductId || defaultProduct.id);
  else blankProductForm();
}

function closeProductManager() {
  productManager.hidden = true;
  document.body.classList.remove("product-manager-open");
  document.querySelector("#manageProductsButton")?.focus();
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

productFilter?.addEventListener("change", event => {
  state.productId = event.target.value;
  state.callPage = 1;
  state.orderPage = 1;
  state.selectedId = null;
  detailPanel.innerHTML = '<div class="empty-state"><div class="empty-mark" aria-hidden="true">☎</div><h2>Chọn một khách hàng để xem chi tiết</h2><p>Thông tin liên hệ, bản ghi và nội dung trao đổi sẽ xuất hiện tại đây.</p></div>';
  loadDashboard();
});

document.querySelector("#manageProductsButton")?.addEventListener("click", openProductManager);
document.querySelectorAll("[data-close-products]").forEach(button => {
  button.addEventListener("click", closeProductManager);
});
document.addEventListener("keydown", event => {
  if (event.key === "Escape" && productManager && !productManager.hidden) closeProductManager();
});
document.querySelector("#newProductButton")?.addEventListener("click", blankProductForm);
document.querySelector("#addOfferButton")?.addEventListener("click", () => {
  const offers = collectOffers();
  offers.push({
    name: "",
    quantity: 1,
    unit_price: 1,
    total_price: 1,
    shipping_policy: "",
    active: true,
  });
  renderOfferRows(offers);
  offerList?.querySelector(".offer-row:last-child input")?.focus();
});

productForm?.addEventListener("submit", async event => {
  event.preventDefault();
  if (!productForm.reportValidity()) return;
  const saveButton = document.querySelector("#saveProductButton");
  saveButton.disabled = true;
  productFormStatus.textContent = "Đang lưu sản phẩm...";
  productFormStatus.className = "form-status";
  try {
    const productId = state.editingProductId;
    const result = productId
      ? await writeJson(`/api/products/${productId}`, "PUT", productPayload())
      : await writeJson("/api/products", "POST", productPayload());
    await loadProducts();
    editProduct(result.product.id);
    productFormStatus.textContent = "Đã lưu sản phẩm. Các cuộc gọi mới sẽ dùng cấu hình này.";
    productFormStatus.className = "form-status success";
    await loadDashboard({ silent: true });
  } catch (error) {
    productFormStatus.textContent = error.message;
    productFormStatus.className = "form-status error";
  } finally {
    saveButton.disabled = false;
  }
});

document.querySelector("#setDefaultProductButton")?.addEventListener("click", async () => {
  if (!state.editingProductId) return;
  productFormStatus.textContent = "Đang đặt sản phẩm mặc định...";
  productFormStatus.className = "form-status";
  try {
    const result = await postJson(`/api/products/${state.editingProductId}/default`, {});
    await loadProducts();
    editProduct(result.product.id);
    productFormStatus.textContent = "Đã cập nhật sản phẩm mặc định.";
    productFormStatus.className = "form-status success";
  } catch (error) {
    productFormStatus.textContent = error.message;
    productFormStatus.className = "form-status error";
  }
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
  const productId = String(formData.get("product_id") || "").trim();
  if (!productId) {
    outboundCallStatus.textContent = "Hãy chọn sản phẩm trước khi gọi.";
    outboundCallStatus.className = "form-status error";
    return;
  }
  if (!toNumber) {
    outboundCallStatus.textContent = "Hãy nhập số điện thoại khách hàng.";
    outboundCallStatus.className = "form-status error";
    return;
  }

  startCallButton.disabled = true;
  outboundCallStatus.textContent = "Đang gửi yêu cầu gọi...";
  outboundCallStatus.className = "form-status";
  try {
    const result = await postJson("/telnyx/outbound/call", {
      to_number: toNumber,
      product_id: Number(productId),
    });
    state.activeCallSid = result.call_sid;
    setActiveCall(state.activeCallSid);
    outboundCallStatus.textContent = "Đã gửi yêu cầu gọi đến Telnyx.";
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

endCallButton?.addEventListener("click", async () => {
  if (!state.activeCallSid) return;
  endCallButton.disabled = true;
  outboundCallStatus.textContent = "Đang ngắt cuộc gọi...";
  outboundCallStatus.className = "form-status";
  try {
    await postJson(`/telnyx/outbound/call/${encodeURIComponent(state.activeCallSid)}/hangup`);
    setActiveCall();
    outboundCallStatus.textContent = "Đã ngắt cuộc gọi.";
    outboundCallStatus.className = "form-status success";
    await loadDashboard();
  } catch (error) {
    endCallButton.disabled = false;
    outboundCallStatus.textContent = error.message;
    outboundCallStatus.className = "form-status error";
  }
});

document.querySelector("#refreshButton")?.addEventListener("click", loadDashboard);
const refreshDashboardSilently = () => {
  if (!document.hidden) loadDashboard({ silent: true });
};
setInterval(refreshDashboardSilently, 3000);
document.addEventListener("visibilitychange", refreshDashboardSilently);
window.addEventListener("focus", refreshDashboardSilently);
async function bootDashboard() {
  try {
    await loadProducts({ preserveSelection: false });
  } catch (error) {
    if (syncStatus) syncStatus.textContent = "Lỗi tải sản phẩm";
  }
  await loadDashboard();
}

bootDashboard();
