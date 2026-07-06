const state = {
  baseUrl: window.location.origin,
  apiKey: "",
  schema: null,
  snapshot: null,
  selectedGroup: "",
  draft: {},
  lastCheck: null,
};

const els = {
  apiBaseInput: document.querySelector("#apiBaseInput"),
  apiKeyInput: document.querySelector("#apiKeyInput"),
  connectButton: document.querySelector("#connectButton"),
  connectionStatus: document.querySelector("#connectionStatus"),
  groupNav: document.querySelector("#groupNav"),
  fieldCount: document.querySelector("#fieldCount"),
  configSource: document.querySelector("#configSource"),
  draftBadge: document.querySelector("#draftBadge"),
  checkAllButton: document.querySelector("#checkAllButton"),
  saveButton: document.querySelector("#saveButton"),
  fieldGrid: document.querySelector("#fieldGrid"),
  writableBadge: document.querySelector("#writableBadge"),
  snapshotMeta: document.querySelector("#snapshotMeta"),
  diffCount: document.querySelector("#diffCount"),
  diffList: document.querySelector("#diffList"),
  checkBadge: document.querySelector("#checkBadge"),
  checkOutput: document.querySelector("#checkOutput"),
};

function init() {
  els.apiBaseInput.value = state.baseUrl;
  bindEvents();
  renderEmpty();
}

function bindEvents() {
  els.connectButton.addEventListener("click", loadConfig);
  els.checkAllButton.addEventListener("click", checkDraft);
  els.saveButton.addEventListener("click", saveDraft);
}

async function loadConfig() {
  syncConnection();
  setStatus("loading");
  try {
    const [schema, snapshot] = await Promise.all([
      api("/v1/env-config/schema"),
      api("/v1/env-config"),
    ]);
    state.schema = schema.data;
    state.snapshot = snapshot.data;
    state.selectedGroup = state.schema.groups[0] || "";
    state.draft = {};
    state.lastCheck = null;
    setStatus("ready");
    render();
  } catch (error) {
    setStatus("error");
    renderError(error.message);
  }
}

function render() {
  if (!state.schema || !state.snapshot) {
    renderEmpty();
    return;
  }
  els.fieldCount.textContent = String(state.schema.fields.length);
  els.configSource.textContent = state.snapshot.source;
  els.writableBadge.textContent = state.snapshot.writable ? "writable" : "read-only";
  renderSnapshotMeta();
  renderGroups();
  renderFields();
  renderDiff();
  renderCheck();
}

function renderEmpty() {
  els.fieldGrid.innerHTML = `
    <div class="empty-state">
      <h2>Env Config</h2>
      <p>Enter the trusted admin key and connect to load the redacted .env snapshot.</p>
    </div>
  `;
  els.saveButton.disabled = true;
  els.checkAllButton.disabled = true;
}

function renderError(message) {
  els.fieldGrid.innerHTML = `
    <div class="empty-state">
      <h2>Cannot Load Config</h2>
      <p>${escapeHtml(message)}</p>
    </div>
  `;
}

function renderSnapshotMeta() {
  const unknown = state.snapshot.unknown_keys || [];
  els.snapshotMeta.replaceChildren(
    metaLine("Source", state.snapshot.source),
    metaLine("Known fields", String(state.schema.fields.length)),
    metaLine("Unknown keys", String(unknown.length)),
  );
}

function renderGroups() {
  els.groupNav.replaceChildren(
    ...state.schema.groups.map((group) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "group-button";
      if (group === state.selectedGroup) {
        button.classList.add("active");
      }
      button.textContent = group;
      button.addEventListener("click", () => {
        state.selectedGroup = group;
        renderGroups();
        renderFields();
      });
      return button;
    }),
  );
}

function renderFields() {
  const fields = state.schema.fields.filter((field) => field.group === state.selectedGroup);
  els.fieldGrid.replaceChildren(...fields.map(fieldCard));
}

