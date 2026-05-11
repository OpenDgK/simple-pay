const runtimeConfig = window.APP_RUNTIME_CONFIG || {};
const CONTENT_KEYS = [
  "heroBadge",
  "feature1",
  "feature2",
  "feature3",
  "flowTitle",
  "flowIntro",
  "step1Title",
  "step1Body",
  "step2Title",
  "step2Body",
  "step3Title",
  "step3Body",
  "lookupTitle",
  "lookupIntro",
  "faqTitle",
  "faqIntro",
  "faq1Title",
  "faq1Body",
  "faq2Title",
  "faq2Body",
  "faq3Title",
  "faq3Body",
];

const state = {
  apiBase: runtimeConfig.apiBaseUrl || "/api",
  config: null,
  products: [],
  selectedProductId: null,
  adminProducts: [],
  adminInventory: [],
  adminToken: localStorage.getItem("sop_admin_token") || "",
  selectedOrder: null,
};

const $ = (selector) => document.querySelector(selector);

function apiUrl(path) {
  if (path.startsWith("http")) return path;
  const base = state.apiBase.endsWith("/") ? state.apiBase.slice(0, -1) : state.apiBase;
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  if (cleanPath.startsWith("/api/") && base.endsWith("/api")) {
    return `${base}${cleanPath.slice(4)}`;
  }
  if (cleanPath.startsWith("/api/")) return cleanPath;
  return `${base}${cleanPath}`;
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2800);
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.adminToken && options.admin) {
    headers.set("Authorization", `Bearer ${state.adminToken}`);
  }
  const res = await fetch(apiUrl(path), { ...options, headers });
  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    throw new Error(data.detail || `请求失败：${res.status}`);
  }
  return data;
}

