const state = { products: [], editingProductId: null };

const productList = document.querySelector("#productList");
const productForm = document.querySelector("#productForm");
const offerList = document.querySelector("#offerList");
const productFormStatus = document.querySelector("#productFormStatus");
const productPageStatus = document.querySelector("#productPageStatus");

const escapeHtml = (value = "") => String(value).replace(
  /[&<>"']/g,
  char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[char]
);

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error("Không thể tải dữ liệu");
  return response.json();
}

async function writeJson(url, method, body) {
  const response = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Không thể lưu sản phẩm");
  return data;
}

async function postJson(url, body) {
  return writeJson(url, "POST", body);
}

function renderProductList() {
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
      <label class="offer-field offer-active-field"><span>Đang bán</span><input data-offer="active" type="checkbox" ${offer.active !== false ? "checked" : ""}></label>
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
  productForm.reset();
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
  renderProductList();
  document.querySelector("#productName").focus();
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
  renderProductList();
}

function collectOffers() {
  return Array.from(offerList.querySelectorAll(".offer-row")).map(row => ({
    name: row.querySelector('[data-offer="name"]').value.trim(),
    quantity: Number(row.querySelector('[data-offer="quantity"]').value),
    unit_price: Number(row.querySelector('[data-offer="unit_price"]').value),
    total_price: Number(row.querySelector('[data-offer="total_price"]').value),
    shipping_policy: row.querySelector('[data-offer="shipping_policy"]').value.trim(),
    active: row.querySelector('[data-offer="active"]').checked,
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

async function loadProducts({ selectId = null } = {}) {
  const data = await fetchJson("/api/products");
  state.products = data.products || [];
  const selected = state.products.find(product => Number(product.id) === Number(selectId || state.editingProductId))
    || state.products.find(product => product.is_default)
    || state.products[0];
  if (selected) editProduct(selected.id);
  else blankProductForm();
  productPageStatus.textContent = "Đã tải dữ liệu";
}

document.querySelector("#newProductButton").addEventListener("click", blankProductForm);
document.querySelector("#addOfferButton").addEventListener("click", () => {
  const offers = collectOffers();
  offers.push({ name: "", quantity: 1, unit_price: 1, total_price: 1, shipping_policy: "", active: true });
  renderOfferRows(offers);
  offerList.querySelector(".offer-row:last-child input")?.focus();
});

productForm.addEventListener("submit", async event => {
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
    await loadProducts({ selectId: result.product.id });
    productFormStatus.textContent = "Đã lưu sản phẩm. Các cuộc gọi mới sẽ dùng cấu hình này.";
    productFormStatus.className = "form-status success";
  } catch (error) {
    productFormStatus.textContent = error.message;
    productFormStatus.className = "form-status error";
  } finally {
    saveButton.disabled = false;
  }
});

document.querySelector("#setDefaultProductButton").addEventListener("click", async () => {
  if (!state.editingProductId) return;
  productFormStatus.textContent = "Đang đặt sản phẩm mặc định...";
  try {
    const result = await postJson(`/api/products/${state.editingProductId}/default`, {});
    await loadProducts({ selectId: result.product.id });
    productFormStatus.textContent = "Đã cập nhật sản phẩm mặc định.";
    productFormStatus.className = "form-status success";
  } catch (error) {
    productFormStatus.textContent = error.message;
    productFormStatus.className = "form-status error";
  }
});

loadProducts().catch(error => {
  productPageStatus.textContent = "Lỗi tải dữ liệu";
  productList.innerHTML = `<div class="request-state error">${escapeHtml(error.message)}</div>`;
});
