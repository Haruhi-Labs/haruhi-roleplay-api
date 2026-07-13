const state = {
  csrfToken: "",
  route: "overview",
  loading: false,
  overview: null,
  tokens: null,
  personas: null,
  usageDays: 30,
  ragAppId: "",
  memoryFilters: {
    appId: "",
    userId: "",
    characterId: "",
    memoryType: "",
    limit: 50,
    offset: 0,
  },
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
  dialogRoot: document.querySelector("#dialogRoot"),
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
    } else if (state.route === "tokens") {
      await renderTokens();
    } else if (state.route === "usage") {
      await renderUsage();
    } else if (state.route === "personas") {
      await renderPersonas();
    } else if (state.route === "models") {
      await renderModels();
    } else if (state.route === "rag") {
      await renderRag();
    } else if (state.route === "memory") {
      await renderMemory();
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

async function renderTokens() {
  const data = await request("/v1/access-tokens");
  state.tokens = data.items || [];
  paintTokens();
  markSynced();
}

function paintTokens(query = "", status = "all") {
  const items = filteredTokens(query, status);
  const active = (state.tokens || []).filter((item) => item.status === "active").length;
  const exhausted = (state.tokens || []).filter(
    (item) => item.quota_tokens !== null && item.remaining_tokens === 0,
  ).length;
  els.routeView.innerHTML = `
    <div class="page-lead">
      <div><h2>服务调用凭证</h2><p>每个令牌只绑定一个应用。明文只在签发时出现一次，后续只能查看安全前缀。</p></div>
      <button id="createTokenButton" class="primary-action" type="button">新建服务令牌</button>
    </div>
    <section class="metric-rack compact-metrics">
      ${metricCell("全部令牌", formatNumber((state.tokens || []).length), "包含已吊销凭证")}
      ${metricCell("活跃令牌", formatNumber(active), "当前可通过鉴权")}
      ${metricCell("额度耗尽", formatNumber(exhausted), "下一次模型请求将被拒绝")}
      ${metricCell("累计 Token", formatCompactNumber((state.tokens || []).reduce((sum, item) => sum + Number(item.total_tokens || 0), 0)), "全部服务历史累计")}
    </section>
    <section class="surface data-surface">
      <div class="table-toolbar">
        <label class="search-control"><span>搜索</span><input id="tokenSearch" type="search" placeholder="服务名称、App ID 或前缀" value="${escapeHtml(query)}" /></label>
        <label class="select-control"><span>状态</span><select id="tokenStatus"><option value="all">全部状态</option><option value="active"${status === "active" ? " selected" : ""}>活跃</option><option value="revoked"${status === "revoked" ? " selected" : ""}>已吊销</option></select></label>
        <span id="tokenCount" class="table-count">显示 ${formatNumber(items.length)} / ${formatNumber((state.tokens || []).length)}</span>
      </div>
      <div id="tokenTableWrap" class="table-wrap">
        ${items.length ? tokenTable(items) : tableEmpty("没有符合条件的服务令牌", "调整筛选条件，或签发一个新的应用令牌。")}
      </div>
    </section>
  `;
  document.querySelector("#createTokenButton")?.addEventListener("click", showCreateTokenDialog);
  const search = document.querySelector("#tokenSearch");
  const statusSelect = document.querySelector("#tokenStatus");
  search?.addEventListener("input", () => updateTokenTable(search.value, statusSelect.value));
  statusSelect?.addEventListener("change", () => updateTokenTable(search.value, statusSelect.value));
  bindTokenRowButtons();
}

function filteredTokens(query, status) {
  const normalizedQuery = query.trim().toLocaleLowerCase("zh-CN");
  return (state.tokens || []).filter((item) => {
    const matchesStatus = status === "all" || item.status === status;
    const haystack = `${item.name} ${item.app_id || ""} ${item.prefix}`.toLocaleLowerCase("zh-CN");
    return matchesStatus && (!normalizedQuery || haystack.includes(normalizedQuery));
  });
}

function updateTokenTable(query, status) {
  const items = filteredTokens(query, status);
  const wrapper = document.querySelector("#tokenTableWrap");
  const count = document.querySelector("#tokenCount");
  if (wrapper) {
    wrapper.innerHTML = items.length
      ? tokenTable(items)
      : tableEmpty("没有符合条件的服务令牌", "调整筛选条件，或签发一个新的应用令牌。");
  }
  if (count) {
    count.textContent = `显示 ${formatNumber(items.length)} / ${formatNumber((state.tokens || []).length)}`;
  }
  bindTokenRowButtons();
}

function bindTokenRowButtons() {
  els.routeView.querySelectorAll("[data-token-id]").forEach((button) => {
    button.addEventListener("click", () => showTokenDetails(button.dataset.tokenId));
  });
}

function tokenTable(items) {
  return `
    <table class="data-table">
      <thead><tr><th>服务</th><th>状态</th><th>额度</th><th>累计用量</th><th>最后调用</th><th><span class="visually-hidden">操作</span></th></tr></thead>
      <tbody>
        ${items.map((item) => `
          <tr>
            <td><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.app_id || "未绑定应用")} · ${escapeHtml(item.prefix)}</small></td>
            <td>${statusBadge(item.status)}</td>
            <td>${quotaCell(item)}</td>
            <td><span class="numeric">${formatNumber(item.total_tokens)}</span><small>P ${formatCompactNumber(item.prompt_tokens)} · C ${formatCompactNumber(item.completion_tokens)}</small></td>
            <td>${formatDate(item.last_used_at, "尚未使用")}</td>
            <td class="row-action"><button class="ghost-action" type="button" data-token-id="${escapeHtml(item.token_id)}">查看</button></td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function quotaCell(item) {
  if (item.quota_tokens === null) {
    return `<strong>不限额</strong><small>无硬性 Token 上限</small>`;
  }
  const used = Number(item.total_tokens || 0);
  const quota = Number(item.quota_tokens || 0);
  const ratio = quota ? Math.min((used / quota) * 100, 100) : 0;
  return `
    <strong>${formatCompactNumber(item.remaining_tokens)} 剩余</strong>
    <progress class="quota-progress" max="100" value="${ratio.toFixed(2)}" aria-label="额度已使用 ${ratio.toFixed(0)}%"></progress>
    <small>${formatCompactNumber(used)} / ${formatCompactNumber(quota)}</small>
  `;
}

async function showCreateTokenDialog() {
  const dialog = openDialog(`
    <div class="dialog-head"><div><p class="eyebrow">Issue credential</p><h2>新建服务令牌</h2></div><button class="dialog-close" type="button" data-close aria-label="关闭">×</button></div>
    <form id="createTokenForm" class="dialog-form">
      <label><span>服务名称</span><input name="name" required maxlength="120" placeholder="例如：订单服务生产环境" /></label>
      <label><span>App ID</span><input name="app_id" required maxlength="128" placeholder="例如：order-service" /></label>
      <label><span>Token 总额度</span><input name="quota_tokens" type="number" min="1" step="1" placeholder="留空表示不限额" /></label>
      <label><span>过期时间</span><input name="expires_at" type="datetime-local" /><small>留空表示永不过期；时间按当前浏览器时区解释。</small></label>
      <div class="dialog-notice"><i></i><p>令牌创建后无法修改 App ID。明文只显示一次，请准备好安全的 Secret Manager。</p></div>
      <div class="dialog-actions"><button class="ghost-action" type="button" data-close>取消</button><button class="primary-action" type="submit">签发令牌</button></div>
    </form>
  `);
  const form = dialog.querySelector("#createTokenForm");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector("[type=submit]");
    submit.disabled = true;
    try {
      const data = new FormData(form);
      const quota = String(data.get("quota_tokens") || "").trim();
      const expires = String(data.get("expires_at") || "").trim();
      const issued = await request("/v1/access-tokens", {
        method: "POST",
        body: {
          name: String(data.get("name") || "").trim(),
          app_id: String(data.get("app_id") || "").trim(),
          quota_tokens: quota ? Number(quota) : null,
          expires_at: expires ? new Date(expires).toISOString() : null,
        },
      });
      dialog.close();
      dialog.remove();
      state.overview = null;
      await showIssuedSecret(issued);
      await renderTokens();
    } catch (error) {
      showDialogError(form, error.message);
      submit.disabled = false;
    }
  });
}

function showIssuedSecret(issued) {
  return new Promise((resolve) => {
    const dialog = openDialog(`
      <div class="dialog-head"><div><p class="eyebrow">Credential issued</p><h2>立即保存令牌</h2></div></div>
      <div class="secret-warning">关闭后将无法再次查看这段明文。</div>
      <div class="issued-summary"><div><span>服务</span><strong>${escapeHtml(issued.name)}</strong></div><div><span>App ID</span><strong>${escapeHtml(issued.app_id)}</strong></div></div>
      <div class="secret-box"><code id="issuedSecret">${escapeHtml(issued.token)}</code><button id="copySecretButton" class="secondary-action" type="button">复制</button></div>
      <div class="dialog-actions"><button id="secretSavedButton" class="primary-action" type="button">我已安全保存</button></div>
    `, { persistent: true });
    dialog.querySelector("#copySecretButton").addEventListener("click", async (event) => {
      try {
        await navigator.clipboard.writeText(issued.token);
        event.currentTarget.textContent = "已复制";
      } catch (error) {
        showToast("浏览器未允许复制，请手动选择令牌文本。", true);
      }
    });
    dialog.querySelector("#secretSavedButton").addEventListener("click", () => {
      dialog.close();
      dialog.remove();
      resolve();
    });
  });
}

