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
];

const state = {
  apiBase: runtimeConfig.apiBaseUrl || "/api",
  config: null,
  products: [],
  selectedProductId: null,
  adminProducts: [],
  adminInventory: [],
  adminToken: localStorage.getItem("sop_admin_token") || "",
  adminOrderCategory: "attention",
  ordersCollapsed: false,
  selectedOrder: null,
  checkoutTimer: null,
  paymentOrder: null,
  paymentUrl: "",
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
  return `<span class="status ${safe}">${escapeHtml(statusText(safe))}</span>`;
}

function emailBadge(order) {
  if (order.email_sent_at && !order.email_error) return `<span class="status delivered">已发送</span>`;
  if (order.email_error) return `<span class="status failed" title="${escapeHtml(order.email_error)}">发送失败</span>`;
  return `<span class="status pending">未发送</span>`;
}

const STATUS_TEXT = {
  pending: "未付款",
  reviewing: "待人工确认",
  paid: "已支付",
  failed: "支付失败",
  expired: "已过期",
  processing: "处理中",
  delivered: "已发货",
  cancelled: "已取消",
  available: "可售",
  reserved: "已锁定",
  sold: "已售出",
  disabled: "已停售",
};

function statusText(value) {
  return STATUS_TEXT[value] || value || "未付款";
}

function setStatusText(selector, value) {
  const el = $(selector);
  if (el) el.textContent = statusText(value);
}

function selectedProduct() {
  return state.products.find((item) => String(item.id) === String(state.selectedProductId)) || null;
}

function ensureSelectedProduct() {
  if (!state.products.length) return null;
  const current = selectedProduct();
  if (current) return current;
  const next = state.products.find((item) => Number(item.stock_count || 0) > 0) || state.products[0];
  state.selectedProductId = next.id;
  return next;
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
  const product = ensureSelectedProduct();
  if (!product) return;
  $("#productTitle").textContent = product.name;
  $("#priceText").textContent = product.priceText || moneyText(product.amount_cents);
  $("#currencyText").textContent = product.currency || "CNY";
  document.title = state.products.length > 1 ? "PLUS / Team · 在线支付" : `${product.name} · 在线支付`;
}

function setCheckoutNotice(html) {
  const notice = $("#checkoutNotice");
  notice.innerHTML = html;
  notice.hidden = false;
}

function clearCheckoutTimer() {
  if (state.checkoutTimer) {
    window.clearInterval(state.checkoutTimer);
    state.checkoutTimer = null;
  }
}

function openPaymentModal(url, order = null) {
  const modal = $("#paymentModal");
  const qrImage = $("#paymentQrImage");
  if (!modal || !qrImage || !url) return false;
  state.paymentUrl = url;
  if (order) state.paymentOrder = order;
  qrImage.src = apiUrl(`/payments/qr?data=${encodeURIComponent(url)}`);
  modal.hidden = false;
  document.body.classList.add("payment-open");
  return true;
}

function closePaymentModal(options = {}) {
  const modal = $("#paymentModal");
  const qrImage = $("#paymentQrImage");
  if (modal) modal.hidden = true;
  if (qrImage && options.clearFrame !== false) qrImage.removeAttribute("src");
  document.body.classList.remove("payment-open");
}

function openAfterPayNoticeModal() {
  const modal = $("#afterPayNoticeModal");
  if (!modal) return;
  setAfterPayNoticePanel("migration");
  modal.hidden = false;
  document.body.classList.add("notice-open");
}

function closeAfterPayNoticeModal() {
  const modal = $("#afterPayNoticeModal");
  if (modal) modal.hidden = true;
  document.body.classList.remove("notice-open");
}

