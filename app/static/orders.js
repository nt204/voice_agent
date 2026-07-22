/** Order Fulfillment & Packing Workspace (/admin/orders). */

let allOrders = [];
let allProducts = [];
let activeStatusFilter = "";
let activeProductFilter = "";
let productCounts = {};
let orderStats = {};
let currentPage = 1;
let totalOrders = 0;
let ordersLoading = false;
let searchTimer = null;
const pageSize = 50;

const STATUS_LABELS = {
  draft: "Cần kiểm tra (dữ liệu cũ)",
  missing_info: "Thiếu thông tin",
  ready_to_confirm: "Chờ khách xác nhận",
  confirmed: "Đã xác nhận — chờ đóng gói",
  packed: "Đã đóng gói",
  shipping: "Đang giao hàng",
  completed: "Hoàn thành",
  cancelled: "Đã hủy",
};

const STATUS_TRANSITIONS = {
  draft: ["draft", "missing_info", "ready_to_confirm", "confirmed", "cancelled"],
  missing_info: ["missing_info", "ready_to_confirm", "cancelled"],
  ready_to_confirm: ["missing_info", "ready_to_confirm", "confirmed", "cancelled"],
  confirmed: ["ready_to_confirm", "confirmed", "packed", "cancelled"],
  packed: ["confirmed", "packed", "shipping", "cancelled"],
  shipping: ["packed", "shipping", "completed", "cancelled"],
  completed: ["shipping", "completed"],
  cancelled: ["missing_info", "ready_to_confirm", "cancelled"],
};

const ordersTableBody = document.querySelector("#ordersTableBody");
const orderSearchInput = document.querySelector("#orderSearchInput");
const orderResultCount = document.querySelector("#orderResultCount");
const orderProductTabs = document.querySelector("#orderProductTabs");
const exportOrdersExcel = document.querySelector("#exportOrdersExcel");
const refreshOrdersButton = document.querySelector("#refreshOrdersButton");
const ordersPager = document.querySelector("#ordersPager");
const editOrderModal = document.querySelector("#editOrderModal");
const editOrderId = document.querySelector("#editOrderId");
const editCustomerName = document.querySelector("#editCustomerName");
const editCustomerPhone = document.querySelector("#editCustomerPhone");
const editShippingAddress = document.querySelector("#editShippingAddress");
const editProductName = document.querySelector("#editProductName");
const editQuantity = document.querySelector("#editQuantity");
const editTotalPrice = document.querySelector("#editTotalPrice");
const editStatus = document.querySelector("#editStatus");
const editMissingFields = document.querySelector("#editMissingFields");
const closeEditModalBtn = document.querySelector("#closeEditModalBtn");
const cancelEditOrderBtn = document.querySelector("#cancelEditOrderBtn");
const saveEditOrderBtn = document.querySelector("#saveEditOrderBtn");

