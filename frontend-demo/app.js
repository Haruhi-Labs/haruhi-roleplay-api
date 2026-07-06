const state = {
  baseUrl: window.location.origin,
  apiKey: "",
  characters: [],
  selectedCharacterId: "",
  selectedMode: "",
  sessionId: "",
  messages: [],
  sources: [],
  debug: null,
  busy: false,
};

const els = {
  apiBaseInput: document.querySelector("#apiBaseInput"),
  apiKeyInput: document.querySelector("#apiKeyInput"),
  connectButton: document.querySelector("#connectButton"),
  newSessionButton: document.querySelector("#newSessionButton"),
  connectionStatus: document.querySelector("#connectionStatus"),
  characterList: document.querySelector("#characterList"),
  characterCount: document.querySelector("#characterCount"),
  sessionBadge: document.querySelector("#sessionBadge"),
  userIdInput: document.querySelector("#userIdInput"),
  appIdInput: document.querySelector("#appIdInput"),
  activeCharacterName: document.querySelector("#activeCharacterName"),
  activeModeName: document.querySelector("#activeModeName"),
  personaAvatar: document.querySelector("#personaAvatar"),
  modeSelect: document.querySelector("#modeSelect"),
  modelInput: document.querySelector("#modelInput"),
  streamToggle: document.querySelector("#streamToggle"),
  sessionToggle: document.querySelector("#sessionToggle"),
  ragToggle: document.querySelector("#ragToggle"),
  memoryToggle: document.querySelector("#memoryToggle"),
  debugToggle: document.querySelector("#debugToggle"),
  messageList: document.querySelector("#messageList"),
  composerForm: document.querySelector("#composerForm"),
  messageInput: document.querySelector("#messageInput"),
  sendButton: document.querySelector("#sendButton"),
  sourceList: document.querySelector("#sourceList"),
  sourceCount: document.querySelector("#sourceCount"),
  ragStatus: document.querySelector("#ragStatus"),
  ragTitleInput: document.querySelector("#ragTitleInput"),
  ragContentInput: document.querySelector("#ragContentInput"),
  ragImportButton: document.querySelector("#ragImportButton"),
  debugOutput: document.querySelector("#debugOutput"),
  latencyBadge: document.querySelector("#latencyBadge"),
};

function init() {
  els.apiBaseInput.value = state.baseUrl;
  bindEvents();
  renderMessages();
  renderSources();
  loadCatalog();
}

function bindEvents() {
  els.connectButton.addEventListener("click", () => {
    syncConnectionFields();
    loadCatalog();
  });
  els.newSessionButton.addEventListener("click", () => createSession({ force: true }));
  els.modeSelect.addEventListener("change", () => {
    state.selectedMode = els.modeSelect.value;
    state.sessionId = "";
    renderActivePersona();
    renderSession();
  });
  els.composerForm.addEventListener("submit", (event) => {
    event.preventDefault();
    sendMessage();
  });
  els.messageInput.addEventListener("input", autoSizeComposer);
  els.messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  });
  els.ragImportButton.addEventListener("click", importRagDocument);
}

function syncConnectionFields() {
  state.baseUrl = els.apiBaseInput.value.trim().replace(/\/$/, "") || window.location.origin;
  state.apiKey = els.apiKeyInput.value.trim();
}

async function loadCatalog() {
  syncConnectionFields();
  setStatus("loading");
  try {
    const response = await api("/v1/personas");
    state.characters = response.data.characters || [];
    if (!state.selectedCharacterId && state.characters.length > 0) {
      const first = state.characters[0];
      state.selectedCharacterId = first.character_id;
      state.selectedMode = first.default_persona_mode;
    }
    renderCharacters();
    renderActivePersona();
    setStatus("ready");
  } catch (error) {
    setStatus("error");
    toast(error.message);
  }
}

function renderCharacters() {
  els.characterCount.textContent = String(state.characters.length);
  els.characterList.replaceChildren();
  for (const character of state.characters) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "character-button";
    if (character.character_id === state.selectedCharacterId) {
      button.classList.add("active");
    }
    button.innerHTML = `
      <span class="character-initial">${escapeHtml(initial(character.display_name))}</span>
      <span>
        <span class="character-name">${escapeHtml(character.display_name)}</span>
        <span class="character-meta">${escapeHtml(character.description || "")}</span>
      </span>
    `;
    button.addEventListener("click", () => {
      state.selectedCharacterId = character.character_id;
      state.selectedMode = character.default_persona_mode;
      state.sessionId = "";
      renderCharacters();
      renderActivePersona();
      renderSession();
    });
    els.characterList.append(button);
  }
}