function setAfterPayNoticePanel(key) {
  const modal = $("#afterPayNoticeModal");
  if (!modal) return;
  modal.querySelectorAll(".notice-tab").forEach((tab) => {
    const active = tab.dataset.noticeKey === key;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  modal.querySelectorAll(".notice-panel").forEach((panel) => {
    const active = panel.dataset.noticeKey === key;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
}

function productPlanLabel(product) {
  const name = String(product.name || "");
  return name ? `${name} 套餐` : "可购买套餐";
}

function productTabLabel(product) {
  const name = String(product.name || "").trim();
  return name || "套餐";
}

function productIntro(product) {
  if (product.description) return product.description;
  const name = String(product.name || "");
  return `购买 ${name || "该商品"} 后，系统会把库存账号密码自动发送到你的邮箱。`;
}

function productFeatures(product) {
  const name = String(product.name || "");
  const plan = name || "一月套餐";
  return [plan, "支付完成自动发货", "邮箱接收账号密码"];
}

function submitButtonText(product) {
  return Number(product.stock_count || 0) > 0 ? `购买 ${product.name}` : "已售罄";
}

function assignedInventoryText(order) {
  const item = order.inventory_item;
  if (!item) return "未分配";
  return item.account || `库存 #${item.id}`;
}

function renderAssignedInventory(order) {
  const item = order.inventory_item;
  if (!item) {
    return `
      <div class="assigned-inventory-card muted">
        <strong>本单发货账号</strong>
        <p>暂未分配库存。订单支付成功后，系统会自动锁定并记录发货账号。</p>
      </div>
    `;
  }
  return `
    <div class="assigned-inventory-card">
      <strong>本单发货账号</strong>
      <dl>
        <div><dt>账号</dt><dd>${escapeHtml(item.account)}</dd></div>
        <div><dt>密码</dt><dd>${escapeHtml(item.password)}</dd></div>
        <div><dt>库存状态</dt><dd>${statusBadge(item.status)}</dd></div>
        <div><dt>售出时间</dt><dd>${escapeHtml(formatDateTime(item.sold_at) || "未售出")}</dd></div>
      </dl>
    </div>
  `;
}

function renderProductTabs() {
  const tabs = $("#productTabs");
  if (!tabs) return;
  if (!state.products.length) {
    tabs.innerHTML = "";
    return;
  }
  const currentProduct = ensureSelectedProduct();
  tabs.innerHTML = state.products.map((product) => {
    const isActive = currentProduct && String(product.id) === String(currentProduct.id);
    const soldOut = Number(product.stock_count || 0) <= 0;
    const soldOutBadge = soldOut ? `<span class="tab-sold-out">已售罄</span>` : "";
    return `
      <button
        class="product-tab${isActive ? " active" : ""}"
        type="button"
        role="tab"
        aria-selected="${isActive ? "true" : "false"}"
        data-product-id="${escapeHtml(product.id)}"
      >
        <span>${escapeHtml(productTabLabel(product))}</span>
        ${soldOutBadge}
      </button>
    `;
  }).join("");
  tabs.querySelectorAll(".product-tab").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedProductId = button.dataset.productId;
      renderProductCards();
    });
  });
}

function renderProductCards() {
  const box = $("#productCards");
  if (!box) return;
  if (!state.products.length) {
    box.innerHTML = `<div class="empty-state">暂无可购买商品，请联系管理员。</div>`;
    renderProductTabs();
    return;
  }
  const product = ensureSelectedProduct();
  renderProductTabs();
  const soldOut = Number(product.stock_count || 0) <= 0;
  const disabled = soldOut ? "disabled" : "";
  const soldOutClass = soldOut ? " sold-out" : "";
  box.innerHTML = `
    <form class="product-buy-card hero-card${soldOutClass}" data-product-id="${escapeHtml(product.id)}" enctype="multipart/form-data">
      <input type="hidden" name="product_id" value="${escapeHtml(product.id)}" />
      <div class="purchase-summary">
        <span class="product-plan-badge">${escapeHtml(productPlanLabel(product))}</span>
        <strong>${escapeHtml(product.name)}</strong>
        <small>${escapeHtml(productStockText(product))}</small>
      </div>
      <label>
        邮箱
        <input name="contact" type="email" maxlength="255" placeholder="you@example.com" required ${disabled} />
      </label>
      <button class="button primary wide" type="submit" ${disabled}>${escapeHtml(submitButtonText(product))}</button>
    </form>
  `;
  box.querySelectorAll(".product-buy-card").forEach((form) => {
    form.addEventListener("submit", handleOrderSubmit);
  });
  updateHeroProduct();
}