function escapeHtml(value) {
  return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function formatPrice(value) {
  return `${Number(value || 0).toLocaleString("en-US")} MMK`;
}

function formatDate(isoString) {
  if (!isoString) return "—";
  const date = new Date(isoString);
  return Number.isNaN(date.getTime())
    ? isoString
    : date.toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  let data = {};
  try {
    data = await response.json();
  } catch {
    data = {};
  }
  if (!response.ok) throw new Error(data.detail || "Yêu cầu không thành công");
  return data;
}

function scopedParams({ paginate = true } = {}) {
  const params = new URLSearchParams();
  if (activeProductFilter === "unassigned") params.set("unassigned", "true");
  else if (activeProductFilter) params.set("product_id", activeProductFilter);
  if (activeStatusFilter) params.set("status", activeStatusFilter);
  const query = (orderSearchInput?.value || "").trim();
  if (query) params.set("q", query);
  if (paginate) {
    params.set("limit", String(pageSize));
    params.set("offset", String((currentPage - 1) * pageSize));
  }
  return params;
}

async function fetchOrders({ silent = false } = {}) {
  if (ordersLoading) return;
  ordersLoading = true;
  if (!silent && ordersTableBody) {
    ordersTableBody.innerHTML = '<tr><td colspan="10" style="text-align:center; padding:24px; color:#64748b;">Đang tải danh sách đơn hàng...</td></tr>';
  }
  try {
    const data = await fetchJson(`/api/orders?${scopedParams()}`);
    allOrders = data.orders || [];
    totalOrders = Number(data.count || 0);
    orderStats = data.stats || {};
    productCounts = data.product_counts || {};
    const lastPage = Math.max(1, Math.ceil(totalOrders / pageSize));
    if (currentPage > lastPage) {
      currentPage = lastPage;
      ordersLoading = false;
      await fetchOrders({ silent });
      return;
    }
    renderProductTabs();
    updateStats();
    renderOrders();
    renderPager();
  } catch (error) {
    if (ordersTableBody) {
      ordersTableBody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding:24px; color:#ef4444;">${escapeHtml(error.message)}</td></tr>`;
    }
  } finally {
    ordersLoading = false;
  }
}

async function fetchProducts() {
  const data = await fetchJson("/api/products");
  allProducts = data.products || [];
  renderProductTabs();
}

function renderProductTabs() {
  if (!orderProductTabs) return;
  const total = Object.values(productCounts).reduce((sum, value) => sum + Number(value || 0), 0);
  const tabs = [
    { id: "", name: "Tất cả sản phẩm", count: total },
    ...allProducts.map(product => ({
      id: String(product.id),
      name: product.name,
      count: Number(productCounts[String(product.id)] || 0),
      active: product.active,
    })),
  ];
  if (Number(productCounts.unassigned || 0) > 0) {
    tabs.push({ id: "unassigned", name: "Chưa phân loại", count: Number(productCounts.unassigned) });
  }
  orderProductTabs.innerHTML = tabs.map(tab => `
    <button class="order-product-tab ${activeProductFilter === tab.id ? "active" : ""}" data-product-filter="${escapeHtml(tab.id)}" type="button" role="tab" aria-selected="${activeProductFilter === tab.id}">
      <span>${escapeHtml(tab.name)}${tab.active === false ? " (tạm ngưng)" : ""}</span><strong>${tab.count}</strong>
    </button>`).join("");
}

function setText(id, value) {
  const element = document.querySelector(`#${id}`);
  if (element) element.textContent = String(value ?? 0);
}

function updateStats() {
  const counts = orderStats.status_counts || {};
  setText("statTotal", orderStats.total_orders || 0);
  setText("statNeedsReview", orderStats.needs_review || 0);
  setText("statReady", orderStats.awaiting_confirmation || 0);
  setText("statConfirmed", orderStats.waiting_to_pack || 0);
  setText("statPacked", counts.packed || 0);
  setText("statShipping", counts.shipping || 0);
  setText("statCompleted", counts.completed || 0);
  setText("statCancelled", counts.cancelled || 0);
  updateExportLink();
}

function updateExportLink() {
  if (!exportOrdersExcel) return;
  const params = scopedParams({ paginate: false });
  const query = params.toString();
  exportOrdersExcel.href = `/api/orders/export.xlsx${query ? `?${query}` : ""}`;
}

function statusOptions(status) {
  const allowed = STATUS_TRANSITIONS[status] || [status];
  return allowed.map(value => `<option value="${value}" ${value === status ? "selected" : ""}>${escapeHtml(STATUS_LABELS[value] || value)}</option>`).join("");
}

function renderOrders() {
  if (!ordersTableBody) return;
  const start = totalOrders ? (currentPage - 1) * pageSize + 1 : 0;
  const end = Math.min(start + allOrders.length - 1, totalOrders);
  if (orderResultCount) orderResultCount.textContent = totalOrders ? `${start}-${end}/${totalOrders} đơn hàng` : "0 đơn hàng";
  if (!allOrders.length) {
    ordersTableBody.innerHTML = '<tr><td colspan="10" style="text-align:center; padding:24px; color:#94a3b8;">Chưa có đơn hàng nào khớp bộ lọc</td></tr>';
    return;
  }
  ordersTableBody.innerHTML = allOrders.map(order => `
    <tr>
      <td><strong>#${order.id}</strong></td>
      <td style="white-space:nowrap; font-size:12px; color:#64748b;">${formatDate(order.created_at)}</td>
      <td><strong>${escapeHtml(order.customer_name || "Chưa có tên")}</strong></td>
      <td><code>${escapeHtml(order.customer_phone || "—")}</code></td>
      <td><div class="order-product-cell"><strong>${escapeHtml(order.product?.name || "Chưa phân loại")}</strong><small>${escapeHtml(order.product_name || "Chưa có gói bán")}</small></div></td>
      <td><strong style="color:#2563eb;">${Number(order.quantity) > 0 ? `x${Number(order.quantity)}` : "—"}</strong></td>
      <td><strong style="color:#16a34a;">${formatPrice(order.total_price)}</strong></td>
      <td style="max-width:220px; word-break:break-word; font-size:12px;">${escapeHtml(order.shipping_address || "Chưa có địa chỉ")}</td>
      <td><select class="status-select" data-order-id="${order.id}" data-current-status="${escapeHtml(order.status)}" style="padding:4px 8px; border-radius:12px; font-weight:600; font-size:11px; border:1px solid #cbd5e1;">${statusOptions(order.status)}</select></td>
      <td><button class="secondary-button edit-order-btn" data-order-id="${order.id}" type="button" style="padding:4px 8px; font-size:12px;">✏️ Sửa</button></td>
    </tr>`).join("");

  document.querySelectorAll(".status-select").forEach(select => {
    select.addEventListener("change", async event => {
      const newStatus = event.target.value;
      if (newStatus === "cancelled" && !window.confirm("Bạn chắc chắn muốn hủy đơn này?")) {
        event.target.value = event.target.dataset.currentStatus;
        return;
      }
      await updateOrder(event.target.dataset.orderId, { status: newStatus });
    });
  });
  document.querySelectorAll(".edit-order-btn").forEach(button => {
    button.addEventListener("click", () => {
      const order = allOrders.find(item => item.id === Number(button.dataset.orderId));
      if (order) openEditModal(order);
    });
  });
}

function renderPager() {
  if (!ordersPager) return;
  const totalPages = Math.max(1, Math.ceil(totalOrders / pageSize));
  ordersPager.innerHTML = `
    <button class="secondary-button" id="ordersPrevPage" type="button" ${currentPage <= 1 ? "disabled" : ""}>← Trước</button>
    <span>Trang ${currentPage}/${totalPages}</span>
    <button class="secondary-button" id="ordersNextPage" type="button" ${currentPage >= totalPages ? "disabled" : ""}>Sau →</button>`;
  document.querySelector("#ordersPrevPage")?.addEventListener("click", () => changePage(currentPage - 1));
  document.querySelector("#ordersNextPage")?.addEventListener("click", () => changePage(currentPage + 1));
}

async function changePage(page) {
  currentPage = Math.max(1, page);
  await fetchOrders();
}

async function updateOrder(orderId, payload) {
  try {
    await fetchJson(`/api/orders/${orderId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    await fetchOrders({ silent: true });
    return true;
  } catch (error) {
    window.alert(`Không thể cập nhật đơn hàng: ${error.message}`);
    await fetchOrders({ silent: true });
    return false;
  }
}

function openEditModal(order) {
  if (!editOrderModal) return;
  editOrderId.value = order.id;
  editCustomerName.value = order.customer_name || "";
  editCustomerPhone.value = order.customer_phone || "";
  editShippingAddress.value = order.shipping_address || "";
  editProductName.value = order.product_name || "";
  editQuantity.value = order.quantity || 1;
  editTotalPrice.value = order.total_price || 0;
  editStatus.innerHTML = statusOptions(order.status);
  editMissingFields.value = Array.isArray(order.missing_fields) ? order.missing_fields.join(", ") : (order.missing_fields || "");
  editOrderModal.style.display = "flex";
}

function closeEditModal() {
  if (editOrderModal) editOrderModal.style.display = "none";
}

orderProductTabs?.addEventListener("click", async event => {
  const button = event.target.closest(".order-product-tab");
  if (!button) return;
  activeProductFilter = button.dataset.productFilter || "";
  currentPage = 1;
  await fetchOrders();
});

document.querySelectorAll(".funnel-item").forEach(item => {
  item.addEventListener("click", async () => {
    document.querySelectorAll(".funnel-item").forEach(button => button.classList.remove("active"));
    item.classList.add("active");
    activeStatusFilter = item.dataset.status || "";
    currentPage = 1;
    await fetchOrders();
  });
});

orderSearchInput?.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    currentPage = 1;
    fetchOrders();
  }, 300);
});
refreshOrdersButton?.addEventListener("click", () => fetchOrders());
closeEditModalBtn?.addEventListener("click", closeEditModal);
cancelEditOrderBtn?.addEventListener("click", closeEditModal);
editOrderModal?.addEventListener("click", event => {
  if (event.target === editOrderModal) closeEditModal();
});

saveEditOrderBtn?.addEventListener("click", async () => {
  const orderId = editOrderId.value;
  if (!orderId) return;
  const payload = {
    customer_name: editCustomerName.value.trim(),
    customer_phone: editCustomerPhone.value.trim(),
    shipping_address: editShippingAddress.value.trim(),
    product_name: editProductName.value.trim(),
    quantity: Number(editQuantity.value),
    total_price: Number(editTotalPrice.value),
    status: editStatus.value,
    missing_fields: editMissingFields.value.trim(),
  };
  if (payload.status === "cancelled" && !window.confirm("Bạn chắc chắn muốn hủy đơn này?")) return;
  saveEditOrderBtn.disabled = true;
  const saved = await updateOrder(orderId, payload);
  saveEditOrderBtn.disabled = false;
  if (saved) closeEditModal();
});

setInterval(() => {
  if (!document.hidden && editOrderModal?.style.display === "none") fetchOrders({ silent: true });
}, 5000);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) fetchOrders({ silent: true });
});

Promise.all([fetchProducts(), fetchOrders()]).catch(error => {
  if (ordersTableBody) ordersTableBody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding:24px; color:#ef4444;">${escapeHtml(error.message)}</td></tr>`;
});
