const API_ROOT = "/v1/demo";
const APP_ID = "roleplay-prod";
const USER_STORAGE_KEY = "haruhi-roleplay-demo-user-v1";
const STREAM_RENDER_INTERVAL_MS = 50;

const STARTERS = {
  haruhi: [
    "春日，今天你打算给 SOS 团安排什么离谱活动？",
    "如果现在发现了一个疑似超自然事件，你会怎么调查？",
    "我们意见不一致时，你通常会怎么说服我？",
    "结合你经历过的事，讲一个适合此刻的桥段。",
  ],
  kyon: [
    "阿虚，你怎么看春日今天的新计划？",
    "用你的视角说说 SOS 团最近的一次麻烦。",
    "如果我被春日抓去当苦力，你有什么忠告？",
    "结合你经历过的事，吐槽一个相似的桥段。",
  ],
  mikuru: [
    "实玖瑠学姐，今天社团活动室里发生了什么？",
    "如果春日又提出奇怪要求，你会怎么办？",
    "能和我聊聊你最安心的一次社团活动吗？",
    "结合过去的经历，找一个和现在相似的桥段。",
  ],
  yuki: [
    "长门，你会怎样判断一件事是否异常？",
    "推荐一本适合今天读的书，并告诉我原因。",
    "如果 SOS 团遇到无法解释的现象，你会做什么？",
    "从已有经历里找一个与此刻最接近的桥段。",
  ],
  itsuki: [
    "古泉，你如何解释春日今天的情绪？",
    "如果闭锁空间再次出现，我们应该先做什么？",
    "以你的立场分析一下 SOS 团现在的气氛。",
    "引用一段相似经历，帮我判断接下来会发生什么。",
  ],
};

const DEFAULT_STARTERS = [
  "今天的社团活动有什么安排？",
  "结合你经历过的事，讲一个和现在相似的桥段。",
  "如果我们突然遇到超自然事件，你会怎么应对？",
  "先用你自己的方式向我介绍一下你吧。",
];

const state = {
  userId: loadOrCreateUserId(),
  characters: [],
  characterId: "",
  personaMode: "",
  sessionId: "",
  messages: [],
  sources: [],
  memories: [],
  usage: null,
  requestId: "",
  busy: false,
  controller: null,
  toastTimer: null,
  scrollFrame: null,
};

const els = {
  connectionLight: document.querySelector("#connectionLight"),
  connectionText: document.querySelector("#connectionText"),
  latencyBadge: document.querySelector("#latencyBadge"),
  characterCount: document.querySelector("#characterCount"),
  characterList: document.querySelector("#characterList"),
  userIdValue: document.querySelector("#userIdValue"),
  resetIdentityButton: document.querySelector("#resetIdentityButton"),
  personaAvatar: document.querySelector("#personaAvatar"),
  activeCharacterName: document.querySelector("#activeCharacterName"),
  activeCharacterDescription: document.querySelector("#activeCharacterDescription"),
  modeSelect: document.querySelector("#modeSelect"),
  newSessionButton: document.querySelector("#newSessionButton"),
  streamToggle: document.querySelector("#streamToggle"),
  sessionToggle: document.querySelector("#sessionToggle"),
  ragToggle: document.querySelector("#ragToggle"),
  memoryToggle: document.querySelector("#memoryToggle"),
  safetyToggle: document.querySelector("#safetyToggle"),
  messageList: document.querySelector("#messageList"),
  welcomeCard: document.querySelector(".welcome-card"),
  starterPrompts: document.querySelector("#starterPrompts"),
  noticeBar: document.querySelector("#noticeBar"),
  composerForm: document.querySelector("#composerForm"),
  chatComposer: document.querySelector("#chatComposer"),
  composerCount: document.querySelector("#composerCount"),
  sendButton: document.querySelector("#sendButton"),
  stopButton: document.querySelector("#stopButton"),
  sessionStatus: document.querySelector("#sessionStatus"),
  rememberToggle: document.querySelector("#rememberToggle"),
  memoryTypeSelect: document.querySelector("#memoryTypeSelect"),
  contextReel: document.querySelector("#contextReel"),
  sourceCount: document.querySelector("#sourceCount"),
  sourceList: document.querySelector("#sourceList"),
  memoryCount: document.querySelector("#memoryCount"),
  memoryList: document.querySelector("#memoryList"),
  refreshMemoriesButton: document.querySelector("#refreshMemoriesButton"),
  ragSearchForm: document.querySelector("#ragSearchForm"),
  ragQueryInput: document.querySelector("#ragQueryInput"),
  topKInput: document.querySelector("#topKInput"),
  spoilerInput: document.querySelector("#spoilerInput"),
  sourceTypesInput: document.querySelector("#sourceTypesInput"),
  ragSearchButton: document.querySelector("#ragSearchButton"),
  ragSearchSummary: document.querySelector("#ragSearchSummary"),
  temperatureInput: document.querySelector("#temperatureInput"),
  temperatureValue: document.querySelector("#temperatureValue"),
  styleInput: document.querySelector("#styleInput"),
  styleValue: document.querySelector("#styleValue"),
  maxTokensInput: document.querySelector("#maxTokensInput"),
  modelInput: document.querySelector("#modelInput"),
  narrationToggle: document.querySelector("#narrationToggle"),
  providerValue: document.querySelector("#providerValue"),
  modelValue: document.querySelector("#modelValue"),
  promptTokensValue: document.querySelector("#promptTokensValue"),
  completionTokensValue: document.querySelector("#completionTokensValue"),
  requestIdValue: document.querySelector("#requestIdValue"),
  openCharactersButton: document.querySelector("#openCharactersButton"),
  openInspectorButton: document.querySelector("#openInspectorButton"),
  characterPanel: document.querySelector("#characterPanel"),
  inspectorPanel: document.querySelector("#inspectorPanel"),
  panelBackdrop: document.querySelector("#panelBackdrop"),
  toast: document.querySelector("#toast"),
};

