const state = { direction: "", interest: "", query: "", selectedId: null };
const callList = document.querySelector("#callList");
const detailPanel = document.querySelector("#detailPanel");

const escapeHtml = (value = "") => String(value).replace(
  /[&<>"']/g,
  char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[char]
);

const formatDate = value => value
  ? new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" }).format(new Date(value))
  : "";

const formatDuration = seconds => {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
};

async function loadCalls() {
  callList.innerHTML = '<div class="empty-list"><p>Đang tải...</p></div>';
  const params = new URLSearchParams();
  if (state.direction) params.set("direction", state.direction);
  if (state.interest) params.set("interest_status", state.interest);
  if (state.query) params.set("q", state.query);
  try {
    const response = await fetch(`/api/calls?${params}`);
    if (!response.ok) throw new Error("Không thể tải lịch sử");
    const data = await response.json();
    document.querySelector("#countAll").textContent = data.counts.all;
    document.querySelector("#countInbound").textContent = data.counts.inbound;
    document.querySelector("#countOutbound").textContent = data.counts.outbound;
    document.querySelector("#countConsultation").textContent = data.interest_counts.needs_consultation;
    document.querySelector("#countNoNeed").textContent = data.interest_counts.no_need;
    document.querySelector("#countUnknown").textContent = data.interest_counts.unknown;
    renderCalls(data.calls);
  } catch (error) {
    callList.innerHTML = `<div class="error-state">${escapeHtml(error.message)}</div>`;
  }
}

function renderCalls(calls) {
  if (!calls.length) {
    callList.innerHTML = document.querySelector("#emptyTemplate").innerHTML;
    return;
  }
  callList.innerHTML = calls.map(call => {
    const customer = call.customer;
    const title = customer.name || customer.phone || "Khách hàng chưa xác định";
    const subtitle = customer.need || `${call.provider} · ${formatDuration(call.duration_seconds)}`;
    const incoming = call.direction === "inbound";
    const interest = interestLabel(call.interest_status);
    return `
      <button class="call-row ${state.selectedId === call.id ? "selected" : ""}" data-id="${escapeHtml(call.id)}">
        <span class="direction-icon" title="${incoming ? "Cuộc gọi đến" : "Cuộc gọi đi"}">${incoming ? "↙" : "↗"}</span>
        <span class="call-main">
          <strong>${escapeHtml(title)}</strong>
          <small>${escapeHtml(subtitle)}</small>
          <span class="interest-badge ${call.interest_status}">${interest}</span>
        </span>
        <span class="call-time">${formatDate(call.started_at)}</span>
      </button>`;
  }).join("");
  document.querySelectorAll(".call-row").forEach(button => {
    button.addEventListener("click", () => loadDetail(button.dataset.id));
  });
}

function interestLabel(status) {
  return {
    needs_consultation: "Cần tư vấn",
    no_need: "Chưa có nhu cầu",
    unknown: "Chưa xác định",
  }[status] || "Chưa xác định";
}

async function loadDetail(callId) {
  state.selectedId = callId;
  document.querySelectorAll(".call-row").forEach(row => {
    row.classList.toggle("selected", row.dataset.id === callId);
  });
  detailPanel.innerHTML = '<div class="empty-detail"><p>Đang tải chi tiết...</p></div>';
  try {
    const response = await fetch(`/api/calls/${encodeURIComponent(callId)}`);
    if (!response.ok) throw new Error("Không thể tải chi tiết cuộc gọi");
    renderDetail(await response.json());
  } catch (error) {
    detailPanel.innerHTML = `<div class="error-state">${escapeHtml(error.message)}</div>`;
  }
}

function renderDetail(call) {
  const customer = call.customer;
  const value = text => escapeHtml(text || "Chưa cung cấp");
  const transcript = call.transcript.length
    ? call.transcript.map(item => `
        <div class="message ${item.speaker}">
          <b>${item.speaker === "customer" ? "Khách hàng" : "Trợ lý AI"}</b>
          ${escapeHtml(item.text)}
        </div>`).join("")
    : '<p class="empty-list">Chưa có nội dung hội thoại.</p>';
  detailPanel.innerHTML = `
    <div class="detail-header">
      <div><h3>${value(customer.name || customer.phone || "Khách hàng")}</h3>
      <p>${formatDate(call.started_at)} · ${formatDuration(call.duration_seconds)} · ${escapeHtml(call.provider)}</p></div>
      <span class="badge">${call.direction === "inbound" ? "Cuộc gọi đến" : "Cuộc gọi đi"}</span>
    </div>
    <div class="customer-grid">
      <div class="field"><span>Họ và tên</span><strong>${value(customer.name)}</strong></div>
      <div class="field"><span>Số điện thoại</span><strong>${value(customer.phone)}</strong></div>
      <div class="field wide"><span>Địa chỉ</span><strong>${value(customer.address)}</strong></div>
      <div class="field wide"><span>Nhu cầu</span><strong>${value(customer.need)}</strong></div>
      <div class="field wide"><span>Trạng thái tư vấn</span>
        <strong class="interest-badge ${call.interest_status}">${interestLabel(call.interest_status)}</strong>
      </div>
    </div>
    <h4 class="transcript-title">Nội dung hội thoại</h4>
    <div class="transcript">${transcript}</div>`;
}

document.querySelectorAll(".metric").forEach(button => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".metric").forEach(item => item.classList.remove("active"));
    button.classList.add("active");
    state.direction = button.dataset.direction;
    loadCalls();
  });
});

document.querySelectorAll(".interest-filter").forEach(button => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".interest-filter").forEach(item => item.classList.remove("active"));
    button.classList.add("active");
    state.interest = button.dataset.interest;
    loadCalls();
  });
});

let searchTimer;
document.querySelector("#searchInput").addEventListener("input", event => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.query = event.target.value.trim();
    loadCalls();
  }, 250);
});
document.querySelector("#refreshButton").addEventListener("click", loadCalls);
loadCalls();
