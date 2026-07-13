const state = {
  direction: "",
  interest: "",
  query: "",
  selectedId: null,
  calls: [],
};

const callList = document.querySelector("#callList");
const detailPanel = document.querySelector("#detailPanel");
const syncStatus = document.querySelector("#syncStatus");
const outboundRequestList = document.querySelector("#outboundRequestList");
const outboundCallForm = document.querySelector("#outboundCallForm");
const outboundCallStatus = document.querySelector("#outboundCallStatus");
const startCallButton = document.querySelector("#startCallButton");
const visibleRange = document.querySelector("#visibleRange");

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

const formatDuration = seconds => {
  const safe = Number.isFinite(seconds) ? seconds : 0;
  const minutes = Math.floor(safe / 60);
  return `${minutes}:${String(safe % 60).padStart(2, "0")}`;
};

const formatPercent = value => `${Math.round((value || 0) * 100)}%`;

function interestLabel(status) {
  return {
    needs_consultation: "Cần tư vấn",
    no_need: "Chưa có nhu cầu",
    unknown: "Chưa xác định",
  }[status] || "Chưa xác định";
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

async function loadDashboard() {
  if (syncStatus) syncStatus.textContent = "Đang tải dữ liệu";
  callList.innerHTML = document.querySelector("#loadingTemplate").innerHTML;
  if (outboundRequestList) {
    outboundRequestList.innerHTML = '<div class="request-state">Đang tải...</div>';
  }
  const params = new URLSearchParams();
  if (state.direction) params.set("direction", state.direction);
  if (state.interest) params.set("interest_status", state.interest);
  if (state.query) params.set("q", state.query);

  try {
    const [summary, listing, outboundRequests] = await Promise.all([
      fetchJson("/api/admin/summary"),
      fetchJson(`/api/calls?${params}`),
      fetchJson("/api/outbound/requests?limit=8"),
    ]);
    renderSummary(summary.stats);
    state.calls = listing.calls;
    renderCalls(listing.calls);
    renderOutboundRequests(outboundRequests.requests || []);
    if (syncStatus) {
      syncStatus.textContent = `Cập nhật ${new Intl.DateTimeFormat("vi-VN", { timeStyle: "short" }).format(new Date())}`;
    }
  } catch (error) {
    if (syncStatus) syncStatus.textContent = "Lỗi tải dữ liệu";
    callList.innerHTML = `<div class="error-state">${escapeHtml(error.message)}</div>`;
    if (outboundRequestList) {
      outboundRequestList.innerHTML = `<div class="request-state error">${escapeHtml(error.message)}</div>`;
    }
  }
}

function renderSummary(stats) {
  const interest = stats.interest_counts || {};
  const directions = stats.direction_counts || {};
  document.querySelector("#kpiTotal").textContent = stats.total_calls || 0;
  document.querySelector("#kpiActive").textContent = `${stats.active_calls || 0} đang diễn ra`;
  document.querySelector("#kpiLeads").textContent = interest.needs_consultation || 0;
  document.querySelector("#kpiLeadRate").textContent = `${formatPercent(stats.lead_rate)} trên tổng cuộc gọi`;
  document.querySelector("#kpiPhones").textContent = stats.contacts_with_phone || 0;
  document.querySelector("#kpiContactRate").textContent = `${formatPercent(stats.contact_capture_rate)} tỉ lệ thu thập`;
  document.querySelector("#kpiDuration").textContent = formatDuration(stats.avg_duration_seconds || 0);
  document.querySelector("#kpiMessages").textContent = `${stats.avg_messages_per_call || 0} tin nhắn mỗi cuộc gọi`;

  document.querySelector("#funnelAll").textContent = stats.total_calls || 0;
  document.querySelector("#funnelHot").textContent = interest.needs_consultation || 0;
  document.querySelector("#funnelCold").textContent = interest.no_need || 0;
  document.querySelector("#funnelUnknown").textContent = interest.unknown || 0;
  document.querySelector("#resultCount").textContent =
    `${directions.inbound || 0} gọi vào, ${directions.outbound || 0} gọi ra`;
}

function renderCalls(calls) {
  document.querySelector("#resultCount").textContent = `${calls.length} kết quả`;
  if (visibleRange) {
    visibleRange.textContent = calls.length
      ? `Hiển thị 1 đến ${calls.length} của ${calls.length} kết quả`
      : "Hiển thị 0 kết quả";
  }
  if (!calls.length) {
    callList.innerHTML = document.querySelector("#emptyTemplate").innerHTML;
    return;
  }

  callList.innerHTML = calls.map(call => {
    const customer = call.customer || {};
    const title = customer.name || customer.phone || "Khách hàng chưa xác định";
    const need = customer.need || "Chưa ghi nhận nhu cầu";
    const isSelected = state.selectedId === call.id;
    return `
      <button class="lead-row ${isSelected ? "selected" : ""}" data-id="${escapeHtml(call.id)}" type="button">
        <span class="lead-person">
          <strong>${escapeHtml(title)}</strong>
          <small>${escapeHtml(customer.phone || call.id)}</small>
        </span>
        <span class="lead-need">${escapeHtml(need)}</span>
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
}

function requestStatusLabel(status) {
  return {
    queued: "Đang chờ",
    started: "Đã gửi",
    completed: "Hoàn tất",
    no_answer: "Không nghe máy",
    busy: "Máy bận",
    canceled: "Đã hủy",
    failed: "Lỗi",
  }[status] || "Không rõ";
}

function renderOutboundRequests(requests) {
  if (!outboundRequestList) return;
  if (!requests.length) {
    outboundRequestList.innerHTML = '<div class="request-state">Chưa có yêu cầu gọi ra.</div>';
    return;
  }

  outboundRequestList.innerHTML = requests.map(request => `
    <div class="request-item">
      <div>
        <strong>${escapeHtml(request.to_number)}</strong>
        <span>${formatDate(request.created_at)}</span>
        ${request.error ? `<small>${escapeHtml(request.error)}</small>` : ""}
      </div>
      <b class="request-status ${escapeHtml(request.status)}">${requestStatusLabel(request.status)}</b>
    </div>
  `).join("");
}

async function loadDetail(callId) {
  state.selectedId = callId;
  document.querySelectorAll(".lead-row").forEach(row => {
    row.classList.toggle("selected", row.dataset.id === callId);
  });
  detailPanel.innerHTML = '<div class="empty-state"><p>Đang tải chi tiết...</p></div>';
  try {
    renderDetail(await fetchJson(`/api/calls/${encodeURIComponent(callId)}`));
  } catch (error) {
    detailPanel.innerHTML = `<div class="error-state">${escapeHtml(error.message)}</div>`;
  }
}

function renderDetail(call) {
  const customer = call.customer || {};
  const field = value => escapeHtml(value || "Chưa cung cấp");
  const transcript = call.transcript && call.transcript.length
    ? call.transcript.map(item => `
        <div class="message ${escapeHtml(item.speaker)}">
          <span>${item.speaker === "customer" ? "Khách hàng" : "AI tư vấn"}</span>
          <p>${escapeHtml(item.text)}</p>
        </div>`).join("")
    : '<div class="list-state">Chưa có transcript.</div>';

  detailPanel.innerHTML = `
    <div class="detail-top">
      <div>
        <span class="status-pill ${escapeHtml(call.interest_status)}">${interestLabel(call.interest_status)}</span>
        <h2>${field(customer.name || customer.phone || "Khách hàng")}</h2>
        <p>${directionLabel(call.direction)} | ${escapeHtml(call.provider)} | ${formatTime(call.started_at)}</p>
      </div>
    </div>

    <div class="info-grid">
      <div><span>Số điện thoại</span><strong>${field(customer.phone)}</strong></div>
      <div><span>Thời gian</span><strong>${formatDate(call.started_at)}</strong></div>
      <div class="wide"><span>Nhu cầu</span><strong>${field(customer.need)}</strong></div>
      <div class="wide"><span>Địa chỉ</span><strong>${field(customer.address)}</strong></div>
    </div>

    <div class="sales-notes">
      <h3>Gợi ý xử lý</h3>
      <p>${nextAction(call)}</p>
    </div>

    <h3 class="section-title">Transcript</h3>
    <div class="transcript">${transcript}</div>
    <form class="reply-box">
      <textarea aria-label="Nhập nội dung" placeholder="Nhập nội dung..." disabled></textarea>
      <button type="button" disabled>Gửi</button>
    </form>`;
}

function nextAction(call) {
  const customer = call.customer || {};
  if (call.interest_status === "needs_consultation" && customer.phone) {
    return "Lead nóng đã có số điện thoại. Nên gọi lại hoặc chuyển cho nhân viên chốt đơn trong ngày.";
  }
  if (call.interest_status === "needs_consultation") {
    return "Lead có nhu cầu nhưng thiếu số điện thoại. Cần ưu tiên kịch bản thu thập thông tin liên hệ.";
  }
  if (call.interest_status === "no_need") {
    return "Khách chưa có nhu cầu. Đưa vào nhóm chăm sóc lại, tránh gọi dồn quá sớm.";
  }
  return "Chưa rõ intent. Nên rà transcript để cải thiện prompt hoặc kịch bản hỏi nhu cầu.";
}

document.querySelectorAll(".funnel-item").forEach(button => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".funnel-item").forEach(item => item.classList.remove("active"));
    button.classList.add("active");
    state.interest = button.dataset.interest;
    loadDashboard();
  });
});

document.querySelectorAll(".segment").forEach(button => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".segment").forEach(item => item.classList.remove("active"));
    button.classList.add("active");
    state.direction = button.dataset.direction;
    loadDashboard();
  });
});

let searchTimer;
document.querySelector("#searchInput").addEventListener("input", event => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.query = event.target.value.trim();
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
loadDashboard();