function renderActivePersona() {
  const character = selectedCharacter();
  if (!character) {
    els.activeCharacterName.textContent = "Roleplay Demo";
    els.activeModeName.textContent = "No catalog loaded";
    els.modeSelect.replaceChildren();
    return;
  }
  const modes = character.modes || [];
  const selected = modes.find((mode) => mode.persona_mode === state.selectedMode) || modes[0];
  if (selected) {
    state.selectedMode = selected.persona_mode;
  }
  els.activeCharacterName.textContent = character.display_name;
  els.activeModeName.textContent = selected
    ? `${selected.display_name} · ${selected.timeline}`
    : character.description;
  els.personaAvatar.textContent = initial(character.display_name);
  els.modeSelect.replaceChildren(
    ...modes.map((mode) => {
      const option = document.createElement("option");
      option.value = mode.persona_mode;
      option.textContent = mode.display_name;
      option.selected = mode.persona_mode === state.selectedMode;
      return option;
    }),
  );
}

function renderMessages() {
  els.messageList.replaceChildren();
  if (state.messages.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.innerHTML = `
      <h2>今天要调查什么？</h2>
      <p>选择角色和 preset 后发送消息。Stream、RAG、Memory 和 Session 都会通过当前本地 Roleplay API 调度。</p>
    `;
    els.messageList.append(empty);
    return;
  }
  for (const message of state.messages) {
    els.messageList.append(messageNode(message));
  }
  els.messageList.scrollTop = els.messageList.scrollHeight;
}

function messageNode(message) {
  const row = document.createElement("article");
  row.className = `message ${message.role}`;
  row.dataset.messageId = message.id;
  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.textContent = message.role === "user" ? "U" : initial(selectedCharacter()?.display_name || "A");
  const body = document.createElement("div");
  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.textContent = message.content;
  body.append(bubble);
  if (message.meta) {
    const meta = document.createElement("div");
    meta.className = "message-meta";
    meta.textContent = message.meta;
    body.append(meta);
  }
  row.append(avatar, body);
  return row;
}

function renderSources() {
  els.sourceCount.textContent = String(state.sources.length);
  if (state.sources.length === 0) {
    els.sourceList.className = "source-list empty-panel";
    els.sourceList.textContent = "No sources";
    return;
  }
  els.sourceList.className = "source-list";
  els.sourceList.replaceChildren(
    ...state.sources.map((source) => {
      const item = document.createElement("div");
      item.className = "source-item";
      item.innerHTML = `
        <div class="source-title">${escapeHtml(source.document_id || source.chunk_id || "source")}</div>
        <div class="source-meta">
          ${escapeHtml(source.source_type || "source")} · ${escapeHtml(source.timeline || "timeline")} · score ${formatScore(source.score)}
        </div>
      `;
      return item;
    }),
  );
}

function renderDebug(debug) {
  state.debug = debug || null;
  els.debugOutput.textContent = JSON.stringify(state.debug || {}, null, 2);
  const latency = state.debug?.latencyMs ?? state.debug?.latency_ms ?? 0;
  els.latencyBadge.textContent = `${latency}ms`;
}

function renderSession() {
  els.sessionBadge.textContent = state.sessionId ? "active" : "new";
}

async function sendMessage() {
  if (state.busy) {
    return;
  }
  syncConnectionFields();
  const content = els.messageInput.value.trim();
  if (!content) {
    return;
  }
  const character = selectedCharacter();
  if (!character || !state.selectedMode) {
    toast("Catalog is not ready.");
    return;
  }
  state.busy = true;
  els.sendButton.disabled = true;
  els.messageInput.value = "";
  autoSizeComposer();
  pushMessage("user", content);
  const assistantId = pushMessage("assistant", "", "streaming");

  try {
    if (els.sessionToggle.checked) {
      await createSession({ force: false });
    }
    const body = chatBody(content);
    if (els.streamToggle.checked) {
      await streamChat(body, assistantId);
    } else {
      const response = await api("/v1/chat", {
        method: "POST",
        body,
      });
      updateMessage(assistantId, response.data.reply || "");
      applyChatResult(response.data);
    }
  } catch (error) {
    updateMessage(assistantId, `请求失败：${error.message}`);
    toast(error.message);
  } finally {
    state.busy = false;
    els.sendButton.disabled = false;
  }
}

function chatBody(message) {
  return {
    app_id: els.appIdInput.value.trim() || "web-demo",
    user_id: els.userIdInput.value.trim() || "demo-user",
    session_id: state.sessionId || undefined,
    character_id: state.selectedCharacterId,
    persona_mode: state.selectedMode,
    message,
    language: "zh-CN",
    capabilities: {
      rag: els.ragToggle.checked,
      memory: els.memoryToggle.checked,
      continuous_session: els.sessionToggle.checked,
      safety_filter: true,
      debug_trace: els.debugToggle.checked,
      stream: els.streamToggle.checked,
    },
    generation: {
      model: els.modelInput.value.trim() || "fake-roleplay-model",
    },
  };
}