async function showTokenDetails(tokenId) {
  const dialog = openDialog(`<div class="loading-state dialog-loading"><span class="skeleton-line"></span><h2>正在读取令牌</h2></div>`);
  try {
    const [token, logs] = await Promise.all([
      request(`/v1/access-tokens/${encodeURIComponent(tokenId)}`),
      request(`/v1/access-tokens/${encodeURIComponent(tokenId)}/logs?limit=50`),
    ]);
    dialog.innerHTML = `
      <div class="dialog-head"><div><p class="eyebrow">Service credential</p><h2>${escapeHtml(token.name)}</h2><p>${escapeHtml(token.app_id || "Legacy unscoped")} · ${escapeHtml(token.prefix)}</p></div><button class="dialog-close" type="button" data-close aria-label="关闭">×</button></div>
      <div class="detail-metrics">
        <div><span>状态</span>${statusBadge(token.status)}</div>
        <div><span>累计 Token</span><strong>${formatNumber(token.total_tokens)}</strong></div>
        <div><span>剩余额度</span><strong>${token.remaining_tokens === null ? "不限额" : formatNumber(token.remaining_tokens)}</strong></div>
        <div><span>最后使用</span><strong>${formatDate(token.last_used_at, "尚未使用")}</strong></div>
      </div>
      <form id="quotaForm" class="inline-form">
        <label><span>调整总额度</span><input name="quota_tokens" type="number" min="1" step="1" value="${token.quota_tokens ?? ""}" placeholder="留空表示不限额" /></label>
        <button class="secondary-action" type="submit"${token.status !== "active" ? " disabled" : ""}>保存额度</button>
      </form>
      <section class="dialog-section">
        <div class="section-heading"><div><h3>最近请求</h3><p>最多显示最近 50 条，不包含请求正文与令牌明文。</p></div><span class="table-count">${formatNumber(logs.count)} 条</span></div>
        <div class="table-wrap compact-table">${logs.items.length ? requestLogTable(logs.items) : tableEmpty("还没有请求记录", "该服务令牌尚未发起经过审计的调用。")}</div>
      </section>
      <div class="dialog-actions split-actions"><div>${token.status === "active" ? '<button id="revokeTokenButton" class="danger-action" type="button">吊销令牌</button>' : ""}</div><button class="ghost-action" type="button" data-close>关闭</button></div>
    `;
    bindDialogClose(dialog);
    dialog.querySelector("#quotaForm")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const raw = new FormData(form).get("quota_tokens");
      const button = form.querySelector("button");
      button.disabled = true;
      try {
        await request(`/v1/access-tokens/${encodeURIComponent(tokenId)}`, {
          method: "PATCH",
          body: { quota_tokens: String(raw || "").trim() ? Number(raw) : null },
        });
        dialog.close();
        dialog.remove();
        state.overview = null;
        showToast("令牌额度已更新。");
        await renderTokens();
      } catch (error) {
        showToast(error.message, true);
        button.disabled = false;
      }
    });
    dialog.querySelector("#revokeTokenButton")?.addEventListener("click", async () => {
      const confirmed = await confirmAction({
        title: "吊销这个服务令牌？",
        message: "调用方将立即无法继续鉴权。该操作不会删除历史用量与审计日志。",
        confirmLabel: "确认吊销",
      });
      if (!confirmed) return;
      await request(`/v1/access-tokens/${encodeURIComponent(tokenId)}`, { method: "DELETE" });
      dialog.close();
      dialog.remove();
      state.overview = null;
      showToast("服务令牌已吊销。");
      await renderTokens();
    });
  } catch (error) {
    dialog.close();
    dialog.remove();
    showToast(error.message, true);
  }
}

async function renderUsage() {
  const [usage, logs] = await Promise.all([
    request(`/v1/admin/usage?days=${state.usageDays}`),
    request("/v1/admin/request-logs?limit=50"),
  ]);
  const serviceNames = new Map((usage.services || []).map((item) => [item.token_id, item.name]));
  els.routeView.innerHTML = `
    <div class="page-lead">
      <div><h2>服务用量与健康度</h2><p>所有指标来自逐令牌审计账本，按 UTC 日期窗口聚合，不采集请求正文或对话内容。</p></div>
      <div class="period-control" role="group" aria-label="统计周期">
        ${[7, 30, 90].map((days) => `<button type="button" data-days="${days}" class="${state.usageDays === days ? "is-active" : ""}">${days} 天</button>`).join("")}
      </div>
    </div>
    <section class="metric-rack">
      ${metricCell("请求总量", formatNumber(usage.request_count), `${formatNumber(usage.active_service_count)} 个活跃服务`)}
      ${metricCell("总 Token", formatCompactNumber(usage.total_tokens), `P ${formatCompactNumber(usage.prompt_tokens)} · C ${formatCompactNumber(usage.completion_tokens)}`)}
      ${metricCell("错误率", formatPercent(usage.error_rate), `${formatNumber(usage.error_count)} 次失败请求`)}
      ${metricCell("平均耗时", formatDuration(usage.average_duration_ms), "端到端 HTTP 审计耗时")}
    </section>
    <div class="dashboard-grid usage-grid">
      <section class="surface trend-surface">
        <header class="surface-head"><div><h3>Token 消耗趋势</h3><p>每日 Token 与请求量</p></div><span class="table-count">最近 ${usage.period_days} 天</span></header>
        <div class="surface-body">${usageTrendSvg(usage.daily || [])}</div>
      </section>
      <section class="surface">
        <header class="surface-head"><div><h3>路由热度</h3><p>按请求次数排序</p></div></header>
        <div class="surface-body route-ranking">${(usage.routes || []).length ? usage.routes.slice(0, 8).map(routeUsageRow).join("") : '<div class="mini-empty">当前周期暂无请求</div>'}</div>
      </section>
    </div>
    <section class="surface data-surface">
      <header class="surface-head"><div><h3>逐服务用量</h3><p>包含当前窗口内零调用的服务</p></div></header>
      <div class="table-wrap">${serviceUsageTable(usage.services || [])}</div>
    </section>
    <section class="surface data-surface">
      <header class="surface-head"><div><h3>最近审计事件</h3><p>跨全部服务令牌的最近请求</p></div><span class="table-count">${formatNumber(logs.count)} 条</span></header>
      <div class="table-wrap">${logs.items.length ? globalLogTable(logs.items, serviceNames) : tableEmpty("当前没有审计事件", "服务令牌产生调用后，请求会出现在这里。")}</div>
    </section>
  `;
  els.routeView.querySelectorAll("[data-days]").forEach((button) => {
    button.addEventListener("click", () => {
      state.usageDays = Number(button.dataset.days);
      renderRoute();
    });
  });
  markSynced();
}

function usageTrendSvg(daily) {
  if (!daily.length) {
    return '<div class="mini-empty">当前周期暂无用量数据</div>';
  }
  const width = 760;
  const height = 230;
  const insetX = 30;
  const insetY = 24;
  const plotWidth = width - insetX * 2;
  const plotHeight = height - insetY * 2 - 24;
  const maxTokens = Math.max(...daily.map((item) => Number(item.total_tokens || 0)), 1);
  const maxRequests = Math.max(...daily.map((item) => Number(item.request_count || 0)), 1);
  const step = daily.length > 1 ? plotWidth / (daily.length - 1) : plotWidth;
  const points = daily.map((item, index) => {
    const x = insetX + (daily.length === 1 ? plotWidth / 2 : index * step);
    const y = insetY + plotHeight - (Number(item.total_tokens || 0) / maxTokens) * plotHeight;
    return [x, y];
  });
  const line = points.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  const bars = daily.map((item, index) => {
    const barWidth = Math.max(Math.min(plotWidth / daily.length - 2, 14), 2);
    const x = insetX + (daily.length === 1 ? plotWidth / 2 : index * step) - barWidth / 2;
    const barHeight = (Number(item.request_count || 0) / maxRequests) * plotHeight;
    const y = insetY + plotHeight - barHeight;
    return `<rect x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${barWidth.toFixed(2)}" height="${barHeight.toFixed(2)}" rx="2"><title>${escapeHtml(item.date)} · ${formatNumber(item.request_count)} 请求 · ${formatNumber(item.total_tokens)} Token</title></rect>`;
  }).join("");
  const labels = [0, Math.floor((daily.length - 1) / 2), daily.length - 1]
    .filter((value, index, array) => array.indexOf(value) === index)
    .map((index) => {
      const x = insetX + (daily.length === 1 ? plotWidth / 2 : index * step);
      return `<text x="${x.toFixed(2)}" y="${height - 4}" text-anchor="middle">${escapeHtml(shortDate(daily[index].date))}</text>`;
    }).join("");
  return `
    <div class="trend-legend"><span><i class="token-line"></i>Token</span><span><i class="request-bar"></i>请求</span></div>
    <svg class="trend-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="每日 Token 与请求量趋势">
      <line x1="${insetX}" y1="${insetY + plotHeight}" x2="${width - insetX}" y2="${insetY + plotHeight}"></line>
      <g class="request-bars">${bars}</g>
      <polyline class="token-polyline" points="${line}"></polyline>
      <g class="chart-labels">${labels}</g>
    </svg>
  `;
}

function serviceUsageTable(items) {
  if (!items.length) return tableEmpty("还没有服务令牌", "签发服务令牌后可按调用方观察用量。")
  return `
    <table class="data-table">
      <thead><tr><th>服务</th><th>请求</th><th>Token</th><th>错误率</th><th>平均耗时</th><th>最后调用</th></tr></thead>
      <tbody>${items.map((item) => `
        <tr><td><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.app_id || "未绑定应用")}</small></td><td class="numeric">${formatNumber(item.request_count)}</td><td><strong>${formatCompactNumber(item.total_tokens)}</strong><small>P ${formatCompactNumber(item.prompt_tokens)} · C ${formatCompactNumber(item.completion_tokens)}</small></td><td>${formatPercent(item.error_rate)}</td><td>${formatDuration(item.average_duration_ms)}</td><td>${formatDate(item.last_used_at, "无调用")}</td></tr>
      `).join("")}</tbody>
    </table>
  `;
}

function routeUsageRow(item) {
  return `<div class="route-rank-row"><span class="method-badge">${escapeHtml(item.method)}</span><div><strong>${escapeHtml(item.path)}</strong><small>${formatNumber(item.request_count)} 请求 · ${formatCompactNumber(item.total_tokens)} Token</small></div><span>${formatDuration(item.average_duration_ms)}</span></div>`;
}