async function loadConfig() {
  state.config = await request("/config");
  state.products = state.config.products || [];
  applyContent(state.config.content || {});
  renderProductCards();
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
  const form = event.currentTarget;
  const button = form.querySelector("button[type='submit']");
  const productId = form.dataset.productId || new FormData(form).get("product_id");
  const product = state.products.find((item) => String(item.id) === String(productId));
  const defaultButtonText = product ? submitButtonText(product) : "立即支付";
  button.disabled = true;
  button.textContent = "正在创建订单...";
  try {
    if (!productId) {
      throw new Error("请选择商品");
    }
    if (product && Number(product.stock_count || 0) <= 0) {
      throw new Error("该商品已售罄");
    }
    const formData = new FormData(form);
    formData.set("product_id", productId);
    const data = await request("/orders", {
      method: "POST",
      body: formData,
    });
    launchCheckout(data);
    await loadConfig();
    showToast(data.mock_payment ? "订单已生成，可进行本地测试" : data.pay_channel === "manual" ? "请扫码付款，付款后提交确认" : "支付窗口已在当前页面打开");
  } catch (error) {
    closePaymentModal();
    showToast(error.message);
  } finally {
    if (button.isConnected) {
      button.disabled = product ? Number(product.stock_count || 0) <= 0 : false;
      button.textContent = defaultButtonText;
    }
    renderProductCards();
  }
}

function launchCheckout(order) {
  clearCheckoutTimer();
  if (order.mock_payment) {
    renderMockCheckout(order);
    return;
  }
  if (order.pay_channel === "manual") {
    renderManualCheckout(order);
    return;
  }

  const paymentUrl = order.pay_body && /^https?:\/\//i.test(order.pay_body) ? order.pay_body : "";
  const modalOpened = paymentUrl ? openPaymentModal(paymentUrl, order) : false;

  const popupText = modalOpened
    ? "支付窗口已在当前页面打开，请在里面完成付款。"
    : "支付窗口暂未打开，请点击下方按钮继续支付。";
  const fallbackAction = paymentUrl
    ? `<button id="reopenPaymentBtn" class="button primary wide" type="button">打开支付窗口</button>`
    : `<div class="token-box"><span>支付参数</span><code>${escapeHtml(order.pay_body || "支付订单已创建，请稍后重试。")}</code></div>`;
  const syncButton = `<button id="inlineSyncPayBtn" class="button secondary wide" type="button">我已完成支付，刷新状态</button>`;

  setCheckoutNotice(`
    <div class="checkout-state">
      <strong>${popupText}</strong>
      <span>请不要关闭本页面。系统会自动检查支付状态，确认后关闭支付窗口并发送账号密码到邮箱。</span>
      ${fallbackAction}
      ${syncButton}
    </div>
  `);

  $("#reopenPaymentBtn")?.addEventListener("click", () => {
    const reopened = openPaymentModal(paymentUrl, order);
    if (!reopened) {
      showToast("支付窗口打开失败，请刷新后重试");
    }
  });
  $("#inlineSyncPayBtn")?.addEventListener("click", () => {
    syncExternalPayment(order).catch((error) => showToast(error.message));
  });
  startExternalPaymentWatcher(order);
}

function parsePaymentPayload(order) {
  try {
    return JSON.parse(order.pay_body || "{}");
  } catch {
    return { instructions: order.pay_body || "" };
  }
}

function manualPaymentMarkup(order) {
  const payload = parsePaymentPayload(order);
  const qr = payload.qr_url
    ? `<img class="payment-qr" src="${escapeHtml(payload.qr_url)}" alt="收款码" />`
    : `<div class="empty-state">收款码未配置，请联系管理员。</div>`;
  return `
    <div class="checkout-state manual">
      <strong>扫码付款后等待人工确认</strong>
      <span>${escapeHtml(payload.instructions || "请扫码付款，付款后点击下方按钮。")}</span>
      <div class="manual-payment-box">
        ${qr}
        <div class="manual-payment-meta">
          <p><strong>订单号：</strong>${escapeHtml(order.order_no)}</p>
          <p><strong>金额：</strong>${escapeHtml(order.amount_text)} ${escapeHtml(order.currency)}</p>
        </div>
      </div>
      <button class="button primary wide manualPaidBtn" type="button">我已付款，等待确认</button>
    </div>
  `;
}