function setView(name) {
  document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
  $(`#${name}`).classList.add("active");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function moneyText(cents) {
  const value = Number(cents || 0) / 100;
  return value.toFixed(2);
}

function statusBadge(value) {
  const safe = value || "pending";
  return `<span class="status ${safe}">${safe}</span>`;
}

function emailBadge(order) {
  if (order.email_sent_at) return `<span class="status delivered">sent</span>`;
  if (order.email_error) return `<span class="status failed" title="${escapeHtml(order.email_error)}">failed</span>`;
  return `<span class="status pending">pending</span>`;
}

function selectedProduct() {
  return state.products.find((item) => String(item.id) === String(state.selectedProductId)) || state.products[0] || null;
}

function productStockText(product) {
  const count = Number(product.stock_count || 0);
  return count > 0 ? `库存 ${count}` : "售罄";
}

function applyContent(content = {}) {
  CONTENT_KEYS.forEach((key) => {
    const el = $(`#${key}`);
    if (el && content[key] !== undefined) {
      el.textContent = content[key];
    }
  });
}

function updateHeroProduct() {
  const product = selectedProduct();
  if (!product) return;
  $("#productTitle").textContent = product.name;
  $("#priceText").textContent = product.priceText || moneyText(product.amount_cents);
  $("#currencyText").textContent = product.currency || "CNY";
  document.title = `${product.name} · 在线支付`;
}

function renderProductOptions() {
  const box = $("#productOptions");
  const button = $("#submitOrderBtn");
  if (!state.products.length) {
    box.innerHTML = `<div class="empty-state">暂无可购买商品，请联系管理员。</div>`;
    button.disabled = true;
    return;
  }
  if (!state.selectedProductId || !state.products.some((item) => String(item.id) === String(state.selectedProductId))) {
    state.selectedProductId = (state.products.find((item) => Number(item.stock_count || 0) > 0) || state.products[0]).id;
  }
  const currentProduct = selectedProduct();
  button.disabled = !currentProduct || Number(currentProduct.stock_count || 0) <= 0;
  button.textContent = button.disabled ? "已售罄" : "立即支付";
  box.innerHTML = state.products.map((product) => {
    const checked = String(product.id) === String(state.selectedProductId) ? "checked" : "";
    const disabled = Number(product.stock_count || 0) <= 0 ? "disabled" : "";
    const soldOutClass = disabled ? " sold-out" : "";
    const description = product.description ? `<small>${escapeHtml(product.description)}</small>` : "";
    return `
      <label class="product-card${soldOutClass}">
        <input type="radio" name="product_id" value="${escapeHtml(product.id)}" ${checked} ${disabled} />
        <span>
          <strong>${escapeHtml(product.name)}</strong>
          ${description}
        </span>
        <b>${escapeHtml(product.priceText || moneyText(product.amount_cents))} ${escapeHtml(product.currency || "CNY")}<small>${escapeHtml(productStockText(product))}</small></b>
      </label>
    `;
  }).join("");
  updateHeroProduct();
}

async function loadConfig() {
  state.config = await request("/config");
  state.products = state.config.products || [];
  applyContent(state.config.content || {});
  renderProductOptions();
}

function renderOrderCard(order) {
  const deliveryResult = order.delivery_result
    ? `<p><strong>交付结果：</strong>${escapeHtml(order.delivery_result)}</p>`
    : `<p><strong>交付结果：</strong>暂无，管理员交付后会显示在这里。</p>`;
  return `
    <div class="lookup-card">
      <p><strong>订单号：</strong>${escapeHtml(order.order_no)}</p>
      <p><strong>商品：</strong>${escapeHtml(order.product_name)} · ${escapeHtml(order.amount_text)} ${escapeHtml(order.currency)}</p>
      <p><strong>支付状态：</strong>${statusBadge(order.pay_status)}</p>
      <p><strong>交付状态：</strong>${statusBadge(order.delivery_status)}</p>
      ${deliveryResult}
    </div>
  `;
}

async function handleOrderSubmit(event) {
  event.preventDefault();
  const button = $("#submitOrderBtn");
  button.disabled = true;
  button.textContent = "正在创建订单...";
  try {
    const formData = new FormData(event.currentTarget);
    if (!formData.get("product_id") && state.selectedProductId) {
      formData.set("product_id", state.selectedProductId);
    }
    if (selectedProduct() && Number(selectedProduct().stock_count || 0) <= 0) {
      throw new Error("该商品已售罄");
    }
    const data = await request("/orders", {
      method: "POST",
      body: formData,
    });
    $("#paymentResult").hidden = false;
    $("#createdOrderNo").textContent = data.order_no;
    $("#createdQueryCode").textContent = data.query_code;
    $("#createdPayStatus").textContent = data.pay_status;
    $("#createdTokenUrl").textContent = data.query_token_url;
    renderPayAction(data);
    await loadConfig();
    showToast("订单已生成，请保存查询码");
    $("#paymentResult").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showToast(error.message);
  } finally {
    renderProductOptions();
  }
}

function renderPayAction(order) {
  const area = $("#payActionArea");
  if (order.mock_payment) {
    area.innerHTML = `
      <button id="mockPayNowBtn" class="button primary wide" type="button">模拟支付成功</button>
      <a class="button quiet wide" href="/pay/mock?order_no=${encodeURIComponent(order.order_no)}">打开 Mock 支付页</a>
    `;
    $("#mockPayNowBtn").addEventListener("click", async () => {
      const paid = await request(`/payments/mock/${encodeURIComponent(order.order_no)}?query_code=${encodeURIComponent(order.query_code)}`, {
        method: "POST",
      });
      $("#createdPayStatus").textContent = paid.pay_status;
      if (paid.delivery_result) {
        $("#lookupResult").innerHTML = renderOrderCard(paid);
      }
      await loadConfig();
      showToast("Mock 支付已完成");
    });
    return;
  }
  if (order.pay_body && /^https?:\/\//i.test(order.pay_body)) {
    area.innerHTML = `<a class="button primary wide" href="${escapeHtml(order.pay_body)}" target="_blank" rel="noopener">前往支付页面</a>`;
    return;
  }
  area.innerHTML = `
    <div class="token-box">
      <span>支付参数</span>
      <code>${escapeHtml(order.pay_body || "支付订单已创建，请按支付平台返回内容展示二维码或跳转链接。")}</code>
    </div>
  `;
}

async function handleLookup(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const orderNo = form.order_no.value.trim();
  const queryCode = form.query_code.value.trim();
  try {
    const data = await request(`/orders/lookup?order_no=${encodeURIComponent(orderNo)}&query_code=${encodeURIComponent(queryCode)}`);
    $("#lookupResult").innerHTML = renderOrderCard(data);
  } catch (error) {
    $("#lookupResult").innerHTML = `<div class="lookup-card"><p>${escapeHtml(error.message)}</p></div>`;
  }
}

async function showTokenView(token) {
  setView("tokenView");
  try {
    const data = await request(`/orders/token/${encodeURIComponent(token)}`);
    $("#tokenResult").innerHTML = renderOrderCard(data);
  } catch (error) {
    $("#tokenResult").innerHTML = `<p>${escapeHtml(error.message)}</p>`;
  }
}

function setupMockPayView() {
  const params = new URLSearchParams(location.search);
  const form = $("#mockPayForm");
  form.order_no.value = params.get("order_no") || "";
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const data = await request(
        `/payments/mock/${encodeURIComponent(form.order_no.value.trim())}?query_code=${encodeURIComponent(form.query_code.value.trim())}`,
        { method: "POST" },
      );
      $("#mockPayResult").innerHTML = renderOrderCard(data);
      showToast("支付状态已更新为 paid");
    } catch (error) {
      $("#mockPayResult").innerHTML = `<p>${escapeHtml(error.message)}</p>`;
    }
  }, { once: true });
}