init();

function init() {
  els.userIdValue.textContent = state.userId;
  bindEvents();
  renderMessages();
  renderSources();
  renderMemories();
  updateSessionStatus();
  loadService();
}

function bindEvents() {
  els.composerForm.addEventListener("submit", (event) => {
    event.preventDefault();
    sendMessage();
  });
  els.chatComposer.addEventListener("input", updateComposer);
  els.chatComposer.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      sendMessage();
    }
  });
  els.stopButton.addEventListener("click", stopCurrentRequest);
  els.newSessionButton.addEventListener("click", () => resetConversation(true));
  els.resetIdentityButton.addEventListener("click", resetIdentity);
  els.modeSelect.addEventListener("change", () => {
    state.personaMode = els.modeSelect.value;
    resetConversation(false);
    renderActivePersona();
    refreshMemories();
  });
  els.sessionToggle.addEventListener("change", () => {
    if (!els.sessionToggle.checked) {
      state.sessionId = "";
    }
    updateSessionStatus();
  });
  els.rememberToggle.addEventListener("change", () => {
    els.memoryTypeSelect.disabled = !els.rememberToggle.checked;
    if (els.rememberToggle.checked) {
      els.memoryToggle.checked = true;
    }
  });
  els.refreshMemoriesButton.addEventListener("click", refreshMemories);
  els.ragSearchForm.addEventListener("submit", searchRag);
  els.temperatureInput.addEventListener("input", () => {
    els.temperatureValue.textContent = Number(els.temperatureInput.value).toFixed(2);
  });
  els.styleInput.addEventListener("input", () => {
    els.styleValue.textContent = Number(els.styleInput.value).toFixed(2);
  });
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.addEventListener("click", () => activateTab(button.dataset.tab));
  });
  els.openCharactersButton.addEventListener("click", () => openPanel(els.characterPanel));
  els.openInspectorButton.addEventListener("click", () => openPanel(els.inspectorPanel));
  els.panelBackdrop.addEventListener("click", closePanels);
  document.querySelectorAll("[data-close-panel]").forEach((button) => {
    button.addEventListener("click", closePanels);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closePanels();
    }
  });
}

async function loadService() {
  setConnection("loading", "正在连接生产服务");
  const startedAt = performance.now();
  try {
    const [healthResponse, catalogResponse] = await Promise.all([
      api("/health"),
      api("/personas"),
    ]);
    const health = healthResponse.data || {};
    state.characters = catalogResponse.data?.characters || [];
    if (state.characters.length === 0) {
      throw new Error("服务没有返回公开角色。");
    }
    if (!state.characters.some((item) => item.character_id === state.characterId)) {
      const preferred = state.characters.find((item) => item.character_id === "haruhi");
      const first = preferred || state.characters[0];
      state.characterId = first.character_id;
      state.personaMode = first.default_persona_mode;
    }
    renderCharacters();
    renderActivePersona();
    setConnection("online", health.status === "ok" ? "生产服务在线" : "服务已连接");
    els.latencyBadge.textContent = `${Math.round(performance.now() - startedAt)} ms`;
    phaseComplete("credential");
    phaseComplete("persona");
    refreshMemories();
  } catch (error) {
    setConnection("error", "服务暂不可用");
    showNotice(publicError(error));
    toast(publicError(error));
  }
}