function requestLogTable(items) {
  return `
    <table class="data-table">
      <thead><tr><th>时间</th><th>请求</th><th>状态</th><th>Token</th><th>耗时</th></tr></thead>
      <tbody>${items.map((item) => `<tr><td>${formatDate(item.created_at)}</td><td><strong>${escapeHtml(item.method)} ${escapeHtml(item.path)}</strong><small>${escapeHtml(item.request_id)}</small></td><td>${httpStatusBadge(item)}</td><td class="numeric">${formatNumber(item.total_tokens)}</td><td>${formatDuration(item.duration_ms)}</td></tr>`).join("")}</tbody>
    </table>
  `;
}

function globalLogTable(items, serviceNames) {
  return `
    <table class="data-table">
      <thead><tr><th>时间</th><th>服务</th><th>请求</th><th>状态</th><th>Token</th><th>耗时</th></tr></thead>
      <tbody>${items.map((item) => `<tr><td>${formatDate(item.created_at)}</td><td><strong>${escapeHtml(serviceNames.get(item.token_id) || "未知服务")}</strong><small>${escapeHtml(item.token_id)}</small></td><td><strong>${escapeHtml(item.method)} ${escapeHtml(item.path)}</strong><small>${escapeHtml(item.request_id)}</small></td><td>${httpStatusBadge(item)}</td><td class="numeric">${formatNumber(item.total_tokens)}</td><td>${formatDuration(item.duration_ms)}</td></tr>`).join("")}</tbody>
    </table>
  `;
}

async function renderPersonas() {
  const data = await request("/v1/admin/personas");
  state.personas = data.characters || [];
  const presetCount = state.personas.reduce((sum, item) => sum + (item.presets || []).length, 0);
  const publicCount = state.personas.filter((item) => item.character.visibility === "public").length;
  els.routeView.innerHTML = `
    <div class="page-lead">
      <div><h2>角色与 Persona</h2><p>角色档案决定可选模式，Persona 模式定义时间线、语气、行为规则、知识边界与上下文策略。</p></div>
      <button id="createPersonaButton" class="primary-action" type="button"${data.writable ? "" : " disabled"}>新建角色</button>
    </div>
    <section class="metric-rack compact-metrics">
      ${metricCell("角色", formatNumber(data.count), data.writable ? "角色目录可写" : "角色目录只读")}
      ${metricCell("Persona 模式", formatNumber(presetCount), "全部可见性状态")}
      ${metricCell("公开角色", formatNumber(publicCount), "可由业务接口列出")}
      ${metricCell("草稿/私有", formatNumber(data.count - publicCount), "仅后台管理可见")}
    </section>
    <section class="persona-grid">
      ${state.personas.length ? state.personas.map(personaCard).join("") : `
        <div class="empty-state persona-empty"><span class="empty-symbol">人</span><h2>尚未配置角色</h2><p>创建第一个角色与默认 Persona 模式后，业务接口才可以进行角色编排。</p></div>
      `}
    </section>
  `;
  document.querySelector("#createPersonaButton")?.addEventListener("click", showCreatePersonaDialog);
  els.routeView.querySelectorAll("[data-character-id]").forEach((button) => {
    button.addEventListener("click", () => showPersonaDetails(button.dataset.characterId));
  });
  markSynced();
}

function personaCard(item) {
  const character = item.character;
  const tags = character.tags || [];
  return `
    <article class="persona-card">
      <div class="persona-card-top">
        <span class="persona-initial">${escapeHtml(String(character.displayName || character.characterId).slice(0, 1))}</span>
        <div>${visibilityBadge(character.visibility)}<h3>${escapeHtml(character.displayName)}</h3><p>${escapeHtml(character.characterId)}</p></div>
        <button class="ghost-action" type="button" data-character-id="${escapeHtml(character.characterId)}">管理</button>
      </div>
      <p class="persona-description">${escapeHtml(character.description)}</p>
      <div class="persona-mode-list">
        ${(item.presets || []).map((preset) => `<span${preset.personaMode === character.defaultPersonaMode ? ' class="is-default"' : ""}>${escapeHtml(preset.displayName)}${preset.personaMode === character.defaultPersonaMode ? " · 默认" : ""}</span>`).join("")}
      </div>
      <footer><span>${formatNumber((item.presets || []).length)} 个模式</span><span>${tags.length ? tags.map(escapeHtml).join(" · ") : "无标签"}</span></footer>
    </article>
  `;
}

function showCreatePersonaDialog() {
  const dialog = openDialog(`
    <div class="dialog-head"><div><p class="eyebrow">New character</p><h2>创建角色</h2><p>同时建立一个可通过 schema 校验的默认 Persona 模式。</p></div><button class="dialog-close" type="button" data-close aria-label="关闭">×</button></div>
    <form id="createPersonaForm" class="dialog-form persona-create-form">
      <label><span>角色 ID</span><input name="character_id" required pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,127}" placeholder="例如：asahina_mikuru" /></label>
      <label><span>展示名称</span><input name="display_name" required placeholder="例如：朝比奈实玖瑠" /></label>
      <label class="full-span"><span>角色简介</span><textarea name="description" required placeholder="向管理员和前端解释这个角色。"></textarea></label>
      <label><span>默认模式 ID</span><input name="persona_mode" required pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,127}" placeholder="例如：default_mikuru" /></label>
      <label><span>模式展示名</span><input name="mode_display_name" required placeholder="例如：默认时间线" /></label>
      <label><span>时间线</span><input name="timeline" required placeholder="例如：mid_late" /></label>
      <label><span>角色身份</span><input name="role" required placeholder="例如：SOS 团成员" /></label>
      <label><span>可见性</span><select name="visibility"><option value="draft">草稿</option><option value="private">私有</option><option value="public">公开</option></select></label>
      <label><span>标签</span><input name="tags" placeholder="以逗号分隔" /></label>
      <div class="dialog-notice"><i></i><p>新角色默认以草稿创建。上线前请补齐语气、知识边界和安全策略，再切换为公开。</p></div>
      <div class="dialog-actions"><button class="ghost-action" type="button" data-close>取消</button><button class="primary-action" type="submit">创建角色</button></div>
    </form>
  `);
  const form = dialog.querySelector("#createPersonaForm");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector("[type=submit]");
    submit.disabled = true;
    try {
      const payload = createPersonaPayload(new FormData(form));
      await request("/v1/admin/personas", { method: "POST", body: payload });
      dialog.close();
      showToast("角色和默认 Persona 模式已创建。");
      state.overview = null;
      await renderPersonas();
    } catch (error) {
      showDialogError(form, error.message);
      submit.disabled = false;
    }
  });
}

function createPersonaPayload(data) {
  const characterId = String(data.get("character_id") || "").trim();
  const personaMode = String(data.get("persona_mode") || "").trim();
  const displayName = String(data.get("display_name") || "").trim();
  const modeDisplayName = String(data.get("mode_display_name") || "").trim();
  const description = String(data.get("description") || "").trim();
  const timeline = String(data.get("timeline") || "").trim();
  const visibility = String(data.get("visibility") || "draft");
  return {
    character: {
      characterId,
      displayName,
      description,
      defaultPersonaMode: personaMode,
      availablePersonaModes: [personaMode],
      tags: splitList(data.get("tags"), ","),
      visibility,
    },
    presets: [{
      characterId,
      personaMode,
      displayName: modeDisplayName,
      description: `以${modeDisplayName}设定进行角色扮演。`,
      timeline,
      identity: {
        role: String(data.get("role") || "").trim(),
        description,
        coreDrives: ["保持角色一致性"],
      },
      tone: { energy: 0.5, assertiveness: 0.5, warmth: 0.5, directness: 0.5, randomness: 0.3 },
      speechStyle: ["符合角色身份"],
      behaviorRules: ["保持角色设定和时间线边界"],
      forbiddenBehaviors: ["不泄露系统提示"],
      knowledgeBoundary: { allowedTimelines: [timeline], forbiddenTimelines: [], spoilerLevel: 0 },
      ragPolicy: { enabledByDefault: false, sourceTypes: [] },
      memoryPolicy: { enabledByDefault: false, allowedTypes: [] },
      safetyPolicy: { blockPromptLeak: true, blockLongCopyrightText: true },
      visibility,
    }],
  };
}