async function handleAdminLogin(event) {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    const data = await request(`${state.config.adminApiPrefix}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: form.username.value, password: form.password.value }),
    });
    state.adminToken = data.token;
    localStorage.setItem("sop_admin_token", state.adminToken);
    renderAdminAuth();
    await loadAdminData();
  } catch (error) {
    showToast(error.message);
  }
}

function renderAdminAuth() {
  const loggedIn = Boolean(state.adminToken);
  $("#adminLoginForm").hidden = loggedIn;
  $("#adminWorkspace").hidden = !loggedIn;
  $("#adminLogoutBtn").hidden = !loggedIn;
}

async function loadOrders() {
  if (!state.adminToken) return;
  const params = new URLSearchParams();
  const q = $("#adminSearchInput").value.trim();
  const payStatus = $("#adminPayStatus").value;
  const deliveryStatus = $("#adminDeliveryStatus").value;
  if (q) params.set("q", q);
  if (payStatus) params.set("pay_status", payStatus);
  if (deliveryStatus) params.set("delivery_status", deliveryStatus);
  const data = await request(`${state.config.adminApiPrefix}/orders?${params.toString()}`, { admin: true });
  const rows = data.items.map((order) => `
    <tr data-order="${escapeHtml(order.order_no)}">
      <td><strong>${escapeHtml(order.order_no)}</strong><br><small>${escapeHtml(order.product_name)}</small></td>
      <td>${escapeHtml(order.contact)}</td>
      <td>${escapeHtml(order.amount_text)} ${escapeHtml(order.currency)}</td>
      <td>${statusBadge(order.pay_status)}</td>
      <td>${statusBadge(order.delivery_status)}</td>
      <td>${emailBadge(order)}</td>
      <td>${order.has_upload ? `<button class="button quiet" data-download="${escapeHtml(order.order_no)}" type="button">下载</button>` : "无"}</td>
      <td>${escapeHtml(order.created_at || "")}</td>
    </tr>
  `).join("");
  $("#ordersTableBody").innerHTML = rows || `<tr><td colspan="8">暂无订单</td></tr>`;
}

async function selectOrder(orderNo) {
  const order = await request(`${state.config.adminApiPrefix}/orders/${encodeURIComponent(orderNo)}`, { admin: true });
  state.selectedOrder = order;
  $("#deliveryForm").hidden = false;
  $("#selectedOrderTitle").textContent = `${order.order_no} · ${order.contact}`;
  const form = $("#deliveryForm");
  form.delivery_status.value = order.delivery_status;
  form.delivery_result.value = order.delivery_result || "";
}

async function handleDeliverySave(event) {
  event.preventDefault();
  if (!state.selectedOrder) return;
  const form = event.currentTarget;
  await request(`${state.config.adminApiPrefix}/orders/${encodeURIComponent(state.selectedOrder.order_no)}/delivery`, {
    method: "PATCH",
    admin: true,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      delivery_status: form.delivery_status.value,
      delivery_result: form.delivery_result.value,
    }),
  });
  showToast("交付结果已保存");
  await loadOrders();
}

async function downloadFile(orderNo) {
  const res = await fetch(apiUrl(`${state.config.adminApiPrefix}/orders/${encodeURIComponent(orderNo)}/file`), {
    headers: { Authorization: `Bearer ${state.adminToken}` },
  });
  if (!res.ok) {
    showToast("文件下载失败");
    return;
  }
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") || "";
  const match = cd.match(/filename\*=UTF-8''([^;]+)|filename="?([^"]+)"?/i);
  const filename = decodeURIComponent(match?.[1] || match?.[2] || `${orderNo}-upload`);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function loadProducts() {
  const data = await request(`${state.config.adminApiPrefix}/products`, { admin: true });
  state.adminProducts = data.items || [];
  renderAdminProducts();
  renderInventoryProductSelect();
}

function renderAdminProducts() {
  const list = $("#productList");
  list.innerHTML = state.adminProducts.map((product) => `
    <button class="admin-list-row" type="button" data-product-id="${escapeHtml(product.id)}">
      <span>
        <strong>${escapeHtml(product.name)}</strong>
        <small>${product.active ? "前台展示" : "已隐藏"} · 可售 ${escapeHtml(product.stock_count || 0)} · 已售 ${escapeHtml(product.stock_sold || 0)} · 排序 ${escapeHtml(product.sort_order)}</small>
      </span>
      <b>${escapeHtml(product.priceText || moneyText(product.amount_cents))} ${escapeHtml(product.currency)}</b>
    </button>
  `).join("") || `<div class="empty-state">暂无商品</div>`;
}

function renderInventoryProductSelect() {
  const select = $("#inventoryProductSelect");
  const current = select.value;
  select.innerHTML = state.adminProducts.map((product) => `
    <option value="${escapeHtml(product.id)}">${escapeHtml(product.name)} · 可售 ${escapeHtml(product.stock_count || 0)}</option>
  `).join("");
  if (current && state.adminProducts.some((product) => String(product.id) === String(current))) {
    select.value = current;
  } else if (state.adminProducts[0]) {
    select.value = state.adminProducts[0].id;
  }
}

async function loadInventory() {
  if (!state.adminToken) return;
  const productId = $("#inventoryProductSelect").value || state.adminProducts[0]?.id;
  if (!productId) {
    $("#inventoryTableBody").innerHTML = `<tr><td colspan="5">请先添加商品</td></tr>`;
    return;
  }
  const data = await request(`${state.config.adminApiPrefix}/inventory?product_id=${encodeURIComponent(productId)}`, { admin: true });
  state.adminInventory = data.items || [];
  renderInventory();
}

function renderInventory() {
  const rows = state.adminInventory.map((item) => `
    <tr>
      <td><strong>${escapeHtml(item.account)}</strong></td>
      <td>${escapeHtml(item.password)}</td>
      <td>${statusBadge(item.status)}</td>
      <td>${item.order_no ? escapeHtml(item.order_no) : "-"}</td>
      <td>
        ${["available", "disabled"].includes(item.status)
          ? `<button class="button quiet" type="button" data-delete-inventory="${escapeHtml(item.id)}">删除</button>`
          : "-"}
      </td>
    </tr>
  `).join("");
  $("#inventoryTableBody").innerHTML = rows || `<tr><td colspan="5">暂无库存</td></tr>`;
}

async function handleInventoryBulkSave(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const productId = $("#inventoryProductSelect").value;
  if (!productId) {
    showToast("请先选择商品");
    return;
  }
  const data = await request(`${state.config.adminApiPrefix}/inventory/bulk`, {
    method: "POST",
    admin: true,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      product_id: Number(productId),
      items_text: form.elements.items_text.value,
    }),
  });
  form.reset();
  showToast(`已导入 ${data.created} 条库存`);
  await loadProducts();
  await loadInventory();
  await loadConfig();
}

async function deleteInventoryItem(itemId) {
  await request(`${state.config.adminApiPrefix}/inventory/${encodeURIComponent(itemId)}`, {
    method: "DELETE",
    admin: true,
  });
  showToast("库存已删除");
  await loadProducts();
  await loadInventory();
  await loadConfig();
}

function resetProductForm() {
  const form = $("#productForm");
  form.reset();
  form.elements.id.value = "";
  form.elements.currency.value = "CNY";
  form.elements.sort_order.value = "100";
  form.elements.active.checked = true;
}

function selectProductForEdit(productId) {
  const product = state.adminProducts.find((item) => String(item.id) === String(productId));
  if (!product) return;
  const form = $("#productForm");
  form.elements.id.value = product.id;
  form.elements.name.value = product.name;
  form.elements.description.value = product.description || "";
  form.elements.amount_cents.value = product.amount_cents;
  form.elements.currency.value = product.currency || "CNY";
  form.elements.sort_order.value = product.sort_order;
  form.elements.active.checked = Boolean(product.active);
}

async function handleProductSave(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const id = form.elements.id.value;
  const payload = {
    name: form.elements.name.value.trim(),
    description: form.elements.description.value.trim() || null,
    amount_cents: Number.parseInt(form.elements.amount_cents.value, 10),
    currency: form.elements.currency.value.trim().toUpperCase() || "CNY",
    active: form.elements.active.checked,
    sort_order: Number.parseInt(form.elements.sort_order.value, 10) || 100,
  };
  const path = id
    ? `${state.config.adminApiPrefix}/products/${encodeURIComponent(id)}`
    : `${state.config.adminApiPrefix}/products`;
  await request(path, {
    method: id ? "PATCH" : "POST",
    admin: true,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  showToast("商品已保存");
  resetProductForm();
  await loadProducts();
  await loadConfig();
}

async function loadContent() {
  const data = await request(`${state.config.adminApiPrefix}/content`, { admin: true });
  const form = $("#contentForm");
  CONTENT_KEYS.forEach((key) => {
    if (form.elements[key]) {
      form.elements[key].value = data.content?.[key] || "";
    }
  });
}

async function handleContentSave(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const content = {};
  CONTENT_KEYS.forEach((key) => {
    content[key] = form.elements[key]?.value || "";
  });
  await request(`${state.config.adminApiPrefix}/content`, {
    method: "PUT",
    admin: true,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  showToast("前台文案已保存");
  await loadConfig();
}

async function loadAdminData() {
  await Promise.all([loadOrders(), loadProducts(), loadContent()]);
  await loadInventory();
}

function setupAdminEvents() {
  $("#adminLoginForm").addEventListener("submit", handleAdminLogin);
  $("#refreshOrdersBtn").addEventListener("click", () => loadOrders().catch((error) => showToast(error.message)));
  $("#adminSearchInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadOrders().catch((error) => showToast(error.message));
  });
  $("#adminPayStatus").addEventListener("change", () => loadOrders().catch((error) => showToast(error.message)));
  $("#adminDeliveryStatus").addEventListener("change", () => loadOrders().catch((error) => showToast(error.message)));
  $("#deliveryForm").addEventListener("submit", handleDeliverySave);
  $("#productForm").addEventListener("submit", (event) => handleProductSave(event).catch((error) => showToast(error.message)));
  $("#inventoryBulkForm").addEventListener("submit", (event) => handleInventoryBulkSave(event).catch((error) => showToast(error.message)));
  $("#inventoryProductSelect").addEventListener("change", () => loadInventory().catch((error) => showToast(error.message)));
  $("#contentForm").addEventListener("submit", (event) => handleContentSave(event).catch((error) => showToast(error.message)));
  $("#newProductBtn").addEventListener("click", resetProductForm);
  $("#adminLogoutBtn").addEventListener("click", () => {
    state.adminToken = "";
    localStorage.removeItem("sop_admin_token");
    renderAdminAuth();
  });
  $("#ordersTableBody").addEventListener("click", (event) => {
    const download = event.target.closest("[data-download]");
    if (download) {
      event.stopPropagation();
      downloadFile(download.dataset.download);
      return;
    }
    const row = event.target.closest("tr[data-order]");
    if (row) selectOrder(row.dataset.order).catch((error) => showToast(error.message));
  });
  $("#productList").addEventListener("click", (event) => {
    const row = event.target.closest("[data-product-id]");
    if (row) selectProductForEdit(row.dataset.productId);
  });
  $("#inventoryTableBody").addEventListener("click", (event) => {
    const button = event.target.closest("[data-delete-inventory]");
    if (button) deleteInventoryItem(button.dataset.deleteInventory).catch((error) => showToast(error.message));
  });
}

function route() {
  const path = location.pathname;
  if (state.config && path === state.config.adminPanelPath) {
    setView("adminView");
    renderAdminAuth();
    if (state.adminToken) loadAdminData().catch(() => renderAdminAuth());
    return;
  }
  if (path.startsWith("/order/")) {
    showTokenView(path.split("/").filter(Boolean)[1]);
    return;
  }
  if (path === "/pay/mock") {
    setView("mockPayView");
    setupMockPayView();
    return;
  }
  setView("homeView");
}

async function boot() {
  try {
    await loadConfig();
  } catch (error) {
    showToast(error.message);
  }
  $("#productOptions").addEventListener("change", (event) => {
    if (event.target.name === "product_id") {
      state.selectedProductId = event.target.value;
      renderProductOptions();
    }
  });
  $("#orderForm").addEventListener("submit", handleOrderSubmit);
  $("#lookupForm").addEventListener("submit", handleLookup);
  setupAdminEvents();
  route();
}

boot();