function renderCharacters() {
  els.characterCount.textContent = String(state.characters.length);
  els.characterList.replaceChildren();
  for (const character of state.characters) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "character-button";
    button.setAttribute("aria-pressed", String(character.character_id === state.characterId));
    if (character.character_id === state.characterId) {
      button.classList.add("active");
    }

    const avatar = document.createElement("span");
    avatar.className = "character-initial";
    avatar.textContent = initial(character.display_name);
    const copy = document.createElement("span");
    const name = document.createElement("span");
    name.className = "character-name";
    name.textContent = character.display_name;
    const meta = document.createElement("span");
    meta.className = "character-meta";
    meta.textContent = character.description || `${character.modes?.length || 0} 个篇章设定`;
    copy.append(name, meta);
    button.append(avatar, copy);
    button.addEventListener("click", () => selectCharacter(character.character_id));
    els.characterList.append(button);
  }
}

function selectCharacter(characterId) {
  if (state.busy) {
    toast("请先停止当前回复，再切换角色。");
    return;
  }
  const character = state.characters.find((item) => item.character_id === characterId);
  if (!character) {
    return;
  }
  state.characterId = character.character_id;
  state.personaMode = character.default_persona_mode;
  resetConversation(false);
  renderCharacters();
  renderActivePersona();
  refreshMemories();
  closePanels();
}

function renderActivePersona() {
  const character = selectedCharacter();
  if (!character) {
    return;
  }
  const modes = character.modes || [];
  let mode = modes.find((item) => item.persona_mode === state.personaMode);
  if (!mode) {
    mode = modes.find((item) => item.persona_mode === character.default_persona_mode) || modes[0];
    state.personaMode = mode?.persona_mode || character.default_persona_mode;
  }

  els.personaAvatar.textContent = initial(character.display_name);
  els.activeCharacterName.textContent = character.display_name;
  els.activeCharacterDescription.textContent = mode?.description || character.description || "公开角色设定";
  els.modeSelect.disabled = modes.length === 0;
  els.modeSelect.replaceChildren(
    ...modes.map((item) => {
      const option = document.createElement("option");
      option.value = item.persona_mode;
      option.textContent = item.display_name || item.persona_mode;
      option.selected = item.persona_mode === state.personaMode;
      return option;
    }),
  );
  renderStarterPrompts();
}

function renderStarterPrompts() {
  const prompts = STARTERS[state.characterId] || DEFAULT_STARTERS;
  els.starterPrompts.replaceChildren(
    ...prompts.map((text) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "starter-button";
      button.textContent = text;
      button.addEventListener("click", () => {
        els.chatComposer.value = text;
        updateComposer();
        els.chatComposer.focus();
      });
      return button;
    }),
  );
}

function renderMessages() {
  if (state.messages.length === 0) {
    if (els.welcomeCard) {
      els.messageList.replaceChildren(els.welcomeCard);
      renderStarterPrompts();
    }
    return;
  }

  els.messageList.replaceChildren(...state.messages.map(messageNode));
  scrollMessages();
}

function messageNode(message) {
  const article = document.createElement("article");
  article.className = `message ${message.role}${message.pending ? " pending" : ""}`;
  article.dataset.messageId = message.id;

  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.textContent = message.role === "user" ? "我" : initial(selectedCharacter()?.display_name || "角");

  const body = document.createElement("div");
  body.className = "message-body";
  const bubble = document.createElement("div");
  bubble.className = `message-bubble${message.error ? " message-error" : ""}`;
  bubble.textContent = message.content || (message.pending ? "正在组织语言…" : "");
  body.append(bubble);

  if (message.meta) {
    const meta = document.createElement("div");
    meta.className = "message-meta";
    meta.textContent = message.meta;
    body.append(meta);
  }
  article.append(avatar, body);
  return article;
}

function appendMessage(role, content, options = {}) {
  const message = {
    id: crypto.randomUUID(),
    role,
    content,
    pending: options.pending === true,
    error: options.error === true,
    meta: options.meta || "",
  };
  state.messages.push(message);
  renderMessages();
  return message;
}

function updateMessage(message, patch) {
  cancelScheduledMessageRender(message);
  const shouldFollow = isMessageListNearBottom();
  Object.assign(message, patch);
  const existing = els.messageList.querySelector(`[data-message-id="${message.id}"]`);
  if (existing) {
    existing.replaceWith(messageNode(message));
  } else {
    renderMessages();
  }
  if (shouldFollow) {
    scrollMessages();
  }
}

function scheduleStreamingMessage(message, content) {
  message.content = content;
  if (message.renderTimer != null) {
    return;
  }
  message.renderTimer = window.setTimeout(() => {
    message.renderTimer = null;
    renderStreamingMessage(message);
  }, STREAM_RENDER_INTERVAL_MS);
}