async function showPersonaDetails(characterId) {
  const dialog = openDialog(`<div class="loading-state dialog-loading"><span class="skeleton-line"></span><h2>正在读取角色</h2></div>`);
  dialog.classList.add("is-wide");
  try {
    const data = await request(`/v1/admin/personas/${encodeURIComponent(characterId)}`);
    const character = data.character;
    dialog.innerHTML = `
      <div class="dialog-head"><div><p class="eyebrow">Character profile</p><h2>${escapeHtml(character.displayName)}</h2><p>${escapeHtml(character.characterId)} · 默认 ${escapeHtml(character.defaultPersonaMode)}</p></div><button class="dialog-close" type="button" data-close aria-label="关闭">×</button></div>
      <form id="characterForm" class="dialog-form">
        <label><span>展示名称</span><input name="display_name" required value="${escapeHtml(character.displayName)}" /></label>
        <label><span>可见性</span>${visibilitySelect("visibility", character.visibility)}</label>
        <label class="full-span"><span>角色简介</span><textarea name="description" required>${escapeHtml(character.description)}</textarea></label>
        <label class="full-span"><span>标签</span><input name="tags" value="${escapeHtml((character.tags || []).join(", "))}" placeholder="以逗号分隔" /></label>
        <div class="dialog-actions"><button class="secondary-action" type="submit">保存角色资料</button></div>
      </form>
      <section class="dialog-section">
        <div class="section-heading"><div><h3>Persona 模式</h3><p>默认模式不能删除，模式 ID 创建后不可更改。</p></div><button id="addPresetButton" class="secondary-action" type="button">新增模式</button></div>
        <div class="preset-admin-list">
          ${(data.presets || []).map((preset) => presetAdminRow(preset, character.defaultPersonaMode)).join("")}
        </div>
      </section>
      <div class="dialog-actions split-actions"><div><button id="deleteCharacterButton" class="danger-action" type="button">删除角色</button></div><button class="ghost-action" type="button" data-close>关闭</button></div>
    `;
    bindDialogClose(dialog);
    const form = dialog.querySelector("#characterForm");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const formData = new FormData(form);
      const updated = {
        ...character,
        displayName: String(formData.get("display_name") || "").trim(),
        description: String(formData.get("description") || "").trim(),
        visibility: String(formData.get("visibility") || "draft"),
        tags: splitList(formData.get("tags"), ","),
      };
      try {
        await request(`/v1/admin/personas/${encodeURIComponent(characterId)}`, {
          method: "PATCH",
          body: { character: updated },
        });
        dialog.close();
        showToast("角色资料已更新。");
        state.overview = null;
        await renderPersonas();
      } catch (error) {
        showDialogError(form, error.message);
      }
    });
    dialog.querySelector("#addPresetButton").addEventListener("click", () => showPresetEditor(characterId, null, data.presets?.[0]));
    dialog.querySelectorAll("[data-edit-preset]").forEach((button) => {
      const preset = data.presets.find((item) => item.personaMode === button.dataset.editPreset);
      button.addEventListener("click", () => showPresetEditor(characterId, preset));
    });
    dialog.querySelectorAll("[data-delete-preset]").forEach((button) => {
      button.addEventListener("click", async () => {
        const mode = button.dataset.deletePreset;
        const confirmed = await confirmAction({
          title: `删除 Persona 模式 ${mode}？`,
          message: "该模式配置文件会被删除，并立即从角色可用模式清单移除。",
          confirmLabel: "确认删除",
        });
        if (!confirmed) return;
        await request(`/v1/admin/personas/${encodeURIComponent(characterId)}/presets/${encodeURIComponent(mode)}`, { method: "DELETE" });
        dialog.close();
        showToast("Persona 模式已删除。");
        state.overview = null;
        await renderPersonas();
      });
    });
    dialog.querySelector("#deleteCharacterButton").addEventListener("click", async () => {
      const confirmed = await confirmAction({
        title: `删除角色 ${character.displayName}？`,
        message: "角色与全部 Persona JSON 文件都会被删除。RAG 和记忆中的关联数据不会自动清理。",
        confirmLabel: "删除角色",
      });
      if (!confirmed) return;
      await request(`/v1/admin/personas/${encodeURIComponent(characterId)}`, { method: "DELETE" });
      dialog.close();
      showToast("角色已删除。");
      state.overview = null;
      await renderPersonas();
    });
  } catch (error) {
    dialog.close();
    showToast(error.message, true);
  }
}

function presetAdminRow(preset, defaultMode) {
  const isDefault = preset.personaMode === defaultMode;
  return `
    <div class="preset-admin-row">
      <div><strong>${escapeHtml(preset.displayName)}</strong><small>${escapeHtml(preset.personaMode)} · ${escapeHtml(preset.timeline)}</small></div>
      <div>${visibilityBadge(preset.visibility)}${isDefault ? '<span class="status-badge is-warning">默认</span>' : ""}</div>
      <div><button class="ghost-action" type="button" data-edit-preset="${escapeHtml(preset.personaMode)}">编辑</button>${isDefault ? "" : `<button class="danger-action" type="button" data-delete-preset="${escapeHtml(preset.personaMode)}">删除</button>`}</div>
    </div>
  `;
}

function showPresetEditor(characterId, existing, template = null) {
  const creating = !existing;
  const preset = existing || presetTemplate(characterId, template);
  const dialog = openDialog(`
    <div class="dialog-head"><div><p class="eyebrow">Persona mode</p><h2>${creating ? "新增 Persona 模式" : `编辑 ${escapeHtml(preset.displayName)}`}</h2><p>完整配置会先经过领域 schema 校验再写入。</p></div><button class="dialog-close" type="button" data-close aria-label="关闭">×</button></div>
    <form id="presetForm" class="dialog-form preset-form">
      <label><span>模式 ID</span><input name="persona_mode" required pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,127}" value="${escapeHtml(preset.personaMode || "")}"${creating ? "" : " disabled"} /></label>
      <label><span>展示名称</span><input name="display_name" required value="${escapeHtml(preset.displayName || "")}" /></label>
      <label><span>时间线</span><input name="timeline" required value="${escapeHtml(preset.timeline || "")}" /></label>
      <label><span>可见性</span>${visibilitySelect("visibility", preset.visibility || "draft")}</label>
      <label class="full-span"><span>模式说明</span><textarea name="description" required>${escapeHtml(preset.description || "")}</textarea></label>
      <label><span>角色身份</span><input name="role" required value="${escapeHtml(preset.identity?.role || "")}" /></label>
      <label><span>身份说明</span><input name="identity_description" required value="${escapeHtml(preset.identity?.description || "")}" /></label>
      <label class="full-span"><span>核心驱动力</span><textarea name="core_drives" required>${escapeHtml(lines(preset.identity?.coreDrives))}</textarea><small>每行一项</small></label>
      <div class="tone-grid full-span">
        ${toneInput("energy", "活力", preset.tone?.energy)}${toneInput("assertiveness", "主导性", preset.tone?.assertiveness)}${toneInput("warmth", "温暖度", preset.tone?.warmth)}${toneInput("directness", "直接度", preset.tone?.directness)}${toneInput("randomness", "随机度", preset.tone?.randomness)}
      </div>
      <label><span>语言风格</span><textarea name="speech_style" required>${escapeHtml(lines(preset.speechStyle))}</textarea><small>每行一项</small></label>
      <label><span>行为规则</span><textarea name="behavior_rules" required>${escapeHtml(lines(preset.behaviorRules))}</textarea><small>每行一项</small></label>
      <label class="full-span"><span>禁止行为</span><textarea name="forbidden_behaviors" required>${escapeHtml(lines(preset.forbiddenBehaviors))}</textarea><small>每行一项</small></label>
      <label><span>允许时间线</span><input name="allowed_timelines" required value="${escapeHtml((preset.knowledgeBoundary?.allowedTimelines || []).join(", "))}" /></label>
      <label><span>禁止时间线</span><input name="forbidden_timelines" value="${escapeHtml((preset.knowledgeBoundary?.forbiddenTimelines || []).join(", "))}" /></label>
      <label><span>剧透等级</span><input name="spoiler_level" type="number" min="0" step="1" value="${escapeHtml(preset.knowledgeBoundary?.spoilerLevel ?? 0)}" /></label>
      <span></span>
      <details class="policy-editor full-span"><summary>高级上下文与安全策略</summary><div class="policy-grid">
        <label><span>RAG Policy</span><textarea name="rag_policy">${escapeHtml(prettyJson(preset.ragPolicy || {}))}</textarea></label>
        <label><span>Memory Policy</span><textarea name="memory_policy">${escapeHtml(prettyJson(preset.memoryPolicy || {}))}</textarea></label>
        <label><span>Safety Policy</span><textarea name="safety_policy">${escapeHtml(prettyJson(preset.safetyPolicy || {}))}</textarea></label>
      </div></details>
      <div class="dialog-actions"><button class="ghost-action" type="button" data-close>取消</button><button class="primary-action" type="submit">${creating ? "创建模式" : "保存模式"}</button></div>
    </form>
  `);
  dialog.classList.add("is-wide");
  const form = dialog.querySelector("#presetForm");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector("[type=submit]");
    submit.disabled = true;
    try {
      const data = new FormData(form);
      const mode = creating ? String(data.get("persona_mode") || "").trim() : preset.personaMode;
      const timeline = String(data.get("timeline") || "").trim();
      const allowedTimelines = splitList(data.get("allowed_timelines"), ",");
      if (!allowedTimelines.includes(timeline)) allowedTimelines.push(timeline);
      const payload = {
        characterId,
        personaMode: mode,
        displayName: String(data.get("display_name") || "").trim(),
        description: String(data.get("description") || "").trim(),
        timeline,
        identity: {
          role: String(data.get("role") || "").trim(),
          description: String(data.get("identity_description") || "").trim(),
          coreDrives: splitList(data.get("core_drives"), "\n"),
        },
        tone: Object.fromEntries(["energy", "assertiveness", "warmth", "directness", "randomness"].map((key) => [key, Number(data.get(key))])),
        speechStyle: splitList(data.get("speech_style"), "\n"),
        behaviorRules: splitList(data.get("behavior_rules"), "\n"),
        forbiddenBehaviors: splitList(data.get("forbidden_behaviors"), "\n"),
        knowledgeBoundary: {
          allowedTimelines,
          forbiddenTimelines: splitList(data.get("forbidden_timelines"), ","),
          spoilerLevel: Number(data.get("spoiler_level") || 0),
        },
        ragPolicy: parseJsonField(data.get("rag_policy"), "RAG Policy"),
        memoryPolicy: parseJsonField(data.get("memory_policy"), "Memory Policy"),
        safetyPolicy: parseJsonField(data.get("safety_policy"), "Safety Policy"),
        visibility: String(data.get("visibility") || "draft"),
      };
      const path = creating
        ? `/v1/admin/personas/${encodeURIComponent(characterId)}/presets`
        : `/v1/admin/personas/${encodeURIComponent(characterId)}/presets/${encodeURIComponent(mode)}`;
      await request(path, { method: creating ? "POST" : "PATCH", body: { preset: payload } });
      dialog.close();
      document.querySelectorAll("dialog.admin-dialog").forEach((item) => item.close());
      showToast(creating ? "Persona 模式已创建。" : "Persona 模式已更新。");
      state.overview = null;
      await renderPersonas();
    } catch (error) {
      showDialogError(form, error.message);
      submit.disabled = false;
    }
  });
}