function fieldCard(field) {
  const card = document.createElement("article");
  card.className = "config-field-card";
  card.dataset.key = field.key;
  const snapshot = valueSnapshot(field.key);
  card.innerHTML = `
    <div class="config-field-head">
      <div>
        <h3>${escapeHtml(field.key)}</h3>
        <p>${escapeHtml(field.description || "")}</p>
      </div>
      <div class="field-pills">
        ${field.secret ? '<span class="status-pill">secret</span>' : ""}
        ${field.hot_reload ? '<span class="status-pill">hot</span>' : ""}
        ${field.restart_required ? '<span class="status-pill">restart</span>' : ""}
      </div>
    </div>
    <div class="config-control"></div>
    <div class="field-footer">
      <span class="field-status">${escapeHtml(statusText(field, snapshot))}</span>
      <span class="field-buttons"></span>
    </div>
  `;
  card.querySelector(".config-control").append(controlForField(field, snapshot));
  const buttons = card.querySelector(".field-buttons");
  buttons.append(
    actionButton("Check", () => checkField(field.key), "check"),
    actionButton("Clear", () => setDraft(field.key, ""), "clear"),
    actionButton("Remove", () => setDraft(field.key, null), "remove"),
  );
  return card;
}

function controlForField(field, snapshot) {
  if (field.secret) {
    const input = document.createElement("input");
    input.type = "password";
    input.autocomplete = "off";
    input.placeholder = `${snapshot.status || "missing"}; enter replacement`;
    input.addEventListener("input", () => {
      if (input.value) {
        setDraft(field.key, input.value);
      } else if (field.key in state.draft) {
        delete state.draft[field.key];
        renderDraftOnly();
      }
    });
    return input;
  }
  if (field.type === "enum" || field.type === "bool") {
    const select = document.createElement("select");
    const options = field.type === "bool" ? ["true", "false"] : field.enum || [];
    select.replaceChildren(
      ...options.map((value) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        option.selected = value === String(snapshot.value || field.default || "");
        return option;
      }),
    );
    select.addEventListener("change", () => setDraft(field.key, select.value));
    return select;
  }
  if (field.type === "json") {
    const textarea = document.createElement("textarea");
    textarea.rows = 7;
    textarea.value = String(snapshot.value || "");
    textarea.spellcheck = false;
    textarea.addEventListener("input", () => setDraft(field.key, textarea.value));
    return textarea;
  }
  const input = document.createElement("input");
  input.type = field.type === "int" ? "number" : "text";
  if (field.min !== undefined) {
    input.min = String(field.min);
  }
  if (field.max !== undefined) {
    input.max = String(field.max);
  }
  input.value = String(snapshot.value || "");
  input.addEventListener("input", () => setDraft(field.key, input.value));
  return input;
}

function setDraft(key, value) {
  const field = fieldByKey(key);
  const snapshot = valueSnapshot(key);
  const current = field.secret ? "" : String(snapshot.value || "");
  if (!field.secret && value !== null && String(value) === current) {
    delete state.draft[key];
  } else {
    state.draft[key] = value;
  }
  renderDraftOnly();
}

function renderDraftOnly() {
  els.draftBadge.textContent = draftKeys().length ? "dirty" : "clean";
  els.saveButton.disabled = !draftKeys().length || !state.snapshot?.writable;
  els.checkAllButton.disabled = !draftKeys().length;
  renderDiff();
}

function renderDiff() {
  const keys = draftKeys();
  els.diffCount.textContent = String(keys.length);
  if (!keys.length) {
    els.diffList.className = "diff-list empty-panel";
    els.diffList.textContent = "No draft changes";
    return;
  }
  els.diffList.className = "diff-list";
  els.diffList.replaceChildren(
    ...keys.map((key) => {
      const field = fieldByKey(key);
      const value = state.draft[key];
      const item = document.createElement("div");
      item.className = "diff-item";
      item.innerHTML = `
        <div class="source-title">${escapeHtml(key)}</div>
        <div class="source-meta">${escapeHtml(diffText(field, value))}</div>
      `;
      return item;
    }),
  );
}