function renderStreamingMessage(message) {
  const existing = els.messageList.querySelector(`[data-message-id="${message.id}"]`);
  const bubble = existing?.querySelector(".message-bubble");
  if (!bubble) {
    renderMessages();
    return;
  }
  const shouldFollow = isMessageListNearBottom();
  bubble.textContent = message.content || "正在组织语言…";
  if (shouldFollow) {
    scrollMessages();
  }
}

function cancelScheduledMessageRender(message) {
  if (message.renderTimer == null) {
    return;
  }
  window.clearTimeout(message.renderTimer);
  message.renderTimer = null;
}

async function sendMessage() {
  if (state.busy) {
    return;
  }
  const content = els.chatComposer.value.trim();
  if (!content) {
    els.chatComposer.focus();
    return;
  }
  if (!selectedCharacter() || !state.personaMode) {
    toast("角色目录还没有准备好，请稍后再试。");
    return;
  }

  clearNotice();
  state.busy = true;
  setBusy(true);
  resetPhases();
  phaseComplete("credential");
  phaseComplete("persona");
  phaseActive(els.ragToggle.checked ? "rag" : els.memoryToggle.checked ? "memory" : "model");
  state.sources = [];
  renderSources();

  appendMessage("user", content);
  const assistant = appendMessage("assistant", "", { pending: true });
  els.chatComposer.value = "";
  updateComposer();

  try {
    state.controller = new AbortController();
    if (els.sessionToggle.checked && !state.sessionId) {
      await createSession();
    }
    const body = buildChatRequest(content);
    const startedAt = performance.now();

    if (els.streamToggle.checked) {
      await streamChat(body, assistant);
    } else {
      await completeChat(body, assistant);
    }

    els.latencyBadge.textContent = `${Math.round(performance.now() - startedAt)} ms`;
    setConnection("online", "生产服务在线");
    if (els.memoryToggle.checked) {
      await refreshMemories({ quiet: true });
    }
    els.rememberToggle.checked = false;
    els.memoryTypeSelect.disabled = true;
  } catch (error) {
    if (error.name === "AbortError") {
      updateMessage(assistant, {
        pending: false,
        content: assistant.content || "回复已由你停止。",
        meta: "已停止接收流式输出",
      });
    } else {
      const message = publicError(error);
      updateMessage(assistant, { pending: false, error: true, content: message });
      showNotice(message);
      toast(message);
    }
  } finally {
    state.controller = null;
    state.busy = false;
    setBusy(false);
  }
}

function buildChatRequest(message) {
  const request = {
    app_id: APP_ID,
    user_id: state.userId,
    session_id: els.sessionToggle.checked ? state.sessionId : null,
    character_id: state.characterId,
    persona_mode: state.personaMode,
    message,
    language: "zh-CN",
    capabilities: {
      rag: els.ragToggle.checked,
      memory: els.memoryToggle.checked,
      continuous_session: els.sessionToggle.checked,
      safety_filter: els.safetyToggle.checked,
      debug_trace: false,
      stream: els.streamToggle.checked,
    },
    generation: {
      temperature: Number(els.temperatureInput.value),
      max_tokens: clampNumber(els.maxTokensInput.value, 64, 8192, 900),
      top_p: 1,
      presence_penalty: 0,
      frequency_penalty: 0,
      style_intensity: Number(els.styleInput.value),
      allow_narration: els.narrationToggle.checked,
    },
    metadata: {
      client: "public-chat-demo",
    },
  };

  const model = els.modelInput.value.trim();
  if (model) {
    request.generation.model = model;
  }
  if (els.rememberToggle.checked) {
    request.capabilities.memory = true;
    request.metadata.memory_write = {
      type: els.memoryTypeSelect.value,
      content: message,
      reason: "用户在公开演示页中明确选择保存此信息",
      confidence: 0.92,
    };
  }
  return request;
}

async function createSession() {
  updateSessionStatus("正在创建连续会话…");
  const response = await api("/sessions", {
    method: "POST",
    body: {
      app_id: APP_ID,
      user_id: state.userId,
      character_id: state.characterId,
      persona_mode: state.personaMode,
    },
    signal: state.controller?.signal,
  });
  state.sessionId = response.data.session_id;
  updateSessionStatus();
}