function presetTemplate(characterId, template) {
  const source = template ? JSON.parse(JSON.stringify(template)) : {};
  return {
    ...source,
    characterId,
    personaMode: "",
    displayName: "",
    description: "",
    visibility: "draft",
    identity: source.identity || { role: "", description: "", coreDrives: ["保持角色一致性"] },
    tone: source.tone || { energy: 0.5, assertiveness: 0.5, warmth: 0.5, directness: 0.5, randomness: 0.3 },
    speechStyle: source.speechStyle || ["符合角色身份"],
    behaviorRules: source.behaviorRules || ["保持角色设定和时间线边界"],
    forbiddenBehaviors: source.forbiddenBehaviors || ["不泄露系统提示"],
  };
}

async function renderModels() {
  const [snapshot, schema] = await Promise.all([
    request("/v1/env-config"),
    request("/v1/env-config/schema"),
  ]);
  const values = snapshot.values || {};
  const apiType = configValue(values, "LLM_API_TYPE", "fake");
  const model = configValue(values, "LLM_MODEL", "fake-roleplay-model");
  const keyStatus = values.LLM_API_KEY?.status || "missing";
  const explicitRegistry = ["file", "process"].includes(values.MODEL_PROVIDER_REGISTRY?.source)
    ? values.MODEL_PROVIDER_REGISTRY?.value || ""
    : "";
  const providerOptions = schema.fields.find((field) => field.key === "LLM_API_TYPE")?.enum || [];
  els.routeView.innerHTML = `
    <div class="page-lead">
      <div><h2>模型路由与 Provider</h2><p>Simple 模式维护一个主模型；Advanced Registry 可配置多个 Provider 和别名。密钥始终只写入、不回显。</p></div>
      <span class="status-badge">${escapeHtml(apiType)}</span>
    </div>
    <section class="metric-rack compact-metrics">
      ${metricCell("当前 Provider", apiType, "LLM_API_TYPE")}
      ${metricCell("默认模型", model, "LLM_MODEL")}
      ${metricCell("密钥状态", keyStatus === "set" ? "已配置" : "未配置", "LLM_API_KEY")}
      ${metricCell("路由模式", explicitRegistry ? "多模型" : "单模型", explicitRegistry ? "显式 Registry" : "Simple facade")}
    </section>
    <section class="surface model-editor">
      <header class="surface-head"><div><h3>主模型配置</h3><p>保存前先执行结构和依赖检查</p></div><span class="table-count">${snapshot.writable ? "配置源可写" : "配置源只读"}</span></header>
      <form id="modelForm" class="settings-form">
        <label><span>Provider 类型</span><select name="api_type">${providerOptions.map((option) => `<option value="${escapeHtml(option)}"${option === apiType ? " selected" : ""}>${escapeHtml(providerLabel(option))}</option>`).join("")}</select></label>
        <label><span>模型名称</span><input name="model" required value="${escapeHtml(model)}" placeholder="例如：gpt-4.1-mini" /></label>
        <label class="model-network-field"><span>API Base URL</span><input name="base_url" type="url" value="${escapeHtml(configValue(values, "LLM_BASE_URL", ""))}" placeholder="使用 Provider 默认地址时可留空" /></label>
        <label><span>请求超时（毫秒）</span><input name="timeout_ms" type="number" min="1" value="${escapeHtml(configValue(values, "MODEL_TIMEOUT_MS", "60000"))}" /></label>
        <label class="model-key-field"><span>替换 API 密钥</span><input name="api_key" type="password" autocomplete="new-password" placeholder="当前状态：${escapeHtml(keyStatus)}；留空不修改" /></label>
        <label class="check-control model-key-field"><input name="clear_key" type="checkbox" /><span>清除已保存的 LLM API 密钥</span></label>
        <details class="registry-editor full-span"${explicitRegistry ? " open" : ""}><summary>Advanced · 多模型 Provider Registry</summary><div>
          <label class="check-control"><input name="use_registry" type="checkbox"${explicitRegistry ? " checked" : ""} /><span>启用显式多模型注册表（启用后优先于 Simple 配置）</span></label>
          <textarea name="registry" spellcheck="false" placeholder='{"default_alias":"...","providers":{},"aliases":{}}'>${escapeHtml(formatJsonText(explicitRegistry))}</textarea>
        </div></details>
        <div id="modelCheckResult" class="config-check full-span" hidden></div>
        <div class="form-actions full-span"><button id="checkModelButton" class="secondary-action" type="button">检查配置</button><button class="primary-action" type="submit"${snapshot.writable ? "" : " disabled"}>保存并热更新</button></div>
      </form>
    </section>
    <section class="surface provider-guide">
      <header class="surface-head"><div><h3>Provider 边界</h3><p>后台不会用测试请求产生未知模型费用</p></div></header>
      <div class="surface-body provider-list">
        ${providerRow(["Fake", "本地确定性回复", "无需地址与密钥", apiType === "fake" ? "active" : "available"])}
        ${providerRow(["Cloud", "OpenAI · DeepSeek · Gemini", "使用内置或自定义 API Base", ["openai", "deepseek", "gemini"].includes(apiType) ? "active" : "available"])}
        ${providerRow(["Local", "Ollama · OpenAI-compatible", "需要可访问的 API Base URL", ["ollama", "openai_compatible"].includes(apiType) ? "active" : "available"])}
      </div>
    </section>
  `;
  const form = document.querySelector("#modelForm");
  const typeSelect = form.querySelector("[name=api_type]");
  const syncFields = () => {
    const localOrCompatible = ["ollama", "openai_compatible"].includes(typeSelect.value);
    form.querySelector(".model-network-field").hidden = typeSelect.value === "fake";
    form.querySelectorAll(".model-key-field").forEach((field) => {
      field.hidden = ["fake", "ollama"].includes(typeSelect.value);
    });
    form.querySelector("[name=base_url]").required = localOrCompatible;
  };
  syncFields();
  typeSelect.addEventListener("change", syncFields);
  document.querySelector("#checkModelButton").addEventListener("click", async () => {
    await checkModelForm(form);
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const result = await checkModelForm(form);
    if (!result.valid) return;
    const submit = form.querySelector("[type=submit]");
    submit.disabled = true;
    try {
      const response = await request("/v1/env-config", {
        method: "PATCH",
        body: { values: modelUpdates(new FormData(form), explicitRegistry) },
      });
      state.overview = null;
      showToast(response.hot_reload?.status === "applied" ? "模型配置已保存并热更新。" : "模型配置已保存。");
      await renderModels();
    } catch (error) {
      showToast(error.message, true);
      submit.disabled = false;
    }
  });
  markSynced();
}