async function streamChat(body, assistantId) {
  const response = await rawApi("/v1/chat/stream", {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw apiError(payload, response.status);
  }
  let accumulated = "";
  await readSse(response, (event) => {
    const data = event.data || {};
    if (event.event === "delta") {
      accumulated += data.text || "";
      updateMessage(assistantId, accumulated);
    }
    if (event.event === "source") {
      state.sources = [...state.sources, data.source].filter(Boolean);
      renderSources();
    }
    if (event.event === "usage") {
      updateMessage(assistantId, accumulated, `${data.provider || ""} ${data.model || ""}`.trim());
    }
    if (event.event === "done") {
      updateMessage(assistantId, data.reply || accumulated);
      applyChatResult(data);
    }
    if (event.event === "error") {
      throw apiError({ ok: false, error: data.error }, response.status);
    }
  });
}

async function readSse(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const event = parseSse(part);
      if (event) {
        onEvent(event);
      }
    }
  }
  if (buffer.trim()) {
    const event = parseSse(buffer);
    if (event) {
      onEvent(event);
    }
  }
}

function parseSse(block) {
  let event = "message";
  const dataLines = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  if (dataLines.length === 0) {
    return null;
  }
  return {
    event,
    data: JSON.parse(dataLines.join("\n")),
  };
}

function applyChatResult(data) {
  state.sessionId = data.session_id || state.sessionId;
  state.sources = data.rag?.sources || state.sources;
  renderSources();
  renderSession();
  renderDebug(data.debug);
}

async function createSession({ force }) {
  if (!force && state.sessionId) {
    return state.sessionId;
  }
  syncConnectionFields();
  const response = await api("/v1/sessions", {
    method: "POST",
    body: {
      app_id: els.appIdInput.value.trim() || "web-demo",
      user_id: els.userIdInput.value.trim() || "demo-user",
      character_id: state.selectedCharacterId,
      persona_mode: state.selectedMode,
      metadata: { source: "frontend-demo" },
    },
  });
  state.sessionId = response.data.session_id;
  els.sessionToggle.checked = true;
  renderSession();
  toast("Session created.");
  return state.sessionId;
}

async function importRagDocument() {
  syncConnectionFields();
  const title = els.ragTitleInput.value.trim() || "Demo Note";
  const content = els.ragContentInput.value.trim();
  if (!content) {
    toast("RAG content is empty.");
    return;
  }
  els.ragStatus.textContent = "saving";
  try {
    const selected = selectedMode();
    const response = await api("/v1/rag/documents", {
      method: "POST",
      body: {
        app_id: els.appIdInput.value.trim() || "web-demo",
        document_id: `demo-${Date.now()}`,
        title,
        source_type: "timeline",
        character_id: state.selectedCharacterId,
        persona_mode: state.selectedMode,
        timeline: selected?.timeline || "mid_late",
        spoiler_level: 2,
        language: "zh-CN",
        content,
        metadata: { source: "frontend-demo" },
      },
    });
    els.ragStatus.textContent = response.data.status || "ready";
    els.ragToggle.checked = true;
    toast("RAG imported.");
  } catch (error) {
    els.ragStatus.textContent = "error";
    toast(error.message);
  }
}

async function api(path, options = {}) {
  const response = await rawApi(path, {
    ...options,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok || !payload?.ok) {
    throw apiError(payload, response.status);
  }
  return payload;
}

function rawApi(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    "X-Request-Id": `demo-${Date.now()}`,
    ...(options.headers || {}),
  };
  if (state.apiKey) {
    headers.Authorization = `Bearer ${state.apiKey}`;
  }
  return fetch(`${state.baseUrl}${path}`, {
    ...options,
    headers,
  });
}

function apiError(payload, status) {
  const error = payload?.error || {};
  return new Error(error.message || `HTTP ${status}`);
}

function pushMessage(role, content, meta = "") {
  const id = `${role}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  state.messages.push({ id, role, content, meta });
  renderMessages();
  return id;
}

function updateMessage(id, content, meta) {
  const message = state.messages.find((item) => item.id === id);
  if (!message) {
    return;
  }
  message.content = content;
  if (meta !== undefined) {
    message.meta = meta;
  }
  renderMessages();
}

function selectedCharacter() {
  return state.characters.find((item) => item.character_id === state.selectedCharacterId);
}

function selectedMode() {
  return selectedCharacter()?.modes?.find((item) => item.persona_mode === state.selectedMode);
}

function setStatus(value) {
  els.connectionStatus.textContent = value;
}

function autoSizeComposer() {
  els.messageInput.style.height = "auto";
  els.messageInput.style.height = `${Math.min(160, els.messageInput.scrollHeight)}px`;
}

function toast(message) {
  const node = document.createElement("div");
  node.className = "toast";
  node.textContent = message;
  document.body.append(node);
  window.setTimeout(() => node.remove(), 3200);
}

function initial(value) {
  return String(value || "?").trim().slice(0, 1).toUpperCase();
}

function formatScore(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(2) : "-";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

init();