async function completeChat(body, assistant) {
  phaseActive("model");
  const response = await api("/chat", {
    method: "POST",
    body,
    signal: state.controller.signal,
  });
  const data = response.data || {};
  state.requestId = response.request_id || data.request_id || "";
  state.sessionId = data.session_id || state.sessionId;
  state.sources = data.rag?.sources || [];
  state.usage = data.usage || null;
  renderSources();
  renderUsage();
  updateSessionStatus();
  completeRequestPhases(data);
  updateMessage(assistant, {
    pending: false,
    content: data.reply || "服务没有返回回复文本。",
    meta: responseMeta(data),
  });
}

async function streamChat(body, assistant) {
  const response = await fetch(`${API_ROOT}/chat/stream`, {
    method: "POST",
    headers: {
      Accept: "text/event-stream",
      "Content-Type": "application/json",
      "X-Request-Id": crypto.randomUUID(),
    },
    body: JSON.stringify(body),
    signal: state.controller.signal,
    credentials: "same-origin",
  });
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  if (!response.body) {
    throw new Error("浏览器无法读取流式响应。");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let reply = "";
  let doneData = null;

  while (true) {
    const result = await reader.read();
    buffer += decoder.decode(result.value || new Uint8Array(), { stream: !result.done });
    const parsed = parseSseBuffer(buffer, result.done);
    buffer = parsed.rest;
    for (const event of parsed.events) {
      const data = event.data;
      if (event.type === "start") {
        state.requestId = data.request_id || "";
        state.sessionId = data.session_id || state.sessionId;
        renderUsage();
        updateSessionStatus();
      } else if (event.type === "source") {
        phaseComplete("rag");
        phaseActive(els.memoryToggle.checked ? "memory" : "model");
        if (data.source) {
          state.sources.push(data.source);
          renderSources();
        }
      } else if (event.type === "delta") {
        phaseComplete("memory");
        phaseActive("model");
        reply += data.text || "";
        scheduleStreamingMessage(assistant, reply);
      } else if (event.type === "usage") {
        state.usage = data;
        renderUsage();
      } else if (event.type === "done") {
        doneData = data;
        reply = data.reply || reply;
      } else if (event.type === "error") {
        const streamError = new Error(data.error?.message || "模型流式生成失败。");
        streamError.code = data.error?.code;
        throw streamError;
      }
    }
    if (result.done) {
      break;
    }
  }

  if (!doneData) {
    throw new Error("流式响应意外结束，没有收到完成事件。");
  }
  state.requestId = doneData.request_id || state.requestId;
  state.sessionId = doneData.session_id || state.sessionId;
  if (state.sources.length === 0) {
    state.sources = doneData.rag?.sources || [];
    renderSources();
  }
  renderUsage();
  updateSessionStatus();
  completeRequestPhases(doneData);
  updateMessage(assistant, {
    pending: false,
    content: reply || "服务没有返回回复文本。",
    meta: responseMeta(doneData),
  });
}

function parseSseBuffer(buffer, flush = false) {
  const normalized = buffer.replaceAll("\r\n", "\n");
  const blocks = normalized.split("\n\n");
  const rest = flush ? "" : blocks.pop() || "";
  const events = [];

  for (const block of blocks) {
    let type = "message";
    const dataLines = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) {
        type = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trimStart());
      }
    }
    if (dataLines.length === 0) {
      continue;
    }
    try {
      events.push({ type, data: JSON.parse(dataLines.join("\n")) });
    } catch {
      throw new Error("服务返回了无法解析的流式事件。");
    }
  }
  return { events, rest };
}

function completeRequestPhases(data) {
  if (els.ragToggle.checked) {
    phaseComplete("rag");
  } else {
    phaseSkipped("rag");
  }
  if (els.memoryToggle.checked || els.sessionToggle.checked) {
    phaseComplete("memory");
  } else {
    phaseSkipped("memory");
  }
  phaseComplete("model");
  if (data.memory?.write_count > 0) {
    toast(`已写入 ${data.memory.write_count} 条长期记忆。`);
  } else if (els.rememberToggle.checked) {
    toast("记忆候选已提交，但策略没有接受它。稳定偏好、关系和约定更容易通过。");
  }
}

function responseMeta(data) {
  const parts = [];
  const sourceCount = data.rag?.hit_count ?? state.sources.length;
  if (data.rag?.enabled) {
    parts.push(`RAG ${sourceCount} 条`);
  }
  if (data.memory?.enabled) {
    parts.push(`读记忆 ${data.memory.read_count || 0}`);
    if (data.memory.write_count) {
      parts.push(`写记忆 ${data.memory.write_count}`);
    }
  }
  if (state.usage?.total_tokens != null) {
    parts.push(`${state.usage.total_tokens} tokens`);
  }
  if (state.requestId) {
    parts.push(`请求 ${shortId(state.requestId)}`);
  }
  return parts.join(" · ");
}