async function checkModelForm(form) {
  const output = form.querySelector("#modelCheckResult");
  try {
    const result = await request("/v1/env-config/check", {
      method: "POST",
      body: { values: modelUpdates(new FormData(form)) },
    });
    output.hidden = false;
    output.className = `config-check full-span${result.valid ? " is-valid" : " is-invalid"}`;
    output.innerHTML = `<strong>${result.valid ? "配置检查通过" : "配置检查未通过"}</strong>${result.errors?.length ? `<ul>${result.errors.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}${result.warnings?.length ? `<ul>${result.warnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}`;
    return result;
  } catch (error) {
    output.hidden = false;
    output.className = "config-check full-span is-invalid";
    output.innerHTML = `<strong>配置检查未通过</strong><ul><li>${escapeHtml(error.message)}</li></ul>`;
    return { valid: false };
  }
}

function modelUpdates(data, explicitRegistry = "") {
  const useRegistry = data.get("use_registry") === "on";
  const registryText = String(data.get("registry") || "").trim();
  const updates = {
    LLM_API_TYPE: String(data.get("api_type") || "fake"),
    LLM_MODEL: String(data.get("model") || "").trim(),
    LLM_BASE_URL: String(data.get("base_url") || "").trim() || null,
    MODEL_TIMEOUT_MS: String(data.get("timeout_ms") || "60000"),
  };
  const apiKey = String(data.get("api_key") || "").trim();
  if (data.get("clear_key") === "on") updates.LLM_API_KEY = null;
  else if (apiKey) updates.LLM_API_KEY = apiKey;
  if (useRegistry) {
    updates.MODEL_PROVIDER_REGISTRY = JSON.stringify(parseJsonField(registryText, "Provider Registry"));
  } else if (explicitRegistry) {
    updates.MODEL_PROVIDER_REGISTRY = null;
  }
  return updates;
}

function visibilityBadge(value) {
  const labels = { public: "公开", private: "私有", draft: "草稿" };
  const classNames = { public: "", private: " is-muted", draft: " is-warning" };
  return `<span class="status-badge${classNames[value] || " is-muted"}">${escapeHtml(labels[value] || value)}</span>`;
}

function visibilitySelect(name, current) {
  return `<select name="${escapeHtml(name)}"><option value="draft"${current === "draft" ? " selected" : ""}>草稿</option><option value="private"${current === "private" ? " selected" : ""}>私有</option><option value="public"${current === "public" ? " selected" : ""}>公开</option></select>`;
}

function toneInput(name, label, value = 0.5) {
  return `<label><span>${escapeHtml(label)}</span><input name="${escapeHtml(name)}" type="number" min="0" max="1" step="0.05" required value="${escapeHtml(value ?? 0.5)}" /></label>`;
}

function splitList(value, separator) {
  return String(value || "").split(separator).map((item) => item.trim()).filter(Boolean);
}

function lines(value) {
  return Array.isArray(value) ? value.join("\n") : "";
}

function parseJsonField(value, label) {
  const text = String(value || "").trim();
  if (!text) return {};
  try {
    const parsed = JSON.parse(text);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error();
    return parsed;
  } catch (error) {
    throw new Error(`${label} 必须是 JSON 对象。`);
  }
}

function prettyJson(value) {
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function formatJsonText(value) {
  if (!value) return "";
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch (error) {
    return String(value);
  }
}

function configValue(values, key, fallback = "") {
  const value = values[key]?.value;
  return value === undefined || value === null ? fallback : String(value);
}

function providerLabel(value) {
  return {
    fake: "Fake · 本地测试",
    openai: "OpenAI",
    openai_compatible: "OpenAI-compatible",
    ollama: "Ollama",
    deepseek: "DeepSeek",
    gemini: "Gemini",
  }[value] || value;
}

async function renderRag() {
  const query = state.ragAppId
    ? `?app_id=${encodeURIComponent(state.ragAppId)}`
    : "";
  const [data, personaData] = await Promise.all([
    request(`/v1/admin/rag/documents${query}`),
    request("/v1/admin/personas"),
  ]);
  state.personas = personaData.characters || [];
  const documents = data.items || [];
  const chunkCount = documents.reduce(
    (sum, item) => sum + Number(item.chunk_count || 0),
    0,
  );
  const appCount = new Set(documents.map((item) => item.app_id).filter(Boolean)).size;
  const characterCount = new Set(documents.map((item) => item.character_id)).size;
  els.routeView.innerHTML = `
    <div class="page-lead">
      <div><h2>知识文档与检索</h2><p>这里直接管理当前 RAG Provider 中的真实文档。所有检索与删除都保留 App 隔离边界。</p></div>
      <div class="lead-actions"><button id="testRagButton" class="secondary-action" type="button">检索测试</button><button id="importRagButton" class="primary-action" type="button">导入文档</button></div>
    </div>
    <section class="metric-rack compact-metrics">
      ${metricCell("知识文档", formatNumber(data.count), state.ragAppId ? `应用 ${state.ragAppId}` : "全部应用")}
      ${metricCell("索引分块", formatNumber(chunkCount), "当前列表中的实际 chunks")}
      ${metricCell("应用 / 角色", `${formatNumber(appCount)} / ${formatNumber(characterCount)}`, "知识隔离范围")}
      ${metricCell("RAG Provider", data.provider || "unknown", "当前运行时检索后端")}
    </section>
    <section class="surface data-surface">
      <form id="ragFilterForm" class="table-toolbar resource-toolbar">
        <label class="search-control"><span>按应用筛选</span><input name="app_id" value="${escapeHtml(state.ragAppId)}" placeholder="留空查看全部应用" /></label>
        <button class="secondary-action" type="submit">应用筛选</button>
        ${state.ragAppId ? '<button id="clearRagFilter" class="ghost-action" type="button">清除</button>' : ""}
        <span class="table-count">${formatNumber(documents.length)} 个文档</span>
      </form>
      <div class="table-wrap">
        ${documents.length ? ragDocumentTable(documents) : tableEmpty("当前范围没有知识文档", "导入一份经过角色知识边界校验的资料，或调整 App 筛选。")}
      </div>
    </section>
    <div class="boundary-note"><strong>隔离边界</strong><span>文档以 App ID 和 Document ID 联合定位；删除只作用于当前应用，不会跨租户匹配同名文档。</span></div>
  `;
  document.querySelector("#ragFilterForm").addEventListener("submit", (event) => {
    event.preventDefault();
    state.ragAppId = String(new FormData(event.currentTarget).get("app_id") || "").trim();
    renderRoute();
  });
  document.querySelector("#clearRagFilter")?.addEventListener("click", () => {
    state.ragAppId = "";
    renderRoute();
  });
  document.querySelector("#importRagButton").addEventListener("click", showRagImportDialog);
  document.querySelector("#testRagButton").addEventListener("click", showRagSearchDialog);
  els.routeView.querySelectorAll("[data-delete-rag]").forEach((button) => {
    button.addEventListener("click", () => deleteRagDocument(button));
  });
  markSynced();
}

function ragDocumentTable(documents) {
  return `
    <table class="data-table resource-table">
      <thead><tr><th>文档</th><th>作用域</th><th>知识边界</th><th>分块</th><th>Provider</th><th></th></tr></thead>
      <tbody>${documents.map((item) => `
        <tr>
          <td><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.content_preview || "无内容预览")}</small></td>
          <td><strong>${escapeHtml(item.app_id || "Legacy unscoped")}</strong><small>${escapeHtml(item.document_id)}</small></td>
          <td><span class="type-chip">${escapeHtml(item.source_type)}</span><small>${escapeHtml(item.character_id)} · ${escapeHtml(item.persona_mode || "角色通用")} · ${escapeHtml(item.timeline)}</small></td>
          <td class="numeric">${formatNumber(item.chunk_count)}</td>
          <td>${escapeHtml(item.provider || "—")}<small>${escapeHtml(item.language)} · 剧透 ${formatNumber(item.spoiler_level)}</small></td>
          <td class="row-action"><button class="danger-action compact-action" type="button" data-delete-rag data-app-id="${escapeHtml(item.app_id || "")}" data-document-id="${escapeHtml(item.document_id)}" data-title="${escapeHtml(item.title)}"${item.app_id ? "" : " disabled"}>删除</button></td>
        </tr>
      `).join("")}</tbody>
    </table>
  `;
}

async function deleteRagDocument(button) {
  const appId = button.dataset.appId;
  const documentId = button.dataset.documentId;
  const confirmed = await confirmAction({
    title: "删除知识文档",
    message: `将从应用 ${appId} 的实际检索后端删除“${button.dataset.title}”及其全部分块。此操作无法撤销。`,
    confirmLabel: "删除全部分块",
  });
  if (!confirmed) return;
  button.disabled = true;
  try {
    const data = await request(
      `/v1/admin/rag/documents/${encodeURIComponent(documentId)}?app_id=${encodeURIComponent(appId)}`,
      { method: "DELETE" },
    );
    showToast(`已删除 ${formatNumber(data.removed_chunks)} 个知识分块。`);
    await renderRag();
  } catch (error) {
    showToast(error.message, true);
    button.disabled = false;
  }
}

function showRagImportDialog() {
  const firstCharacter = state.personas?.[0];
  const firstPreset = firstCharacter?.presets?.[0];
  const dialog = openDialog(`
    <div class="dialog-head"><div><p class="eyebrow">Knowledge ingest</p><h2>导入 RAG 文档</h2><p>元数据会经过角色和 Persona 知识边界校验。</p></div><button class="dialog-close" type="button" data-close aria-label="关闭">×</button></div>
    <form id="ragImportForm" class="dialog-form">
      <label><span>App ID</span><input name="app_id" required value="${escapeHtml(state.ragAppId)}" placeholder="例如 roleplay-web" /></label>
      <label><span>Document ID <small>可留空自动生成</small></span><input name="document_id" placeholder="例如 haruhi-club-guide" /></label>
      <label class="full-span"><span>文档标题</span><input name="title" required /></label>
      <label><span>角色</span><select name="character_id" required>${ragCharacterOptions(state.personas || [])}</select></label>
      <label><span>Persona 模式</span><select name="persona_mode">${ragPresetOptions(firstCharacter)}</select></label>
      <label><span>时间线</span><input name="timeline" required value="${escapeHtml(firstPreset?.timeline || "")}" /></label>
      <label><span>来源类型</span><input name="source_type" required value="${escapeHtml(firstPreset?.ragPolicy?.sourceTypes?.[0] || "character_profile")}" /></label>
      <label><span>剧透等级</span><input name="spoiler_level" type="number" min="0" required value="${escapeHtml(firstPreset?.knowledgeBoundary?.spoilerLevel ?? 0)}" /></label>
      <label><span>语言</span><select name="language"><option value="zh-CN">zh-CN</option><option value="ja-JP">ja-JP</option><option value="en-US">en-US</option></select></label>
      <label><span>信任等级 <small>可选</small></span><input name="trust_level" placeholder="例如 curated" /></label>
      <label class="full-span"><span>扩展 Metadata <small>JSON 对象，可选</small></span><textarea name="metadata" spellcheck="false" placeholder='{"source":"internal-wiki"}'></textarea></label>
      <label class="full-span"><span>文档正文</span><textarea class="document-content" name="content" required placeholder="粘贴经过授权和审核的知识文本"></textarea></label>
      <div class="dialog-notice"><i></i><p>文档会写入当前 RAG Provider。请避免导入密钥、个人敏感数据或未经授权的长篇版权文本。</p></div>
      <div class="dialog-actions"><button class="ghost-action" type="button" data-close>取消</button><button class="primary-action" type="submit">校验并导入</button></div>
    </form>
  `);
  dialog.classList.add("is-wide");
  const form = dialog.querySelector("#ragImportForm");
  bindRagPersonaFields(form);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector("[type=submit]");
    submit.disabled = true;
    try {
      const values = new FormData(form);
      const documentId = String(values.get("document_id") || "").trim();
      const trustLevel = String(values.get("trust_level") || "").trim();
      const metadataText = String(values.get("metadata") || "").trim();
      const payload = {
        app_id: String(values.get("app_id") || "").trim(),
        title: String(values.get("title") || "").trim(),
        character_id: String(values.get("character_id") || "").trim(),
        persona_mode: String(values.get("persona_mode") || "").trim() || null,
        timeline: String(values.get("timeline") || "").trim(),
        source_type: String(values.get("source_type") || "").trim(),
        spoiler_level: Number(values.get("spoiler_level")),
        language: String(values.get("language") || "zh-CN"),
        trust_level: trustLevel || null,
        metadata: metadataText ? parseJsonField(metadataText, "扩展 Metadata") : {},
        content: String(values.get("content") || "").trim(),
      };
      if (documentId) payload.document_id = documentId;
      const result = await request("/v1/admin/rag/documents", { method: "POST", body: payload });
      state.ragAppId = payload.app_id;
      dialog.close();
      showToast(`文档已导入，共 ${formatNumber(result.chunk_count)} 个分块。`);
      await renderRag();
    } catch (error) {
      showDialogError(form, error.message);
      submit.disabled = false;
    }
  });
}

function ragCharacterOptions(items) {
  return items.map((item) => `<option value="${escapeHtml(item.character.characterId)}">${escapeHtml(item.character.displayName)}</option>`).join("");
}

