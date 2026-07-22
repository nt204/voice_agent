/**
 * JavaScript for Order Fulfillment & Packing Workspace (/admin/orders)
 */

let allOrders = [];
let allProducts = [];
let activeStatusFilter = "";
let activeProductFilter = "";

const ordersTableBody = document.querySelector("#ordersTableBody");
const orderSearchInput = document.querySelector("#orderSearchInput");
const orderResultCount = document.querySelector("#orderResultCount");
const orderProductTabs = document.querySelector("#orderProductTabs");
const exportOrdersCsv = document.querySelector("#exportOrdersCsv");
const editOrderModal = document.querySelector("#editOrderModal");
const editOrderForm = document.querySelector("#editOrderForm");
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

const statTotal = document.querySelector("#statTotal");
const statConfirmed = document.querySelector("#statConfirmed");
const statPacked = document.querySelector("#statPacked");
const statShipping = document.querySelector("#statShipping");
const statCompleted = document.querySelector("#statCompleted");
const statCancelled = document.querySelector("#statCancelled");

function escapeHtml(str) {
  if (!str) return "";
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function formatPrice(val) {
  if (!val) return "0 MMK";
  return Number(val).toLocaleString("en-US") + " MMK";
}

function formatDate(isoStr) {
  if (!isoStr) return "—";
  try {
    const d = new Date(isoStr);
    return d.toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return isoStr;
  }
}

async function fetchOrders() {
  try {
    const res = await fetch("/api/orders?limit=500");
    const data = await res.json();
    if (data.ok) {
      allOrders = data.orders || [];
      updateStats();
      renderOrders();
    }
  } catch (err) {
    if (ordersTableBody) {
      ordersTableBody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding: 24px; color: #ef4444;">Lỗi khi tải danh sách đơn hàng: ${escapeHtml(err.message)}</td></tr>`;
    }
  }
}

async function fetchProducts() {
  try {
    const res = await fetch("/api/products");
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Không thể tải sản phẩm");
    allProducts = data.products || [];
    renderProductTabs();
  } catch (err) {
    if (orderProductTabs) {
      orderProductTabs.innerHTML = `<span class="order-product-load-error">${escapeHtml(err.message)}</span>`;
    }
  }
}

function orderProductKey(order) {
  return order.product_id == null ? "unassigned" : String(order.product_id);
}

function ordersForActiveProduct() {
  if (!activeProductFilter) return allOrders;
  return allOrders.filter(order => orderProductKey(order) === activeProductFilter);
}

function renderProductTabs() {
  if (!orderProductTabs) return;
  const counts = new Map();
  for (const order of allOrders) {
    const key = orderProductKey(order);
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  const tabs = [
    { id: "", name: "Tất cả sản phẩm", count: allOrders.length },
    ...allProducts.map(product => ({
      id: String(product.id),
      name: product.name,
      count: counts.get(String(product.id)) || 0,
      active: product.active,
    })),
  ];
  if (counts.get("unassigned")) {
    tabs.push({ id: "unassigned", name: "Chưa phân loại", count: counts.get("unassigned") });
  }
  orderProductTabs.innerHTML = tabs.map(tab => `
    <button class="order-product-tab ${activeProductFilter === tab.id ? "active" : ""}" data-product-filter="${escapeHtml(tab.id)}" type="button" role="tab" aria-selected="${activeProductFilter === tab.id}">
      <span>${escapeHtml(tab.name)}${tab.active === false ? " (tạm ngưng)" : ""}</span>
      <strong>${tab.count}</strong>
    </button>
  `).join("");
}

function updateExportLink() {
  if (!exportOrdersCsv) return;
  const params = new URLSearchParams();
  if (activeProductFilter === "unassigned") params.set("unassigned", "true");
  else if (activeProductFilter) params.set("product_id", activeProductFilter);
  const query = params.toString();
  exportOrdersCsv.href = `/api/orders/export${query ? `?${query}` : ""}`;
}

function updateStats() {
  const scopedOrders = ordersForActiveProduct();
  if (statTotal) statTotal.textContent = scopedOrders.length;
  if (statConfirmed) statConfirmed.textContent = scopedOrders.filter(o => o.status === "confirmed" || o.status === "draft").length;
  if (statPacked) statPacked.textContent = scopedOrders.filter(o => o.status === "packed").length;
  if (statShipping) statShipping.textContent = scopedOrders.filter(o => o.status === "shipping").length;
  if (statCompleted) statCompleted.textContent = scopedOrders.filter(o => o.status === "completed").length;
  if (statCancelled) statCancelled.textContent = scopedOrders.filter(o => o.status === "cancelled").length;
  updateExportLink();
}

function renderOrders() {
  if (!ordersTableBody) return;
  const q = (orderSearchInput?.value || "").trim().toLowerCase();

  const filtered = ordersForActiveProduct().filter(o => {
    if (activeStatusFilter === "confirmed") {
      if (o.status !== "confirmed" && o.status !== "draft") return false;
    } else if (activeStatusFilter && o.status !== activeStatusFilter) {
      return false;
    }

    if (q) {
      const match = (
        (o.customer_name || "").toLowerCase().includes(q) ||
        (o.customer_phone || "").toLowerCase().includes(q) ||
        (o.shipping_address || "").toLowerCase().includes(q) ||
        (o.product_name || "").toLowerCase().includes(q)
      );
      if (!match) return false;
    }
    return true;
  });

  if (orderResultCount) orderResultCount.textContent = `${filtered.length} đơn hàng`;

  if (filtered.length === 0) {
    ordersTableBody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding: 24px; color: #94a3b8;">Chưa có đơn hàng nào khớp bộ lọc</td></tr>`;
    return;
  }

  ordersTableBody.innerHTML = filtered.map(o => {
    const productGroupName = o.product?.name || "Chưa phân loại";
    const offerName = o.product_name || "Chưa có gói bán";
    let statusBadge = `<select class="status-select" data-order-id="${o.id}" style="padding: 4px 8px; border-radius: 12px; font-weight: 600; font-size: 11px; border: 1px solid #cbd5e1;">
      <option value="draft" ${o.status === "draft" ? "selected" : ""}>Chờ đóng gói</option>
      <option value="confirmed" ${o.status === "confirmed" ? "selected" : ""}>Chờ đóng gói (Confirmed)</option>
      <option value="packed" ${o.status === "packed" ? "selected" : ""}>Đã đóng gói</option>
      <option value="shipping" ${o.status === "shipping" ? "selected" : ""}>Đang giao hàng</option>
      <option value="completed" ${o.status === "completed" ? "selected" : ""}>Hoàn thành</option>
      <option value="cancelled" ${o.status === "cancelled" ? "selected" : ""}>Đã hủy</option>
    </select>`;

    return `
      <tr>
        <td><strong>#${o.id}</strong></td>
        <td style="white-space: nowrap; font-size: 12px; color: #64748b;">${formatDate(o.created_at)}</td>
        <td><strong>${escapeHtml(o.customer_name || "Chưa có tên")}</strong></td>
        <td><code>${escapeHtml(o.customer_phone || "—")}</code></td>
        <td><div class="order-product-cell"><strong>${escapeHtml(productGroupName)}</strong><small>${escapeHtml(offerName)}</small></div></td>
        <td><strong style="color: #2563eb;">${Number(o.quantity) > 0 ? `x${Number(o.quantity)}` : "—"}</strong></td>
        <td><strong style="color: #16a34a;">${formatPrice(o.total_price)}</strong></td>
        <td style="max-width: 220px; word-break: break-word; font-size: 12px;">${escapeHtml(o.shipping_address || "Chưa có địa chỉ")}</td>
        <td>${statusBadge}</td>
        <td>
          <button class="secondary-button edit-order-btn" data-order-id="${o.id}" type="button" style="padding: 4px 8px; font-size: 12px;">✏️ Sửa</button>
        </td>
      </tr>
    `;
  }).join("");

  // Attach status change listeners
  document.querySelectorAll(".status-select").forEach(sel => {
    sel.addEventListener("change", async (e) => {
      const orderId = e.target.dataset.orderId;
      const newStatus = e.target.value;
      await updateOrderStatus(orderId, { status: newStatus });
    });
  });

  // Attach edit button listeners
  document.querySelectorAll(".edit-order-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const orderId = Number(btn.dataset.orderId);
      const order = allOrders.find(o => o.id === orderId);
      if (order) openEditModal(order);
    });
  });
}

