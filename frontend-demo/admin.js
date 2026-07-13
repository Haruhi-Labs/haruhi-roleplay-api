const state = {
  csrfToken: "",
  route: "overview",
  loading: false,
  overview: null,
};

const routes = {
  overview: {
    eyebrow: "运行状态",
    title: "总览",
    description: "掌握角色编排服务当前的关键资源与运行配置。",
  },
  usage: {
    eyebrow: "可观测性",
    title: "用量分析",
    description: "按服务、模型与时间观察请求和 Token 消耗。",
  },
  tokens: {
    eyebrow: "调用凭证",
    title: "服务令牌",
    description: "签发、调整和吊销绑定应用的独立调用凭证。",
  },
  personas: {
    eyebrow: "角色编排",
    title: "角色",
    description: "维护角色档案、Persona 模式与发布状态。",
  },
  models: {
    eyebrow: "推理资源",
    title: "模型",
    description: "配置模型 Provider、路由别名与连接状态。",
  },
  rag: {
    eyebrow: "知识上下文",
    title: "RAG 知识",
    description: "导入、检索和维护各应用隔离的知识资料。",
  },
  memory: {
    eyebrow: "长期上下文",
    title: "记忆",
    description: "查看用户长期记忆并执行精确清理。",
  },
  settings: {
    eyebrow: "部署与运行",
    title: "系统配置",
    description: "安全维护运行配置、存储与外部服务密钥。",
  },
};

const els = {
  bootView: document.querySelector("#bootView"),
  loginView: document.querySelector("#loginView"),
  loginForm: document.querySelector("#loginForm"),
  passwordInput: document.querySelector("#passwordInput"),
  passwordToggle: document.querySelector("#passwordToggle"),
  loginButton: document.querySelector("#loginButton"),
  loginError: document.querySelector("#loginError"),
  adminView: document.querySelector("#adminView"),
  sidebar: document.querySelector("#sidebar"),
  sidebarScrim: document.querySelector("#sidebarScrim"),
  menuButton: document.querySelector("#menuButton"),
  logoutButton: document.querySelector("#logoutButton"),
  refreshButton: document.querySelector("#refreshButton"),
  routeEyebrow: document.querySelector("#routeEyebrow"),
  routeTitle: document.querySelector("#routeTitle"),
  routeView: document.querySelector("#routeView"),
  liveStateText: document.querySelector("#liveStateText"),
  syncTime: document.querySelector("#syncTime"),
  toastRegion: document.querySelector("#toastRegion"),
};

init();

function init() {
  bindEvents();
  restoreSession();
}

function bindEvents() {
  els.loginForm.addEventListener("submit", login);
  els.passwordToggle.addEventListener("click", togglePassword);
  els.logoutButton.addEventListener("click", logout);
  els.refreshButton.addEventListener("click", () => renderRoute({ force: true }));
  els.menuButton.addEventListener("click", () => setSidebar(true));
  els.sidebarScrim.addEventListener("click", () => setSidebar(false));
  document.querySelectorAll("[data-route]").forEach((button) => {
    button.addEventListener("click", () => navigate(button.dataset.route));
  });
  window.addEventListener("hashchange", () => {
    const nextRoute = routeFromHash();
    if (nextRoute !== state.route) {
      state.route = nextRoute;
      renderRoute();
    }
  });
}

async function restoreSession() {
  try {
    const data = await request("/v1/admin/session", { allowUnauthorized: true });
    state.csrfToken = data.csrf_token;
    showAdmin();
  } catch (error) {
    showLogin();
  }
}

async function login(event) {
  event.preventDefault();
  const password = els.passwordInput.value;
  if (!password) {
    showLoginError("请输入管理员密码。");
    return;
  }
  setLoginBusy(true);
  showLoginError("");
  try {
    const data = await request("/v1/admin/session", {
      method: "POST",
      body: { password },
      allowUnauthorized: true,
    });
    state.csrfToken = data.csrf_token;
    els.passwordInput.value = "";
    showAdmin();
  } catch (error) {
    showLoginError(error.message || "登录失败，请稍后重试。");
  } finally {
    setLoginBusy(false);
  }
}

async function logout() {
  els.logoutButton.disabled = true;
  try {
    await request("/v1/admin/session", { method: "DELETE" });
  } catch (error) {
    showToast(error.message, true);
  } finally {
    state.csrfToken = "";
    state.overview = null;
    els.logoutButton.disabled = false;
    showLogin();
  }
}