async function searchRag(event) {
  event.preventDefault();
  const query = els.ragQueryInput.value.trim();
  if (!query) {
    els.ragQueryInput.focus();
    return;
  }
  if (!state.characterId || !state.personaMode) {
    toast("角色目录还没有准备好。");
    return;
  }

  const sourceTypes = els.sourceTypesInput.value
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const filters = {
    spoiler_level_max: clampNumber(els.spoilerInput.value, 0, 5, 2),
    language: "zh-CN",
  };
  if (sourceTypes.length > 0) {
    filters.source_types = sourceTypes;
  }

  els.ragSearchButton.disabled = true;
  els.ragSearchSummary.textContent = "正在查询 Qdrant 生产语料…";
  phaseActive("rag");
  try {
    const response = await api("/rag/search", {
      method: "POST",
      body: {
        app_id: APP_ID,
        user_id: state.userId,
        character_id: state.characterId,
        persona_mode: state.personaMode,
        query,
        top_k: clampNumber(els.topKInput.value, 1, 20, 6),
        filters,
        debug: false,
      },
    });
    const data = response.data || {};
    state.sources = (data.chunks || []).map((chunk) => ({
      ...(chunk.source || chunk),
      content: chunk.content,
      score: chunk.score ?? chunk.source?.score,
    }));
    renderSources();
    phaseComplete("rag");
    els.ragSearchSummary.textContent = [
      `Provider: ${data.provider || "未知"}`,
      `返回 ${data.hit_count ?? state.sources.length} 条`,
      `原始 ${data.raw_hit_count ?? "—"} 条`,
      data.rerank_applied ? "已重排" : "未重排",
    ].join(" · ");
    activateTab("sources");
  } catch (error) {
    phaseSkipped("rag");
    els.ragSearchSummary.textContent = publicError(error);
    toast(publicError(error));
  } finally {
    els.ragSearchButton.disabled = false;
  }
}

function renderSources() {
  els.sourceCount.textContent = String(state.sources.length);
  if (state.sources.length === 0) {
    els.sourceList.className = "card-list empty-list";
    els.sourceList.textContent = "发送一条启用桥段检索的消息后，引用来源会出现在这里。";
    return;
  }
  els.sourceList.className = "card-list";
  els.sourceList.replaceChildren(...state.sources.map(sourceNode));
}

function sourceNode(source, index) {
  const card = document.createElement("article");
  card.className = "source-card";

  const contentText = source.content || source.text || source.preview;
  if (contentText) {
    const content = document.createElement("p");
    content.className = "source-content";
    content.textContent = contentText;
    card.append(content);
    if (contentText.length > 280) {
      content.classList.add("collapsed");
      const expandButton = document.createElement("button");
      expandButton.type = "button";
      expandButton.className = "source-expand-button";
      expandButton.textContent = "展开完整语料";
      expandButton.setAttribute("aria-expanded", "false");
      expandButton.addEventListener("click", () => {
        const expanded = content.classList.toggle("expanded");
        content.classList.toggle("collapsed", !expanded);
        expandButton.textContent = expanded ? "收起语料" : "展开完整语料";
        expandButton.setAttribute("aria-expanded", String(expanded));
      });
      card.append(expandButton);
    }
  }

  const header = document.createElement("header");
  const title = document.createElement("h3");
  title.textContent = source.title || source.document_title || source.document_id || `引用 ${index + 1}`;
  const score = document.createElement("span");
  score.className = "score-badge";
  score.textContent = Number.isFinite(Number(source.score)) ? Number(source.score).toFixed(3) : "source";
  header.append(title, score);
  card.append(header);
  const meta = document.createElement("div");
  meta.className = "source-meta";
  meta.textContent = [
    source.source_type,
    source.timeline,
    source.spoiler_level != null ? `剧透 ${source.spoiler_level}` : "",
    source.chunk_id,
  ].filter(Boolean).join(" · ");
  card.append(meta);
  return card;
}

async function refreshMemories(options = {}) {
  if (!state.characterId || !state.personaMode) {
    return;
  }
  els.refreshMemoriesButton.disabled = true;
  try {
    const query = new URLSearchParams({
      app_id: APP_ID,
      character_id: state.characterId,
      persona_mode: state.personaMode,
      limit: "30",
    });
    const response = await api(`/memory/${encodeURIComponent(state.userId)}?${query}`);
    state.memories = response.data?.items || [];
    renderMemories();
    if (els.memoryToggle.checked) {
      phaseComplete("memory");
    }
  } catch (error) {
    if (!options.quiet) {
      toast(publicError(error));
    }
  } finally {
    els.refreshMemoriesButton.disabled = false;
  }
}

