const state = {
  csrfToken: "",
  route: "overview",
  loading: false,
  overview: null,
  tokens: null,
  usageDays: 30,
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