function manualSubmittedMarkup(order) {
  return `
    <div class="checkout-state warning">
      <strong>已提交，等待管理员确认收款。</strong>
      <span>管理员会尽快核对收款，10 分钟内发货。账号密码会自动发送到你的邮箱。</span>
      <div class="manual-payment-meta">
        <p><strong>订单号：</strong>${escapeHtml(order.order_no)}</p>
      </div>
    </div>
  `;
}

function bindManualPaymentButtons(order, root) {
  root.querySelectorAll(".manualPaidBtn").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "正在提交确认...";
      try {
        await submitManualPayment(order);
      } catch (error) {
        button.disabled = false;
        button.textContent = "我已付款，等待确认";
        showToast(error.message);
      }
    });
  });
}

async function submitManualPayment(order) {
    const reviewing = await request(`/payments/manual/${encodeURIComponent(order.order_no)}?query_code=${encodeURIComponent(order.query_code)}`, {
      method: "POST",
    });
    const submitted = manualSubmittedMarkup(order);
    const notice = $("#checkoutNotice");
    const actionArea = $("#payActionArea");
    if (notice && !notice.hidden) notice.innerHTML = submitted;
    if (actionArea) actionArea.innerHTML = submitted;
    setStatusText("#createdPayStatus", reviewing.pay_status);
    if ($("#lookupResult")) $("#lookupResult").innerHTML = renderOrderCard(reviewing);
    await loadConfig();
    showToast("已提交付款确认，等待管理员处理");
}

function renderManualCheckout(order) {
  setCheckoutNotice(manualPaymentMarkup(order));
  bindManualPaymentButtons(order, $("#checkoutNotice"));
}

function renderMockCheckout(order) {
  setCheckoutNotice(`
    <div class="checkout-state">
      <strong>本地 Mock 支付测试</strong>
      <span>真实环境会直接打开支付窗口，本地可用下面按钮模拟支付成功。</span>
      <button id="inlineMockPayBtn" class="button primary wide" type="button">模拟支付成功</button>
    </div>
  `);
  $("#inlineMockPayBtn").addEventListener("click", async () => {
    const paid = await request(`/payments/mock/${encodeURIComponent(order.order_no)}?query_code=${encodeURIComponent(order.query_code)}`, {
      method: "POST",
    });
    setCheckoutPaid(paid);
    await loadConfig();
  });
}

function setCheckoutPaid(order) {
  clearCheckoutTimer();
  closePaymentModal();
  setCheckoutNotice(`
    <div class="checkout-state success">
      <strong>支付已确认，账号密码已发送到邮箱。</strong>
      <span>如果邮件没有立即收到，请先检查垃圾邮件，或点击右下角客服按钮联系我们。</span>
    </div>
  `);
  if (order.delivery_result && $("#lookupResult")) {
    $("#lookupResult").innerHTML = renderOrderCard(order);
  }
  openAfterPayNoticeModal();
  showToast("支付已确认，已自动发货");
}

async function syncEzbotiPayment(order, options = {}) {
  const checked = await request(`/payments/ezboti/sync/${encodeURIComponent(order.order_no)}?query_code=${encodeURIComponent(order.query_code)}`, {
    method: "POST",
  });
  if (checked.pay_status === "paid") {
    setCheckoutPaid(checked);
    await loadConfig();
  } else if (!options.quiet) {
    showToast("暂未检测到支付成功，请稍后再试");
  }
  return checked;
}

async function syncLookupPayment(order, options = {}) {
  const checked = await request(`/orders/lookup?order_no=${encodeURIComponent(order.order_no)}&query_code=${encodeURIComponent(order.query_code)}`);
  if (checked.pay_status === "paid") {
    setCheckoutPaid(checked);
    await loadConfig();
  } else if (["failed", "expired"].includes(checked.pay_status)) {
    clearCheckoutTimer();
    setCheckoutNotice(`
      <div class="checkout-state warning">
        <strong>暂未确认付款。</strong>
        <span>如果你已经完成付款，请联系右下角客服核对订单。订单号：${escapeHtml(checked.order_no)}</span>
      </div>
    `);
  } else if (!options.quiet) {
    showToast("正在等待支付平台确认，请稍后刷新");
  }
  return checked;
}