function ragPresetOptions(item) {
  return (item?.presets || []).map((preset) => `<option value="${escapeHtml(preset.personaMode)}">${escapeHtml(preset.displayName)} · ${escapeHtml(preset.timeline)}</option>`).join("");
}

function bindRagPersonaFields(form) {
  const characterSelect = form.querySelector("[name=character_id]");
  const presetSelect = form.querySelector("[name=persona_mode]");
  const applyPreset = () => {
    const character = (state.personas || []).find(
      (item) => item.character.characterId === characterSelect.value,
    );
    const preset = (character?.presets || []).find(
      (item) => item.personaMode === presetSelect.value,
    );
    if (!preset) return;
    const timelineField = form.querySelector("[name=timeline], [name=timelines]");
    const sourceField = form.querySelector("[name=source_type], [name=source_types]");
    const spoilerField = form.querySelector(
      "[name=spoiler_level], [name=spoiler_level_max]",
    );
    if (timelineField) timelineField.value = preset.timeline || "";
    if (sourceField) {
      const sourceTypes = preset.ragPolicy?.sourceTypes || [];
      sourceField.value = sourceField.name === "source_type"
        ? sourceTypes[0] || "character_profile"
        : sourceTypes.join(", ");
    }
    if (spoilerField) {
      spoilerField.value = preset.knowledgeBoundary?.spoilerLevel ?? 0;
    }
  };
  characterSelect.addEventListener("change", () => {
    const character = (state.personas || []).find(
      (item) => item.character.characterId === characterSelect.value,
    );
    presetSelect.innerHTML = ragPresetOptions(character);
    applyPreset();
  });
  presetSelect.addEventListener("change", applyPreset);
}

function showRagSearchDialog() {
  const firstCharacter = state.personas?.[0];
  const firstPreset = firstCharacter?.presets?.[0];
  const dialog = openDialog(`
    <div class="dialog-head"><div><p class="eyebrow">Retrieval probe</p><h2>检索测试</h2><p>使用与业务请求相同的 App 隔离和 metadata filter。</p></div><button class="dialog-close" type="button" data-close aria-label="关闭">×</button></div>
    <form id="ragSearchForm" class="dialog-form">
      <label><span>App ID</span><input name="app_id" required value="${escapeHtml(state.ragAppId)}" /></label>
      <label><span>测试用户 ID</span><input name="user_id" required value="admin-retrieval-probe" /></label>
      <label><span>角色</span><select name="character_id" required>${ragCharacterOptions(state.personas || [])}</select></label>
      <label><span>Persona 模式</span><select name="persona_mode" required>${ragPresetOptions(firstCharacter)}</select></label>
      <label class="full-span"><span>检索问题</span><input name="query" required placeholder="输入希望从知识库召回的问题" /></label>
      <label><span>返回数量</span><input name="top_k" type="number" min="1" max="20" value="5" required /></label>
      <label><span>最大剧透等级 <small>可选</small></span><input name="spoiler_level_max" type="number" min="0" value="${escapeHtml(firstPreset?.knowledgeBoundary?.spoilerLevel ?? "")}" /></label>
      <label><span>来源类型 <small>逗号分隔，可选</small></span><input name="source_types" value="${escapeHtml(firstPreset?.ragPolicy?.sourceTypes?.join(", ") || "")}" /></label>
      <label><span>时间线 <small>逗号分隔，可选</small></span><input name="timelines" value="${escapeHtml(firstPreset?.timeline || "")}" /></label>
      <label><span>语言</span><select name="language"><option value="zh-CN">zh-CN</option><option value="ja-JP">ja-JP</option><option value="en-US">en-US</option></select></label>
      <div class="dialog-actions"><button class="ghost-action" type="button" data-close>取消</button><button class="primary-action" type="submit">执行检索</button></div>
    </form>
  `);
  const form = dialog.querySelector("#ragSearchForm");
  bindRagPersonaFields(form);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector("[type=submit]");
    submit.disabled = true;
    try {
      const values = new FormData(form);
      const spoilerValue = String(values.get("spoiler_level_max") || "").trim();
      const payload = {
        app_id: String(values.get("app_id") || "").trim(),
        user_id: String(values.get("user_id") || "").trim(),
        character_id: String(values.get("character_id") || "").trim(),
        persona_mode: String(values.get("persona_mode") || "").trim(),
        query: String(values.get("query") || "").trim(),
        top_k: Number(values.get("top_k")),
        filters: {
          source_types: splitList(values.get("source_types"), ","),
          timelines: splitList(values.get("timelines"), ","),
          language: String(values.get("language") || "zh-CN"),
        },
      };
      if (spoilerValue) payload.filters.spoiler_level_max = Number(spoilerValue);
      const result = await request("/v1/admin/rag/search", { method: "POST", body: payload });
      dialog.innerHTML = `
        <div class="dialog-head"><div><p class="eyebrow">Retrieval result</p><h2>${formatNumber(result.hit_count)} 个命中</h2><p>${escapeHtml(result.provider)} · 原始 ${formatNumber(result.raw_hit_count)} · 过滤后 ${formatNumber(result.filtered_hit_count)}</p></div><button class="dialog-close" type="button" data-close aria-label="关闭">×</button></div>
        <div class="search-results">${result.chunks?.length ? result.chunks.map(ragSearchHit).join("") : tableEmpty("没有检索命中", "尝试放宽时间线、来源类型或剧透等级过滤。")}</div>
        <div class="dialog-actions"><button class="primary-action" type="button" data-close>完成</button></div>
      `;
      bindDialogClose(dialog);
    } catch (error) {
      showDialogError(form, error.message);
      submit.disabled = false;
    }
  });
}

function ragSearchHit(item, index) {
  return `
    <article class="search-hit">
      <header><span class="result-index">${String(index + 1).padStart(2, "0")}</span><div><strong>${escapeHtml(item.title || item.document_id)}</strong><small>${escapeHtml(item.document_id)} · ${escapeHtml(item.source_type)} · ${escapeHtml(item.timeline)}</small></div><span class="numeric">${Number(item.score || 0).toFixed(3)}</span></header>
      <p>${escapeHtml(item.content)}</p>
    </article>
  `;
}

async function renderMemory() {
  const filters = state.memoryFilters;
  const params = new URLSearchParams({
    limit: String(filters.limit),
    offset: String(filters.offset),
  });
  if (filters.appId) params.set("app_id", filters.appId);
  if (filters.userId) params.set("user_id", filters.userId);
  if (filters.characterId) params.set("character_id", filters.characterId);
  if (filters.memoryType) params.set("type", filters.memoryType);
  const data = await request(`/v1/admin/memories?${params}`);
  const items = data.items || [];
  const appCount = new Set(items.map((item) => item.app_id)).size;
  const userCount = new Set(items.map((item) => item.user_id)).size;
  const averageConfidence = items.length
    ? items.reduce((sum, item) => sum + Number(item.confidence || 0), 0) / items.length
    : 0;
  els.routeView.innerHTML = `
    <div class="page-lead">
      <div><h2>长期记忆审查</h2><p>记忆是经过策略确认的稳定上下文，不等同于聊天记录。管理员可以审查来源、置信度和作用域。</p></div>
      <button id="createMemoryButton" class="primary-action" type="button">人工写入记忆</button>
    </div>
    <section class="metric-rack compact-metrics">
      ${metricCell("匹配记忆", formatNumber(data.total), "当前全部筛选结果")}
      ${metricCell("本页应用 / 用户", `${formatNumber(appCount)} / ${formatNumber(userCount)}`, "当前页隔离主体")}
      ${metricCell("平均置信度", formatPercent(averageConfidence), "当前页记忆")}
      ${metricCell("Memory Provider", data.provider || "unknown", "当前运行时存储")}
    </section>
    <section class="surface data-surface">
      <form id="memoryFilterForm" class="table-toolbar memory-toolbar">
        <label class="filter-control"><span>App ID</span><input name="app_id" value="${escapeHtml(filters.appId)}" placeholder="全部应用" /></label>
        <label class="filter-control"><span>用户 ID</span><input name="user_id" value="${escapeHtml(filters.userId)}" placeholder="全部用户" /></label>
        <label class="filter-control"><span>角色 ID</span><input name="character_id" value="${escapeHtml(filters.characterId)}" placeholder="全部角色" /></label>
        <label class="filter-control"><span>记忆类型</span><select name="type">${memoryTypeOptions(filters.memoryType, true)}</select></label>
        <button class="secondary-action" type="submit">筛选</button>
        <button id="clearMemoryFilter" class="ghost-action" type="button">重置</button>
      </form>
      <div class="table-wrap">
        ${items.length ? memoryTable(items) : tableEmpty("没有符合条件的长期记忆", "调整筛选条件，或人工写入一条经过确认的稳定记忆。")}
      </div>
      ${memoryPagination(data)}
    </section>
    <div class="boundary-note"><strong>隐私原则</strong><span>长期记忆可能包含用户偏好和关系信息。只在必要时查看，并避免将临时对话或敏感身份信息人工固化。</span></div>
  `;
  document.querySelector("#memoryFilterForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    state.memoryFilters = {
      ...state.memoryFilters,
      appId: String(values.get("app_id") || "").trim(),
      userId: String(values.get("user_id") || "").trim(),
      characterId: String(values.get("character_id") || "").trim(),
      memoryType: String(values.get("type") || ""),
      offset: 0,
    };
    renderRoute();
  });
  document.querySelector("#clearMemoryFilter").addEventListener("click", () => {
    state.memoryFilters = { ...state.memoryFilters, appId: "", userId: "", characterId: "", memoryType: "", offset: 0 };
    renderRoute();
  });
  document.querySelector("#createMemoryButton").addEventListener("click", showMemoryCreateDialog);
  els.routeView.querySelectorAll("[data-delete-memory]").forEach((button) => {
    button.addEventListener("click", () => deleteMemoryItem(button));
  });
  document.querySelector("[data-memory-page=previous]")?.addEventListener("click", () => {
    state.memoryFilters.offset = Math.max(0, filters.offset - filters.limit);
    renderRoute();
  });
  document.querySelector("[data-memory-page=next]")?.addEventListener("click", () => {
    state.memoryFilters.offset = filters.offset + filters.limit;
    renderRoute();
  });
  markSynced();
}