orderProductTabs?.addEventListener("click", event => {
  const button = event.target.closest(".order-product-tab");
  if (!button) return;
  activeProductFilter = button.dataset.productFilter || "";
  renderProductTabs();
  updateStats();
  renderOrders();
});

async function updateOrderStatus(orderId, payload) {
  try {
    const res = await fetch(`/api/orders/${orderId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.ok) {
      const idx = allOrders.findIndex(o => o.id === Number(orderId));
      if (idx !== -1) allOrders[idx] = data.order;
      updateStats();
      renderOrders();
    }
  } catch (err) {
    alert("Không thể cập nhật đơn hàng: " + err.message);
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
  editStatus.value = order.status || "confirmed";
  editMissingFields.value = order.missing_fields || "";
  editOrderModal.style.display = "flex";
}

function closeEditModal() {
  if (editOrderModal) editOrderModal.style.display = "none";
}

closeEditModalBtn?.addEventListener("click", closeEditModal);
cancelEditOrderBtn?.addEventListener("click", closeEditModal);
editOrderModal?.addEventListener("click", (e) => {
  if (e.target === editOrderModal) closeEditModal();
});

saveEditOrderBtn?.addEventListener("click", async () => {
  const orderId = editOrderId.value;
  if (!orderId) return;

  const payload = {
    customer_name: editCustomerName.value.trim(),
    customer_phone: editCustomerPhone.value.trim(),
    shipping_address: editShippingAddress.value.trim(),
    product_name: editProductName.value.trim(),
    quantity: Number(editQuantity.value) || 1,
    total_price: Number(editTotalPrice.value) || 0,
    status: editStatus.value,
    missing_fields: editMissingFields.value.trim(),
  };

  saveEditOrderBtn.disabled = true;
  await updateOrderStatus(orderId, payload);
  saveEditOrderBtn.disabled = false;
  closeEditModal();
});

// Funnel item filter click listeners
document.querySelectorAll(".funnel-item").forEach(item => {
  item.addEventListener("click", () => {
    document.querySelectorAll(".funnel-item").forEach(i => i.classList.remove("active"));
    item.classList.add("active");
    activeStatusFilter = item.dataset.status || "";
    renderOrders();
  });
});

orderSearchInput?.addEventListener("input", renderOrders);

// Initial fetch
Promise.all([fetchProducts(), fetchOrders()]).then(() => {
  renderProductTabs();
  updateStats();
  renderOrders();
});