function syncExternalPayment(order, options = {}) {
  if (order.pay_channel === "ezboti") {
    return syncEzbotiPayment(order, options);
  }
  return syncLookupPayment(order, options);
}

async function cancelPendingOrder(order) {
  const cancelled = await request(`/orders/${encodeURIComponent(order.order_no)}/cancel?query_code=${encodeURIComponent(order.query_code)}`, {
    method: "POST",
  });
  if (cancelled.pay_status === "paid") {
    setCheckoutPaid(cancelled);
    return;
  }
  clearCheckoutTimer();
  setCheckoutNotice(`
    <div class="checkout-state warning">
      <strong>未检测到支付成功，库存已释放。</strong>
      <span>如你已经完成付款，请联系管理员核对订单。</span>
    </div>
  `);
  await loadConfig();
}

function startExternalPaymentWatcher(order) {
  let attempts = 0;
  let checking = false;
  state.checkoutTimer = window.setInterval(async () => {
    if (checking) return;
    attempts += 1;
    checking = true;
    try {
      const checked = await syncExternalPayment(order, { quiet: true });
      if (checked.pay_status === "paid") return;
      if (attempts >= 120) {
        clearCheckoutTimer();
        setCheckoutNotice(`
          <div class="checkout-state warning">
            <strong>还没有收到支付平台确认。</strong>
            <span>如果你已经付款，稍后会自动发货到邮箱；也可以联系右下角客服核对。</span>
          </div>
        `);
      }
    } catch (error) {
      showToast(error.message);
    } finally {
      checking = false;
    }
  }, 5000);
}