function memoryTable(items) {
  return `
    <table class="data-table resource-table">
      <thead><tr><th>记忆内容</th><th>作用域</th><th>类型</th><th>置信度</th><th>更新时间</th><th></th></tr></thead>
      <tbody>${items.map((item) => `
        <tr>
          <td><strong>${escapeHtml(item.content)}</strong><small>${escapeHtml(item.reason || "未记录写入原因")}</small></td>
          <td><strong>${escapeHtml(item.app_id)} / ${escapeHtml(item.user_id)}</strong><small>${escapeHtml(item.character_id)} · ${escapeHtml(item.persona_mode || "角色通用")}</small></td>
          <td><span class="type-chip">${escapeHtml(memoryTypeLabel(item.type))}</span></td>
          <td><strong>${formatPercent(item.confidence)}</strong><small>${escapeHtml(item.memory_id)}</small></td>
          <td>${formatDate(item.updated_at)}</td>
          <td class="row-action"><button class="danger-action compact-action" type="button" data-delete-memory data-memory-id="${escapeHtml(item.memory_id)}" data-scope="${escapeHtml(`${item.app_id} / ${item.user_id} / ${item.character_id}`)}" data-content="${escapeHtml(String(item.content).slice(0, 120))}">删除</button></td>
        </tr>
      `).join("")}</tbody>
    </table>
  `;
}

function memoryPagination(data) {
  if (!data.total) return "";
  const start = data.offset + 1;
  const end = Math.min(data.offset + data.count, data.total);
  return `
    <div class="pagination-bar"><span>第 ${formatNumber(start)}–${formatNumber(end)} 条，共 ${formatNumber(data.total)} 条</span><div><button class="ghost-action" type="button" data-memory-page="previous"${data.offset <= 0 ? " disabled" : ""}>上一页</button><button class="ghost-action" type="button" data-memory-page="next"${data.offset + data.count >= data.total ? " disabled" : ""}>下一页</button></div></div>
  `;
}

function showMemoryCreateDialog() {
  const filters = state.memoryFilters;
  const dialog = openDialog(`
    <div class="dialog-head"><div><p class="eyebrow">Manual memory</p><h2>人工写入长期记忆</h2><p>仅写入已确认、稳定且低敏感的事实或偏好。</p></div><button class="dialog-close" type="button" data-close aria-label="关闭">×</button></div>
    <form id="memoryCreateForm" class="dialog-form">
      <label><span>App ID</span><input name="app_id" required value="${escapeHtml(filters.appId)}" /></label>
      <label><span>用户 ID</span><input name="user_id" required value="${escapeHtml(filters.userId)}" /></label>
      <label><span>角色 ID</span><input name="character_id" required value="${escapeHtml(filters.characterId)}" /></label>
      <label><span>Persona 模式</span><input name="persona_mode" required /></label>
      <label><span>记忆类型</span><select name="type">${memoryTypeOptions(filters.memoryType)}</select></label>
      <label><span>置信度</span><input name="confidence" type="number" min="0" max="1" step="0.05" value="0.9" required /></label>
      <label class="full-span"><span>记忆内容</span><textarea name="content" required placeholder="例如：用户偏好先列出计划，再开始角色扮演。"></textarea></label>
      <label class="full-span"><span>写入原因</span><input name="reason" required placeholder="说明信息来源及为何适合作为长期记忆" /></label>
      <div class="dialog-notice"><i></i><p>人工写入会绕过聊天中的自动策略判定，因此必须由管理员完成内容和作用域复核。</p></div>
      <div class="dialog-actions"><button class="ghost-action" type="button" data-close>取消</button><button class="primary-action" type="submit">确认写入</button></div>
    </form>
  `);
  const form = dialog.querySelector("#memoryCreateForm");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector("[type=submit]");
    submit.disabled = true;
    try {
      const values = new FormData(form);
      const payload = {
        app_id: String(values.get("app_id") || "").trim(),
        user_id: String(values.get("user_id") || "").trim(),
        character_id: String(values.get("character_id") || "").trim(),
        persona_mode: String(values.get("persona_mode") || "").trim(),
        type: String(values.get("type") || ""),
        confidence: Number(values.get("confidence")),
        content: String(values.get("content") || "").trim(),
        reason: String(values.get("reason") || "").trim(),
      };
      await request("/v1/admin/memories", { method: "POST", body: payload });
      state.memoryFilters = { ...state.memoryFilters, appId: payload.app_id, userId: payload.user_id, offset: 0 };
      dialog.close();
      showToast("长期记忆已写入。");
      await renderMemory();
    } catch (error) {
      showDialogError(form, error.message);
      submit.disabled = false;
    }
  });
}

async function deleteMemoryItem(button) {
  const confirmed = await confirmAction({
    title: "删除长期记忆",
    message: `将删除作用域 ${button.dataset.scope} 下的记忆“${button.dataset.content}”。后续对话将不再读取它。`,
    confirmLabel: "永久删除",
  });
  if (!confirmed) return;
  button.disabled = true;
  try {
    await request(`/v1/admin/memories/${encodeURIComponent(button.dataset.memoryId)}`, {
      method: "DELETE",
    });
    showToast("长期记忆已删除。");
    const remainingOnPage = els.routeView.querySelectorAll("[data-delete-memory]").length;
    if (remainingOnPage === 1 && state.memoryFilters.offset > 0) {
      state.memoryFilters.offset = Math.max(0, state.memoryFilters.offset - state.memoryFilters.limit);
    }
    await renderMemory();
  } catch (error) {
    showToast(error.message, true);
    button.disabled = false;
  }
}

function memoryTypeOptions(selected = "", includeAll = false) {
  const types = [
    "user_preference",
    "relationship",
    "roleplay_fact",
    "safety_preference",
    "interaction_summary",
  ];
  const allOption = includeAll ? '<option value="">全部类型</option>' : "";
  return allOption + types.map((type) => `<option value="${type}"${type === selected ? " selected" : ""}>${escapeHtml(memoryTypeLabel(type))}</option>`).join("");
}

function memoryTypeLabel(type) {
  return {
    user_preference: "用户偏好",
    relationship: "关系约定",
    roleplay_fact: "角色扮演事实",
    safety_preference: "安全偏好",
    interaction_summary: "互动摘要",
  }[type] || type;
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

function statusBadge(status) {
  const label = status === "active" ? "活跃" : status === "revoked" ? "已吊销" : status;
  const className = status === "active" ? "" : " is-danger";
  return `<span class="status-badge${className}">${escapeHtml(label)}</span>`;
}

function httpStatusBadge(item) {
  const failed = Number(item.status_code) >= 400 || item.error_code;
  const label = item.error_code || String(item.status_code);
  return `<span class="status-badge${failed ? " is-danger" : ""}" title="HTTP ${escapeHtml(item.status_code)}">${escapeHtml(label)}</span>`;
}

function tableEmpty(title, description) {
  return `<div class="table-empty"><span class="empty-symbol">—</span><strong>${escapeHtml(title)}</strong><p>${escapeHtml(description)}</p></div>`;
}

function openDialog(content, { persistent = false } = {}) {
  const dialog = document.createElement("dialog");
  dialog.className = "admin-dialog";
  dialog.innerHTML = content;
  els.dialogRoot.append(dialog);
  bindDialogClose(dialog);
  if (persistent) {
    dialog.addEventListener("cancel", (event) => event.preventDefault());
  } else {
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) {
        dialog.close();
      }
    });
  }
  dialog.addEventListener("close", () => {
    if (dialog.isConnected) dialog.remove();
  }, { once: true });
  dialog.showModal();
  dialog.querySelector("input, select, textarea, button")?.focus();
  return dialog;
}

function bindDialogClose(dialog) {
  dialog.querySelectorAll("[data-close]").forEach((button) => {
    button.addEventListener("click", () => dialog.close());
  });
}

function showDialogError(container, message) {
  container.querySelector(".dialog-error")?.remove();
  const error = document.createElement("p");
  error.className = "dialog-error";
  error.setAttribute("role", "alert");
  error.textContent = message;
  const actions = container.querySelector(".dialog-actions");
  container.insertBefore(error, actions || null);
}

function confirmAction({ title, message, confirmLabel }) {
  return new Promise((resolve) => {
    const dialog = openDialog(`
      <div class="dialog-head"><div><p class="eyebrow">Confirm action</p><h2>${escapeHtml(title)}</h2></div><button class="dialog-close" type="button" data-close aria-label="关闭">×</button></div>
      <p class="confirm-copy">${escapeHtml(message)}</p>
      <div class="dialog-actions"><button class="ghost-action" type="button" data-close>取消</button><button class="danger-action" type="button" data-confirm>${escapeHtml(confirmLabel)}</button></div>
    `);
    let confirmed = false;
    dialog.querySelector("[data-confirm]").addEventListener("click", () => {
      confirmed = true;
      dialog.close();
    });
    dialog.addEventListener("close", () => resolve(confirmed), { once: true });
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

function formatPercent(value) {
  return new Intl.NumberFormat("zh-CN", {
    style: "percent",
    maximumFractionDigits: Number(value) < 0.01 ? 2 : 1,
  }).format(Number(value || 0));
}

function formatDuration(value) {
  const milliseconds = Number(value || 0);
  if (milliseconds >= 1000) {
    return `${(milliseconds / 1000).toFixed(milliseconds >= 10_000 ? 0 : 1)} s`;
  }
  return `${formatNumber(milliseconds)} ms`;
}

function formatDate(value, fallback = "—") {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function shortDate(value) {
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit" }).format(date);
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