function renderMemories() {
  els.memoryCount.textContent = String(state.memories.length);
  if (state.memories.length === 0) {
    els.memoryList.className = "card-list empty-list";
    els.memoryList.textContent = "暂时没有长期记忆。只有你明确勾选保存且通过策略的稳定信息才会出现在这里。";
    return;
  }
  els.memoryList.className = "card-list";
  els.memoryList.replaceChildren(...state.memories.map(memoryNode));
}

function memoryNode(memory) {
  const card = document.createElement("article");
  card.className = "memory-card";
  const header = document.createElement("header");
  const title = document.createElement("h3");
  title.textContent = memory.content;
  const type = document.createElement("span");
  type.className = "type-badge";
  type.textContent = memoryTypeName(memory.type);
  header.append(title, type);
  card.append(header);

  const reason = document.createElement("p");
  reason.textContent = memory.reason || "明确保存的长期记忆";
  card.append(reason);
  const meta = document.createElement("div");
  meta.className = "memory-meta";
  meta.textContent = `置信度 ${formatConfidence(memory.confidence)} · ${formatDate(memory.updated_at || memory.created_at)}`;
  card.append(meta);

  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "delete-memory-button";
  remove.textContent = "删除这条记忆";
  remove.addEventListener("click", () => deleteMemory(memory));
  card.append(remove);
  return card;
}

async function deleteMemory(memory) {
  if (!window.confirm(`确认删除这条记忆吗？\n\n${memory.content}`)) {
    return;
  }
  const query = new URLSearchParams({
    app_id: APP_ID,
    character_id: state.characterId,
    persona_mode: state.personaMode,
  });
  try {
    await api(
      `/memory/${encodeURIComponent(state.userId)}/${encodeURIComponent(memory.memory_id)}?${query}`,
      { method: "DELETE" },
    );
    state.memories = state.memories.filter((item) => item.memory_id !== memory.memory_id);
    renderMemories();
    toast("长期记忆已删除。");
  } catch (error) {
    toast(publicError(error));
  }
}

function renderUsage() {
  const usage = state.usage || {};
  els.providerValue.textContent = usage.provider || "—";
  els.modelValue.textContent = usage.model || "—";
  els.promptTokensValue.textContent = valueOrDash(usage.prompt_tokens);
  els.completionTokensValue.textContent = valueOrDash(usage.completion_tokens);
  els.requestIdValue.textContent = state.requestId || "—";
  els.requestIdValue.title = state.requestId || "";
}