function renderPayAction(order) {
  const area = $("#payActionArea");
  if (!area) return;
  if (order.mock_payment) {
    area.innerHTML = `
      <button id="mockPayNowBtn" class="button primary wide" type="button">模拟支付成功</button>
      <a class="button quiet wide" href="/pay/mock?order_no=${encodeURIComponent(order.order_no)}">打开 Mock 支付页</a>
    `;
    $("#mockPayNowBtn").addEventListener("click", async () => {
      const paid = await request(`/payments/mock/${encodeURIComponent(order.order_no)}?query_code=${encodeURIComponent(order.query_code)}`, {
        method: "POST",
      });
      setStatusText("#createdPayStatus", paid.pay_status);
      if (paid.delivery_result && $("#lookupResult")) {
        $("#lookupResult").innerHTML = renderOrderCard(paid);
      }
      await loadConfig();
      showToast("Mock 支付已完成");
    });
    return;
  }
  if (order.pay_channel === "manual") {
    area.innerHTML = manualPaymentMarkup(order);
    bindManualPaymentButtons(order, area);
    return;
  }
  if (order.pay_body && /^https?:\/\//i.test(order.pay_body)) {
    area.innerHTML = `
      <button id="tokenOpenPayBtn" class="button primary wide" type="button">打开支付窗口</button>
      <button id="externalSyncPayBtn" class="button quiet wide" type="button">我已支付，检查支付状态</button>
    `;
    $("#tokenOpenPayBtn").addEventListener("click", () => openPaymentModal(order.pay_body, order));
    $("#externalSyncPayBtn").addEventListener("click", async () => {
      const checked = await syncExternalPayment(order);
      setStatusText("#createdPayStatus", checked.pay_status);
      if ($("#lookupResult")) $("#lookupResult").innerHTML = renderOrderCard(checked);
    });
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

function renderTokenResult(order) {
  let hint = `<div class="checkout-state warning"><strong>正在等待支付平台确认。</strong><span>如果你已经完成付款，请保持此页打开；确认后会自动发货到邮箱。</span></div>`;
  if (order.pay_status === "paid") {
    hint = `<div class="checkout-state success"><strong>支付已确认。</strong><span>账号密码会发送到你填写的邮箱，请留意收件箱和垃圾邮件。</span></div>`;
  } else if (["failed", "expired"].includes(order.pay_status)) {
    hint = `<div class="checkout-state warning"><strong>暂未确认付款。</strong><span>如果你已经完成付款，请联系右下角客服核对订单。订单号：${escapeHtml(order.order_no)}</span></div>`;
  }
  return `${hint}${renderOrderCard(order)}`;
}

function startTokenWatcher(token) {
  let attempts = 0;
  let checking = false;
  clearCheckoutTimer();
  state.checkoutTimer = window.setInterval(async () => {
    if (checking) return;
    attempts += 1;
    checking = true;
    try {
      const data = await request(`/orders/token/${encodeURIComponent(token)}`);
      $("#tokenResult").innerHTML = renderTokenResult(data);
      if (data.pay_status === "paid") {
        clearCheckoutTimer();
        showToast("支付已确认，已自动发货");
      } else if (["failed", "expired"].includes(data.pay_status) || attempts >= 120) {
        clearCheckoutTimer();
      }
    } catch (error) {
      clearCheckoutTimer();
      $("#tokenResult").innerHTML = `<p>${escapeHtml(error.message)}</p>`;
    } finally {
      checking = false;
    }
  }, 5000);
}

async function showTokenView(token) {
  setView("tokenView");
  clearCheckoutTimer();
  try {
    const data = await request(`/orders/token/${encodeURIComponent(token)}`);
    $("#tokenResult").innerHTML = renderTokenResult(data);
    if (!["paid", "failed", "expired"].includes(data.pay_status)) {
      startTokenWatcher(token);
    }
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
      showToast("支付状态已更新为已支付");
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

const ORDER_CATEGORIES = [
  { key: "attention", label: "待处理" },
  { key: "success", label: "已完成" },
  { key: "unsuccessful", label: "未成功" },
  { key: "all", label: "全部" },
];

function orderNeedsAttention(order) {
  if (order.pay_status === "reviewing") return true;
  return order.pay_status === "paid" && (
    order.delivery_status !== "delivered" ||
    Boolean(order.email_error) ||
    !order.email_sent_at
  );
}

function orderSucceeded(order) {
  return order.pay_status === "paid" &&
    order.delivery_status === "delivered" &&
    Boolean(order.email_sent_at) &&
    !order.email_error;
}

function orderUnsuccessful(order) {
  return ["pending", "failed", "expired"].includes(order.pay_status) || order.delivery_status === "cancelled";
}

function orderMatchesCategory(order, category) {
  if (category === "attention") return orderNeedsAttention(order);
  if (category === "success") return orderSucceeded(order);
  if (category === "unsuccessful") return orderUnsuccessful(order);
  return true;
}

function renderOrderCategoryTabs(items) {
  const tabs = $("#orderCategoryTabs");
  if (!tabs) return;
  const counts = Object.fromEntries(ORDER_CATEGORIES.map((item) => [item.key, 0]));
  items.forEach((order) => {
    ORDER_CATEGORIES.forEach((category) => {
      if (orderMatchesCategory(order, category.key)) counts[category.key] += 1;
    });
  });
  tabs.innerHTML = ORDER_CATEGORIES.map((category) => `
    <button class="order-category-tab${state.adminOrderCategory === category.key ? " active" : ""}" type="button" data-order-category="${category.key}">
      <span>${escapeHtml(category.label)}</span>
      <b>${escapeHtml(counts[category.key])}</b>
    </button>
  `).join("");
}

function formatDateTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
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
  const allItems = data.items || [];
  renderOrderCategoryTabs(allItems);
  const filteredItems = allItems.filter((order) => orderMatchesCategory(order, state.adminOrderCategory));
  const visibleItems = filteredItems.slice(0, 50);
  const currentCategory = ORDER_CATEGORIES.find((item) => item.key === state.adminOrderCategory) || ORDER_CATEGORIES[0];
  const hintExtra = filteredItems.length > visibleItems.length ? `，仅显示最近 ${visibleItems.length} 条` : "";
  $("#orderListHint").textContent = `${currentCategory.label}：${filteredItems.length} 条（当前筛选共 ${allItems.length} 条${hintExtra}）`;
  $("#ordersTableWrap").hidden = state.ordersCollapsed;
  $("#toggleOrdersBtn").textContent = state.ordersCollapsed ? "展开列表" : "收起列表";
  const rows = visibleItems.map((order) => `
    <tr data-order="${escapeHtml(order.order_no)}">
      <td><strong>${escapeHtml(order.order_no)}</strong><br><small>${escapeHtml(order.product_name)}</small></td>
      <td>${escapeHtml(order.contact)}</td>
      <td>${escapeHtml(assignedInventoryText(order))}</td>
      <td>${escapeHtml(order.amount_text)} ${escapeHtml(order.currency)}</td>
      <td>${statusBadge(order.pay_status)}</td>
      <td>${statusBadge(order.delivery_status)}</td>
      <td>${emailBadge(order)}</td>
      <td>${order.has_upload ? `<button class="button quiet" data-download="${escapeHtml(order.order_no)}" type="button">下载</button>` : "无"}</td>
      <td>${escapeHtml(formatDateTime(order.created_at))}</td>
    </tr>
  `).join("");
  $("#ordersTableBody").innerHTML = rows || `<tr><td colspan="9">暂无订单</td></tr>`;
}

async function selectOrder(orderNo) {
  const order = await request(`${state.config.adminApiPrefix}/orders/${encodeURIComponent(orderNo)}`, { admin: true });
  state.selectedOrder = order;
  $("#deliveryForm").hidden = false;
  $("#selectedOrderTitle").textContent = `${order.order_no} · ${order.contact} · ${statusText(order.pay_status)} / ${statusText(order.delivery_status)}`;
  const form = $("#deliveryForm");
  form.pay_status.value = order.pay_status;
  form.delivery_status.value = order.delivery_status;
  form.delivery_result.value = order.delivery_result || "";
  const inventoryBox = $("#assignedInventoryBox");
  inventoryBox.hidden = false;
  inventoryBox.innerHTML = renderAssignedInventory(order);
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
      pay_status: form.pay_status.value,
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
        ${item.status !== "sold"
          ? `<button class="button quiet danger" type="button" data-delete-inventory="${escapeHtml(item.id)}">删除</button>`
          : `<span class="muted-text">已售出，保留记录</span>`}
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
  if (!window.confirm("确定删除这条库存吗？删除后不可恢复，已售出的库存不会被允许删除。")) return;
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
  $("#orderCategoryTabs").addEventListener("click", (event) => {
    const button = event.target.closest("[data-order-category]");
    if (!button) return;
    state.adminOrderCategory = button.dataset.orderCategory;
    loadOrders().catch((error) => showToast(error.message));
  });
  $("#toggleOrdersBtn").addEventListener("click", () => {
    state.ordersCollapsed = !state.ordersCollapsed;
    loadOrders().catch((error) => showToast(error.message));
  });
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

function setupPaymentModalEvents() {
  $("#paymentModalClose")?.addEventListener("click", () => closePaymentModal({ clearFrame: false }));
  $("#paymentModalRefresh")?.addEventListener("click", () => {
    if (!state.paymentOrder) {
      showToast("暂无可刷新的订单");
      return;
    }
    syncExternalPayment(state.paymentOrder).catch((error) => showToast(error.message));
  });
  $("#paymentModalOpenNew")?.addEventListener("click", () => {
    if (!state.paymentUrl) {
      showToast("暂无支付链接");
      return;
    }
    window.open(state.paymentUrl, "_blank", "noopener");
  });
}

function setupAfterPayNoticeEvents() {
  $("#afterPayNoticeClose")?.addEventListener("click", closeAfterPayNoticeModal);
  $("#afterPayNoticeOk")?.addEventListener("click", closeAfterPayNoticeModal);
  $("#afterPayNoticeModal .notice-modal-backdrop")?.addEventListener("click", closeAfterPayNoticeModal);
  $("#afterPayNoticeTabs")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-notice-key]");
    if (button) setAfterPayNoticePanel(button.dataset.noticeKey);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("#afterPayNoticeModal")?.hidden) {
      closeAfterPayNoticeModal();
    }
  });
}

function setupSupportWidget() {
  const button = $("#supportToggle");
  const card = $("#supportCard");
  if (!button || !card) return;
  button.addEventListener("click", () => {
    const nextOpen = card.hidden;
    card.hidden = !nextOpen;
    button.setAttribute("aria-expanded", String(nextOpen));
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
  $("#lookupForm")?.addEventListener("submit", handleLookup);
  setupPaymentModalEvents();
  setupAfterPayNoticeEvents();
  setupSupportWidget();
  setupAdminEvents();
  route();
}

boot();