function renderCheck() {
  const result = state.lastCheck;
  if (!result) {
    els.checkBadge.textContent = "idle";
    els.checkOutput.className = "check-output empty-panel";
    els.checkOutput.textContent = "No check result";
    return;
  }
  els.checkBadge.textContent = result.valid ? "valid" : "invalid";
  els.checkOutput.className = "check-output";
  const lines = [];
  for (const error of result.errors || []) {
    lines.push(`ERROR ${error}`);
  }
  for (const warning of result.warnings || []) {
    lines.push(`WARN ${warning}`);
  }
  if (!lines.length) {
    lines.push("All checks passed.");
  }
  els.checkOutput.textContent = lines.join("\n");
}

async function checkField(key) {
  try {
    const value = key in state.draft ? state.draft[key] : valueSnapshot(key).value || "";
    const response = await api("/v1/env-config/check", {
      method: "POST",
      body: { key, value },
    });
    state.lastCheck = response.data;
    renderCheck();
  } catch (error) {
    showCheckError(error.message);
  }
}

async function checkDraft() {
  if (!draftKeys().length) {
    return;
  }
  try {
    const response = await api("/v1/env-config/check", {
      method: "POST",
      body: { values: state.draft },
    });
    state.lastCheck = response.data;
    renderCheck();
  } catch (error) {
    showCheckError(error.message);
  }
}

async function saveDraft() {
  if (!draftKeys().length) {
    return;
  }
  try {
    const response = await api("/v1/env-config", {
      method: "PATCH",
      body: { values: state.draft },
    });
    state.snapshot = response.data.config;
    state.lastCheck = response.data.check;
    state.draft = {};
    render();
    toast(`Saved. Hot reload: ${response.data.hot_reload.status}`);
  } catch (error) {
    showCheckError(error.message);
  }
}

function showCheckError(message) {
  state.lastCheck = {
    valid: false,
    errors: [message],
    warnings: [],
  };
  renderCheck();
}

function syncConnection() {
  state.baseUrl = els.apiBaseInput.value.trim().replace(/\/$/, "") || window.location.origin;
  state.apiKey = els.apiKeyInput.value.trim();
}

async function api(path, options = {}) {
  const response = await fetch(`${state.baseUrl}${path}`, {
    method: options.method || "GET",
    headers: {
      "Content-Type": "application/json",
      "X-Request-Id": `config-${Date.now()}`,
      ...(state.apiKey ? { Authorization: `Bearer ${state.apiKey}` } : {}),
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok || !payload?.ok) {
    const error = payload?.error;
    throw new Error(error?.message || `HTTP ${response.status}`);
  }
  return payload;
}

function valueSnapshot(key) {
  return state.snapshot?.values?.[key] || {};
}

function fieldByKey(key) {
  return state.schema.fields.find((field) => field.key === key);
}

function draftKeys() {
  return Object.keys(state.draft);
}

function statusText(field, snapshot) {
  if (field.secret) {
    return `secret ${snapshot.status || "missing"} from ${snapshot.source || "missing"}`;
  }
  return `${snapshot.status || "missing"} from ${snapshot.source || "missing"}`;
}

function diffText(field, value) {
  if (value === null) {
    return field.secret ? "remove secret key" : "remove key";
  }
  if (field.secret) {
    return value ? "set/replace secret" : "set empty secret";
  }
  return `set to ${value === "" ? "(empty)" : value}`;
}

function metaLine(label, value) {
  const row = document.createElement("div");
  row.className = "meta-line";
  row.innerHTML = `<span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>`;
  return row;
}

function actionButton(label, onClick, action) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "mini-button";
  button.dataset.action = action;
  button.textContent = label;
  button.addEventListener("click", onClick);
  return button;
}

function setStatus(value) {
  els.connectionStatus.textContent = value;
}

function toast(message) {
  const node = document.createElement("div");
  node.className = "toast";
  node.textContent = message;
  document.body.append(node);
  window.setTimeout(() => node.remove(), 3200);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

init();