function activateTab(name) {
  document.querySelectorAll(".tab-button").forEach((button) => {
    const active = button.dataset.tab === name;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    const active = panel.dataset.panel === name;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
}

function resetConversation(showToast) {
  stopCurrentRequest();
  state.sessionId = "";
  state.messages = [];
  state.sources = [];
  state.usage = null;
  state.requestId = "";
  renderMessages();
  renderSources();
  renderUsage();
  resetPhases();
  phaseComplete("credential");
  phaseComplete("persona");
  updateSessionStatus();
  clearNotice();
  if (showToast) {
    toast("已开始一段新的对话；长期记忆仍然保留。");
  }
}

function resetIdentity() {
  if (state.busy) {
    toast("请先停止当前回复，再更换演示身份。");
    return;
  }
  state.userId = createUserId();
  localStorage.setItem(USER_STORAGE_KEY, state.userId);
  state.memories = [];
  els.userIdValue.textContent = state.userId;
  resetConversation(false);
  renderMemories();
  toast("已生成新的匿名演示身份。");
}

function updateComposer() {
  els.chatComposer.style.height = "auto";
  els.chatComposer.style.height = `${Math.min(els.chatComposer.scrollHeight, 150)}px`;
  els.composerCount.textContent = `${els.chatComposer.value.length} / 16000`;
}

function updateSessionStatus(override) {
  if (override) {
    els.sessionStatus.textContent = override;
    return;
  }
  if (!els.sessionToggle.checked) {
    els.sessionStatus.textContent = "连续会话：已关闭";
  } else if (state.sessionId) {
    els.sessionStatus.textContent = `连续会话：${shortId(state.sessionId)}`;
    els.sessionStatus.title = state.sessionId;
  } else {
    els.sessionStatus.textContent = "连续会话：将在发送时创建";
    els.sessionStatus.title = "";
  }
}

function setBusy(busy) {
  els.sendButton.disabled = busy;
  els.stopButton.hidden = !busy;
  els.newSessionButton.disabled = busy;
  els.modeSelect.disabled = busy || !selectedCharacter();
}

function stopCurrentRequest() {
  if (state.controller) {
    state.controller.abort();
  }
}

function phaseActive(name) {
  phaseItem(name)?.classList.add("active");
}

function phaseComplete(name) {
  const item = phaseItem(name);
  item?.classList.remove("active", "skipped");
  item?.classList.add("complete");
}

function phaseSkipped(name) {
  const item = phaseItem(name);
  item?.classList.remove("active", "complete");
  item?.classList.add("skipped");
}

function resetPhases() {
  els.contextReel.querySelectorAll("li").forEach((item) => {
    item.classList.remove("active", "complete", "skipped");
  });
}

function phaseItem(name) {
  return els.contextReel.querySelector(`[data-phase="${name}"]`);
}

function openPanel(panel) {
  closePanels();
  panel.classList.add("open");
  els.panelBackdrop.hidden = false;
  els.panelBackdrop.classList.add("visible");
}

function closePanels() {
  els.characterPanel.classList.remove("open");
  els.inspectorPanel.classList.remove("open");
  els.panelBackdrop.classList.remove("visible");
  els.panelBackdrop.hidden = true;
}

function showNotice(message) {
  els.noticeBar.textContent = message;
  els.noticeBar.hidden = false;
}

function clearNotice() {
  els.noticeBar.hidden = true;
  els.noticeBar.textContent = "";
}

function toast(message) {
  window.clearTimeout(state.toastTimer);
  els.toast.textContent = message;
  els.toast.hidden = false;
  state.toastTimer = window.setTimeout(() => {
    els.toast.hidden = true;
  }, 4200);
}

function setConnection(status, text) {
  els.connectionLight.className = `status-light ${status}`;
  els.connectionText.textContent = text;
}

async function api(path, options = {}) {
  const response = await fetch(`${API_ROOT}${path}`, {
    method: options.method || "GET",
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      "X-Request-Id": crypto.randomUUID(),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
    credentials: "same-origin",
  });
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  const payload = await response.json();
  if (!payload.ok) {
    throw errorFromPayload(payload, response.status);
  }
  return payload;
}

async function errorFromResponse(response) {
  try {
    const payload = await response.json();
    return errorFromPayload(payload, response.status);
  } catch {
    const error = new Error(`服务请求失败（HTTP ${response.status}）。`);
    error.status = response.status;
    return error;
  }
}

function errorFromPayload(payload, status) {
  const error = new Error(payload.error?.message || `服务请求失败（HTTP ${status}）。`);
  error.code = payload.error?.code;
  error.status = status;
  error.requestId = payload.request_id;
  return error;
}

function publicError(error) {
  const prefix = error.code ? `${error.code}：` : "";
  if (error.status === 429) {
    return `${prefix}公开演示请求较多，请稍后再试。`;
  }
  if (error.status === 403) {
    return `${prefix}演示代理拒绝了这个请求。`;
  }
  return `${prefix}${error.message || "请求失败，请稍后重试。"}`;
}

function loadOrCreateUserId() {
  const stored = localStorage.getItem(USER_STORAGE_KEY);
  if (stored && /^demo-[a-zA-Z0-9_-]{8,90}$/.test(stored)) {
    return stored;
  }
  const userId = createUserId();
  localStorage.setItem(USER_STORAGE_KEY, userId);
  return userId;
}

function createUserId() {
  return `demo-${crypto.randomUUID()}`;
}

function selectedCharacter() {
  return state.characters.find((item) => item.character_id === state.characterId);
}

function initial(value) {
  const clean = String(value || "角").trim();
  return clean.slice(0, 1).toUpperCase();
}

function shortId(value) {
  const clean = String(value || "");
  return clean.length > 12 ? `${clean.slice(0, 8)}…` : clean;
}

function clampNumber(value, min, max, fallback) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, parsed));
}

function valueOrDash(value) {
  return value == null ? "—" : String(value);
}

function formatConfidence(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${Math.round(numeric * 100)}%` : "—";
}

function formatDate(value) {
  if (!value) {
    return "时间未知";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("zh-CN", { hour12: false });
}

function memoryTypeName(value) {
  return {
    user_preference: "用户偏好",
    relationship: "关系约定",
    roleplay_fact: "角色事实",
    safety_preference: "安全偏好",
    interaction_summary: "互动摘要",
  }[value] || value || "记忆";
}

function scrollMessages() {
  if (state.scrollFrame != null) {
    return;
  }
  state.scrollFrame = requestAnimationFrame(() => {
    state.scrollFrame = null;
    els.messageList.scrollTop = els.messageList.scrollHeight;
  });
}

function isMessageListNearBottom() {
  const remaining = els.messageList.scrollHeight
    - els.messageList.scrollTop
    - els.messageList.clientHeight;
  return remaining < 120;
}
