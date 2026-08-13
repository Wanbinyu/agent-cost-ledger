(() => {
  const $ = (id) => document.getElementById(id);

  const state = {
    sessionId: null,
    ready: false,
    busy: false,
    settings: null,
  };

  function fmtTokens(inT, outT) {
    return `${Number(inT || 0).toLocaleString()} in / ${Number(outT || 0).toLocaleString()} out`;
  }

  function fmtCost(usd, partial) {
    if (usd === null || usd === undefined) {
      return partial ? "未知（缺单价）" : "—";
    }
    const s = `$${Number(usd).toFixed(6)}`;
    return partial ? `${s}*` : s;
  }

  function setStatus(text, level) {
    $("u-status").textContent = text;
    const dot = $("u-dot");
    dot.className = "dot" + (level ? ` ${level}` : "");
  }

  function updateUsageBar(settings, sessionUsage, totalUsage) {
    if (settings) {
      $("u-model").textContent = settings.model || "—";
    }
    if (sessionUsage) {
      $("u-session").textContent = fmtTokens(
        sessionUsage.input_tokens,
        sessionUsage.output_tokens
      );
      $("u-session-cost").textContent = fmtCost(
        sessionUsage.cost_usd,
        sessionUsage.cost_is_partial
      );
    }
    if (totalUsage) {
      $("u-total").textContent = fmtTokens(
        totalUsage.input_tokens,
        totalUsage.output_tokens
      );
      $("u-total-cost").textContent = fmtCost(
        totalUsage.cost_usd,
        totalUsage.cost_is_partial
      );
    }
  }

  function showBanner(text, kind) {
    const el = $("banner");
    if (!text) {
      el.className = "banner hidden";
      el.textContent = "";
      return;
    }
    el.className = `banner ${kind || ""}`;
    el.textContent = text;
  }

  function renderMessages(messages) {
    const box = $("messages");
    box.innerHTML = "";
    if (!messages || !messages.length) {
      const empty = document.createElement("div");
      empty.className = "msg system-empty";
      empty.textContent =
        "直接输入即可对话。每条回复的 token / 费用会自动记入底栏，无需手动 add。";
      box.appendChild(empty);
      return;
    }
    for (const m of messages) {
      if (m.role !== "user" && m.role !== "assistant") continue;
      const el = document.createElement("div");
      el.className = `msg ${m.role}`;
      if (m.role === "assistant" && (m.input_tokens || m.output_tokens)) {
        const meta = document.createElement("div");
        meta.className = "meta";
        meta.textContent = `${m.model || ""} · ${fmtTokens(m.input_tokens, m.output_tokens)}`;
        el.appendChild(meta);
      }
      const body = document.createElement("div");
      body.textContent = m.content || "";
      el.appendChild(body);
      box.appendChild(el);
    }
    box.scrollTop = box.scrollHeight;
  }

  async function api(path, options = {}) {
    const resp = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    let data = null;
    const text = await resp.text();
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = { detail: text };
    }
    if (!resp.ok) {
      const detail = (data && data.detail) || resp.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return data;
  }

  async function refreshSettings() {
    const s = await api("/api/settings");
    state.settings = s;
    state.ready = !!s.ready;
    $("u-model").textContent = s.model || "—";
    if (s.ready) {
      setStatus("已连接", "ok");
      showBanner("", "");
    } else {
      setStatus("未配置 Key", "warn");
      showBanner(
        "尚未配置模型。点右上角「设置」，或设置环境变量 OPENAI_API_KEY 后重启。",
        ""
      );
    }
    return s;
  }

  async function refreshUsage() {
    const q = state.sessionId ? `?session_id=${encodeURIComponent(state.sessionId)}` : "";
    const sessionUsage = state.sessionId
      ? await api(`/api/usage${q}`)
      : { input_tokens: 0, output_tokens: 0, cost_usd: null, cost_is_partial: false };
    const totalUsage = await api("/api/usage");
    updateUsageBar(state.settings, sessionUsage, totalUsage);
  }

  async function refreshSessions() {
    const data = await api("/api/sessions");
    const ul = $("session-list");
    ul.innerHTML = "";
    for (const s of data.sessions || []) {
      const li = document.createElement("li");
      li.textContent = s.title || s.id;
      li.dataset.id = s.id;
      if (s.id === state.sessionId) li.classList.add("active");
      li.onclick = () => loadSession(s.id);
      ul.appendChild(li);
    }
  }

  async function loadSession(id) {
    const session = await api(`/api/sessions/${id}`);
    state.sessionId = session.id;
    renderMessages(session.messages || []);
    await refreshSessions();
    await refreshUsage();
  }

  async function newSession() {
    const session = await api("/api/sessions", { method: "POST", body: "{}" });
    state.sessionId = session.id;
    renderMessages([]);
    await refreshSessions();
    await refreshUsage();
    $("input").focus();
  }

  function openModal(force) {
    const s = state.settings || {};
    $("s-base").value = s.base_url || "https://api.openai.com/v1";
    $("s-model").value = s.model || "gpt-4o-mini";
    $("s-provider").value = s.provider || "openai";
    $("s-key").value = "";
    $("s-key").placeholder = s.has_api_key
      ? `已保存 ${s.api_key_masked}（留空则保留）`
      : "sk-… 或中转 Key";
    $("s-in-price").value =
      s.input_price_per_1m === null || s.input_price_per_1m === undefined
        ? ""
        : s.input_price_per_1m;
    $("s-out-price").value =
      s.output_price_per_1m === null || s.output_price_per_1m === undefined
        ? ""
        : s.output_price_per_1m;
    $("modal").classList.remove("hidden");
    if (force) $("s-key").focus();
  }

  function closeModal() {
    $("modal").classList.add("hidden");
  }

  async function saveSettings() {
    const body = {
      provider: $("s-provider").value.trim() || "openai",
      base_url: $("s-base").value.trim() || "https://api.openai.com/v1",
      api_key: $("s-key").value.trim(),
      model: $("s-model").value.trim() || "gpt-4o-mini",
      keep_existing_key: true,
    };
    const ip = $("s-in-price").value;
    const op = $("s-out-price").value;
    if (ip !== "") body.input_price_per_1m = Number(ip);
    if (op !== "") body.output_price_per_1m = Number(op);

    const s = await api("/api/settings", {
      method: "POST",
      body: JSON.stringify(body),
    });
    state.settings = s;
    state.ready = !!s.ready;
    closeModal();
    if (s.ready) {
      setStatus("已连接", "ok");
      showBanner("配置已保存，可以直接对话。", "ok");
      setTimeout(() => showBanner("", ""), 2500);
    } else {
      setStatus("未配置 Key", "warn");
      showBanner("仍缺少 API Key。", "err");
    }
  }

  async function sendMessage(text) {
    if (state.busy) return;
    if (!text.trim()) return;
    if (!state.ready) {
      openModal(true);
      return;
    }

    state.busy = true;
    $("btn-send").disabled = true;
    setStatus("生成中…", "warn");

    // optimistic user bubble
    const current = [];
    const nodes = $("messages").querySelectorAll(".msg.user, .msg.assistant");
    // rebuild from DOM is fragile; append temp
    const empty = $("messages").querySelector(".system-empty");
    if (empty) empty.remove();

    const userEl = document.createElement("div");
    userEl.className = "msg user";
    userEl.textContent = text;
    $("messages").appendChild(userEl);

    const waitEl = document.createElement("div");
    waitEl.className = "msg assistant";
    waitEl.textContent = "…";
    $("messages").appendChild(waitEl);
    $("messages").scrollTop = $("messages").scrollHeight;

    try {
      const data = await api("/api/chat", {
        method: "POST",
        body: JSON.stringify({
          session_id: state.sessionId,
          message: text,
        }),
      });
      state.sessionId = data.session_id;
      waitEl.remove();
      const a = data.message || {};
      const aEl = document.createElement("div");
      aEl.className = "msg assistant";
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = `${a.model || ""} · ${fmtTokens(a.input_tokens, a.output_tokens)}`;
      aEl.appendChild(meta);
      const body = document.createElement("div");
      body.textContent = a.content || "";
      aEl.appendChild(body);
      $("messages").appendChild(aEl);
      $("messages").scrollTop = $("messages").scrollHeight;

      updateUsageBar(data.settings, data.session_usage, data.total_usage);
      state.settings = data.settings || state.settings;
      await refreshSessions();
      setStatus("已连接", "ok");
      showBanner("", "");
    } catch (err) {
      waitEl.textContent = `错误：${err.message || err}`;
      waitEl.style.borderColor = "#6a2434";
      setStatus("出错", "err");
      showBanner(String(err.message || err), "err");
    } finally {
      state.busy = false;
      $("btn-send").disabled = false;
      $("input").focus();
    }
  }

  function autosize() {
    const el = $("input");
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }

  async function boot() {
    renderMessages([]);
    try {
      await refreshSettings();
      await refreshUsage();
      await refreshSessions();
      if (!state.sessionId) {
        // keep empty until first message creates session via chat API
      }
      if (!state.ready) {
        openModal(true);
      } else {
        setStatus("已连接", "ok");
      }
    } catch (err) {
      setStatus("启动失败", "err");
      showBanner(String(err.message || err), "err");
    }
  }

  $("composer").addEventListener("submit", (e) => {
    e.preventDefault();
    const text = $("input").value;
    $("input").value = "";
    autosize();
    sendMessage(text);
  });

  $("input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      $("composer").requestSubmit();
    }
  });
  $("input").addEventListener("input", autosize);

  $("btn-new").onclick = () => newSession();
  $("btn-setup").onclick = () => openModal(true);
  $("btn-cancel").onclick = () => {
    if (state.ready) closeModal();
  };
  $("btn-save").onclick = () => saveSettings().catch((err) => {
    showBanner(String(err.message || err), "err");
  });

  boot();
})();