function showLogin() {
  els.bootView.hidden = true;
  els.adminView.hidden = true;
  els.loginView.hidden = false;
  window.setTimeout(() => els.passwordInput.focus(), 0);
}

function showAdmin() {
  els.bootView.hidden = true;
  els.loginView.hidden = true;
  els.adminView.hidden = false;
  state.route = routeFromHash();
  renderRoute();
}

function togglePassword() {
  const shouldShow = els.passwordInput.type === "password";
  els.passwordInput.type = shouldShow ? "text" : "password";
  els.passwordToggle.textContent = shouldShow ? "隐藏" : "显示";
  els.passwordToggle.setAttribute("aria-label", shouldShow ? "隐藏密码" : "显示密码");
}

function setLoginBusy(busy) {
  els.loginButton.disabled = busy;
  els.passwordInput.disabled = busy;
  els.loginButton.firstElementChild.textContent = busy ? "正在验证" : "安全登录";
}

function showLoginError(message) {
  els.loginError.textContent = message;
  els.loginError.hidden = !message;
}

function navigate(route) {
  const next = routes[route] ? route : "overview";
  setSidebar(false);
  if (state.route === next) {
    renderRoute();
    return;
  }
  window.location.hash = next;
}

function routeFromHash() {
  const route = window.location.hash.replace(/^#\/?/, "");
  return routes[route] ? route : "overview";
}

async function renderRoute({ force = false } = {}) {
  const route = routes[state.route];
  els.routeEyebrow.textContent = route.eyebrow;
  els.routeTitle.textContent = route.title;
  document.title = `${route.title} · Haruhi Control Room`;
  document.querySelectorAll("[data-route]").forEach((button) => {
    const active = button.dataset.route === state.route;
    button.classList.toggle("is-active", active);
    if (active) {
      button.setAttribute("aria-current", "page");
    } else {
      button.removeAttribute("aria-current");
    }
  });
  renderLoading();
  try {
    if (state.route === "overview") {
      await renderOverview(force);
    } else if (state.route === "settings") {
      await renderSettingsSummary();
    } else {
      renderCapabilityPlaceholder(state.route);
    }
    els.routeView.focus({ preventScroll: true });
  } catch (error) {
    renderError(error);
  }
}

async function renderOverview(force) {
  if (!state.overview || force) {
    setLiveState("正在同步");
    const [health, personas, tokens, runtimeConfig] = await Promise.all([
      request("/health"),
      request("/v1/personas"),
      request("/v1/access-tokens"),
      request("/v1/runtime-config"),
    ]);
    state.overview = { health, personas, tokens, runtimeConfig };
  }
  const { health, personas, tokens, runtimeConfig } = state.overview;
  const items = tokens.items || [];
  const activeTokens = items.filter((item) => item.status === "active");
  const roleCount = (personas.characters || []).length;
  const modeCount = (personas.characters || []).reduce(
    (sum, character) => sum + (character.modes || []).length,
    0,
  );
  const totalTokens = items.reduce((sum, item) => sum + Number(item.total_tokens || 0), 0);
  const quotaTokens = items.reduce(
    (sum, item) => sum + (item.quota_tokens === null ? 0 : Number(item.quota_tokens || 0)),
    0,
  );
  const finiteUsed = items.reduce(
    (sum, item) => sum + (item.quota_tokens === null ? 0 : Number(item.total_tokens || 0)),
    0,
  );
  const capacity = quotaTokens ? Math.min((finiteUsed / quotaTokens) * 100, 100) : 0;
  const values = runtimeConfig.values || {};
  const providers = providerRows(values);

  els.routeView.innerHTML = `
    <div class="page-lead">
      <div>
        <p class="eyebrow">System pulse</p>
        <h2>编排服务一切正常</h2>
        <p>这里汇集凭证、角色、模型和上下文资源的实时摘要。管理动作会保留明确的状态与风险边界。</p>
      </div>
      <span class="status-badge">${escapeHtml(health.status || "ok")}</span>
    </div>

    <section class="metric-rack" aria-label="核心指标">
      ${metricCell("活跃服务令牌", formatNumber(activeTokens.length), `共 ${formatNumber(items.length)} 个凭证`)}
      ${metricCell("累计 Token", formatCompactNumber(totalTokens), "Prompt 与 Completion 合计")}
      ${metricCell("可用角色", formatNumber(roleCount), `${formatNumber(modeCount)} 个 Persona 模式`)}
      ${metricCell("配置来源", runtimeConfig.persists_updates ? "持久化" : "内存", shortPath(runtimeConfig.source))}
    </section>

    <div class="dashboard-grid">
      <section class="surface">
        <header class="surface-head">
          <div><h3>编排资源</h3><p>当前装配的 Provider 与持久化策略</p></div>
          <button class="ghost-action" type="button" data-go-route="models">管理模型</button>
        </header>
        <div class="surface-body provider-list">
          ${providers.map(providerRow).join("")}
        </div>
      </section>

      <section class="surface">
        <header class="surface-head">
          <div><h3>额度使用</h3><p>有限额服务令牌的合计消耗</p></div>
        </header>
        <div class="surface-body capacity-figure">
          <div class="capacity-total">
            <strong>${capacity.toFixed(capacity < 10 ? 1 : 0)}%</strong>
            <span>${formatCompactNumber(finiteUsed)} / ${quotaTokens ? formatCompactNumber(quotaTokens) : "未设置"}</span>
          </div>
          <progress class="capacity-bar" max="100" value="${capacity.toFixed(2)}" aria-label="有限额令牌使用率"></progress>
          <div class="capacity-legend">
            <div><span>有限额令牌</span><strong>${formatNumber(items.filter((item) => item.quota_tokens !== null).length)}</strong></div>
            <div><span>不限额令牌</span><strong>${formatNumber(items.filter((item) => item.quota_tokens === null).length)}</strong></div>
            <div><span>已吊销</span><strong>${formatNumber(items.filter((item) => item.status === "revoked").length)}</strong></div>
          </div>
        </div>
      </section>
    </div>
  `;
  bindRouteLinks();
  markSynced();
}

async function renderSettingsSummary() {
  const [snapshot, schema] = await Promise.all([
    request("/v1/env-config"),
    request("/v1/env-config/schema"),
  ]);
  const restartCount = (schema.fields || []).filter((field) => field.restart_required).length;
  const secretCount = (schema.fields || []).filter((field) => field.secret).length;
  els.routeView.innerHTML = `
    <div class="page-lead">
      <div><h2>部署配置</h2><p>配置中心会对敏感值脱敏，并区分热更新与需要重启的变更。</p></div>
      <a class="primary-action" href="/config">打开配置编辑器</a>
    </div>
    <section class="metric-rack">
      ${metricCell("配置字段", formatNumber((schema.fields || []).length), "已知且经过类型校验")}
      ${metricCell("敏感字段", formatNumber(secretCount), "只写入，不回显")}
      ${metricCell("重启字段", formatNumber(restartCount), "保存后需重启服务")}
      ${metricCell("写回状态", snapshot.writable ? "可写" : "只读", shortPath(snapshot.source))}
    </section>
    <div class="empty-state settings-empty">
      <span class="empty-symbol">CFG</span>
      <h2>完整配置编辑器已隔离</h2>
      <p>Provider 密钥、数据库连接和监听配置属于高风险操作，继续使用独立的受信任编辑器，并共享当前安全会话。</p>
    </div>
  `;
  markSynced();
}

function renderCapabilityPlaceholder(route) {
  const copy = {
    usage: ["用量时间线正在接入", "这里将提供全局趋势、服务排行、错误率与模型 Token 构成。"],
    tokens: ["令牌工作台正在接入", "这里将完成签发、额度调整、吊销与逐请求审计。"],
    personas: ["角色工作台正在接入", "这里将维护角色档案、Persona 模式、草稿与发布状态。"],
    models: ["模型路由正在接入", "这里将管理 Provider、模型别名、密钥状态和连接检查。"],
    rag: ["知识库工作台正在接入", "这里将管理文档导入、隔离范围、检索测试与删除。"],
    memory: ["记忆工作台正在接入", "这里将按应用和用户检查、筛选并清理长期记忆。"],
  }[route];
  els.routeView.innerHTML = `
    <div class="page-lead">
      <div><h2>${escapeHtml(routes[route].title)}</h2><p>${escapeHtml(routes[route].description)}</p></div>
    </div>
    <div class="empty-state">
      <span class="empty-symbol">${escapeHtml(route.slice(0, 3).toUpperCase())}</span>
      <h2>${escapeHtml(copy[0])}</h2>
      <p>${escapeHtml(copy[1])}</p>
    </div>
  `;
  setLiveState("框架已就绪");
}

function renderLoading() {
  els.routeView.innerHTML = `
    <div class="loading-state">
      <span class="skeleton-line"></span>
      <h2>正在读取管理数据</h2>
      <p>安全会话已建立，正在同步当前资源状态。</p>
    </div>
  `;
}

function renderError(error) {
  els.routeView.innerHTML = `
    <div class="error-state">
      <span class="empty-symbol">!</span>
      <h2>无法载入当前页面</h2>
      <p>${escapeHtml(error.message || "管理接口返回了未知错误。")}</p>
      <button class="secondary-action" type="button" data-retry>重新载入</button>
    </div>
  `;
  els.routeView.querySelector("[data-retry]")?.addEventListener("click", () => renderRoute({ force: true }));
  setLiveState("同步失败");
}

function providerRows(values) {
  const modelType = values.LLM_API_TYPE || values.MODEL_PROVIDER || "fake";
  const modelName = values.LLM_MODEL || values.MODEL_NAME || "服务端默认";
  return [
    ["LLM", modelName, `Provider · ${modelType}`, "ready"],
    ["Embedding", values.EMBEDDING_MODEL || values.EMBEDDING_API_TYPE || "hash", `Provider · ${values.EMBEDDING_API_TYPE || values.EMBEDDING_PROVIDER || "hash"}`, "ready"],
    ["RAG", values.RAG_INDEX || values.RAG_API_TYPE || values.RAG_PROVIDER || "local", `Provider · ${values.RAG_API_TYPE || values.RAG_PROVIDER || "local"}`, "ready"],
    ["Session", values.SESSION_PROVIDER || "memory", shortPath(values.SESSION_SQLITE_PATH || "进程内存"), "ready"],
    ["Memory", values.MEMORY_PROVIDER || "memory", shortPath(values.MEMORY_SQLITE_PATH || "进程内存"), "ready"],
  ];
}

function providerRow([kind, name, detail, status]) {
  return `
    <div class="provider-row">
      <span class="provider-kind">${escapeHtml(kind)}</span>
      <div><strong>${escapeHtml(String(name))}</strong><small>${escapeHtml(String(detail))}</small></div>
      <span class="status-badge">${escapeHtml(status)}</span>
    </div>
  `;
}

function metricCell(label, value, hint) {
  return `
    <div class="metric-cell">
      <span class="metric-label">${escapeHtml(label)}<i></i></span>
      <strong class="metric-value">${escapeHtml(String(value))}</strong>
      <span class="metric-hint" title="${escapeHtml(String(hint))}">${escapeHtml(String(hint))}</span>
    </div>
  `;
}

function bindRouteLinks() {
  els.routeView.querySelectorAll("[data-go-route]").forEach((button) => {
    button.addEventListener("click", () => navigate(button.dataset.goRoute));
  });
}

function setSidebar(open) {
  els.sidebar.classList.toggle("is-open", open);
  els.sidebarScrim.hidden = !open;
}

function setLiveState(text) {
  els.liveStateText.textContent = text;
}

function markSynced() {
  const now = new Date();
  els.syncTime.textContent = `同步于 ${new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(now)}`;
  setLiveState("服务在线");
}

function showToast(message, error = false) {
  const toast = document.createElement("div");
  toast.className = `toast${error ? " is-error" : ""}`;
  toast.textContent = message;
  els.toastRegion.append(toast);
  window.setTimeout(() => toast.remove(), 4200);
}

async function request(path, options = {}) {
  const method = options.method || "GET";
  const headers = { Accept: "application/json" };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && state.csrfToken) {
    headers["X-CSRF-Token"] = state.csrfToken;
  }
  const response = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    cache: "no-store",
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  let payload;
  try {
    payload = await response.json();
  } catch (error) {
    throw new Error(`管理接口返回了无法解析的响应（HTTP ${response.status}）。`);
  }
  if (!response.ok || !payload.ok) {
    if (response.status === 401 && !options.allowUnauthorized) {
      state.csrfToken = "";
      showLogin();
    }
    throw new Error(payload.error?.message || `请求失败（HTTP ${response.status}）。`);
  }
  return payload.data;
}

function formatNumber(value) {
  return new Intl.NumberFormat("zh-CN").format(Number(value || 0));
}

function formatCompactNumber(value) {
  return new Intl.NumberFormat("zh-CN", {
    notation: Number(value) >= 10_000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(Number(value || 0));
}

function shortPath(value) {
  const text = String(value || "—");
  if (text.length <= 34) {
    return text;
  }
  return `…${text.slice(-31)}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
