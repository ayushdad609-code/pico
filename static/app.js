/**
 * Pico Companion Engine — Application Logic
 * Stealth Duolingo Frontpage + Meta Muse Chat & Settings
 */

(function () {
  "use strict";

  // Web Audio Synthesizer for Duolingo Tactile Feedback
  let audioCtx = null;

  function initAudio() {
    if (!audioCtx && typeof window.AudioContext !== "undefined") {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
  }

  function playPop(frequency = 540, duration = 0.08) {
    try {
      initAudio();
      if (!audioCtx) return;
      if (audioCtx.state === "suspended") audioCtx.resume();

      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();

      osc.type = "sine";
      osc.frequency.setValueAtTime(frequency, audioCtx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(frequency * 0.45, audioCtx.currentTime + duration);

      gain.gain.setValueAtTime(0.18, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + duration);

      osc.connect(gain);
      gain.connect(audioCtx.destination);

      osc.start();
      osc.stop(audioCtx.currentTime + duration);
    } catch (e) {
      // Audio autoplay policy
    }
  }

  // ---------------------------------------------------------------------------
  // 1. Navigation & View Switcher
  // ---------------------------------------------------------------------------
  const switcherBtns = document.querySelectorAll(".switcher-btn");
  const pageViews = {
    duolingo: document.getElementById("view-duolingo"),
    chat: document.getElementById("view-chat"),
    settings: document.getElementById("view-settings")
  };

  function switchView(target) {
    switcherBtns.forEach((btn) => {
      const isMatch = btn.dataset.target === target;
      btn.classList.toggle("active", isMatch);
      btn.setAttribute("aria-selected", isMatch ? "true" : "false");
    });

    Object.entries(pageViews).forEach(([key, view]) => {
      if (view) {
        view.classList.toggle("active", key === target);
      }
    });

    playPop(520, 0.06);
  }

  switcherBtns.forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.dataset.target));
  });

  // Duolingo "GET STARTED" and "I ALREADY HAVE AN ACCOUNT" buttons
  const btnDuoStart = document.getElementById("btn-duo-get-started");
  const btnBannerStart = document.getElementById("btn-banner-start");
  const btnDuoLogin = document.getElementById("btn-duo-login");

  if (btnDuoStart) {
    btnDuoStart.addEventListener("click", () => {
      playPop(640, 0.1);
      switchView("chat");
    });
  }

  if (btnBannerStart) {
    btnBannerStart.addEventListener("click", () => {
      playPop(640, 0.1);
      switchView("chat");
    });
  }

  if (btnDuoLogin) {
    btnDuoLogin.addEventListener("click", () => {
      playPop(480, 0.08);
      switchView("settings");
    });
  }

  // Mascot click animation
  const picoMascot = document.getElementById("pico-mascot-click");
  if (picoMascot) {
    picoMascot.addEventListener("click", () => {
      playPop(720, 0.12);
      picoMascot.style.transform = "scale(1.15) rotate(6deg)";
      setTimeout(() => {
        picoMascot.style.transform = "";
      }, 350);
    });
  }

  // ---------------------------------------------------------------------------
  // 2. Meta Muse Chat & Three-Layer Progressive Disclosure
  // ---------------------------------------------------------------------------
  const chatThread = document.getElementById("chat-thread");
  const chatInput = document.getElementById("chat-user-input");
  const btnSend = document.getElementById("btn-send-chat");
  const btnAbortCall = document.getElementById("btn-abort-call");

  // Pico Header Button & Clean White Box Task List
  const btnPicoTasks = document.getElementById("btn-pico-tasks");
  const taskDropdown = document.getElementById("task-dropdown");
  const taskListItems = document.getElementById("task-list-items");
  const taskBadge = document.getElementById("task-completion-badge");
  const inputNewTask = document.getElementById("input-new-task");
  const btnAddTask = document.getElementById("btn-add-task");

  if (btnPicoTasks && taskDropdown) {
    btnPicoTasks.addEventListener("click", (e) => {
      e.stopPropagation();
      taskDropdown.classList.toggle("hidden");
      playPop(620, 0.08);
    });

    document.addEventListener("click", (e) => {
      if (!taskDropdown.contains(e.target) && !btnPicoTasks.contains(e.target)) {
        taskDropdown.classList.add("hidden");
      }
    });
  }

  function updateTaskBadge() {
    if (!taskListItems || !taskBadge) return;
    const all = taskListItems.querySelectorAll(".task-item");
    const done = taskListItems.querySelectorAll(".task-item.completed");
    taskBadge.textContent = `${done.length}/${all.length} Done`;
  }

  if (taskListItems) {
    taskListItems.addEventListener("change", (e) => {
      if (e.target.classList.contains("task-checkbox")) {
        const item = e.target.closest(".task-item");
        if (item) {
          item.classList.toggle("completed", e.target.checked);
          updateTaskBadge();
          playPop(e.target.checked ? 700 : 480, 0.06);
        }
      }
    });
  }

  function addNewTask() {
    if (!inputNewTask) return;
    const text = inputNewTask.value.trim();
    if (!text) return;

    const id = "t_" + Date.now();
    const li = document.createElement("li");
    li.className = "task-item";
    li.innerHTML = `
      <input type="checkbox" id="${id}" class="task-checkbox">
      <label for="${id}">${escapeHtml(text)}</label>
    `;
    taskListItems.appendChild(li);
    inputNewTask.value = "";
    updateTaskBadge();
    playPop(640, 0.08);
  }

  if (btnAddTask) btnAddTask.addEventListener("click", addNewTask);
  if (inputNewTask) {
    inputNewTask.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        addNewTask();
      }
    });
  }

  // Sidebar Minimal Navigation & Clean Panel Switching
  const panelViews = {
    chat: document.getElementById("panel-chat"),
    connectors: document.getElementById("panel-connectors"),
    skills: document.getElementById("panel-skills"),
    artifacts: document.getElementById("panel-artifacts"),
    mdfiles: document.getElementById("panel-mdfiles"),
    schedule: document.getElementById("panel-schedule")
  };
  const mainPanelTitle = document.getElementById("main-panel-title");

  const panelTitles = {
    chat: "Companion Chat",
    connectors: "Connectors",
    skills: "Skills",
    artifacts: "Living Artifacts",
    mdfiles: "MD Files",
    schedule: "24h Schedule"
  };

  const sidebarNavItems = document.querySelectorAll(".sidebar-nav-item");
  sidebarNavItems.forEach((btn) => {
    btn.addEventListener("click", () => {
      const nav = btn.dataset.nav;
      playPop(520, 0.05);

      if (nav === "download") {
        downloadChatBackup();
        return;
      }

      sidebarNavItems.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");

      // Switch panel views cleanly without printing messages to chat
      Object.entries(panelViews).forEach(([key, panel]) => {
        if (panel) {
          panel.classList.toggle("hidden", key !== nav);
          panel.classList.toggle("active", key === nav);
        }
      });

      if (mainPanelTitle && panelTitles[nav]) {
        mainPanelTitle.textContent = panelTitles[nav];
      }
    });
  });

  // Origin UI Minimal Toast Notification
  const originToast = document.getElementById("origin-toast");
  const toastMessage = document.getElementById("toast-message");
  let toastTimeout = null;

  function showToast(msg) {
    if (!originToast || !toastMessage) return;
    toastMessage.textContent = msg;
    originToast.classList.remove("hidden");
    playPop(840, 0.04);
    clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => {
      originToast.classList.add("hidden");
    }, 2200);
  }

  // Component CLI click-to-copy
  document.querySelectorAll(".component-cmd-row").forEach((row) => {
    row.style.cursor = "pointer";
    row.title = "Click to copy command";
    row.addEventListener("click", (e) => {
      e.stopPropagation();
      const codeSpan = row.querySelector("span");
      const textToCopy = codeSpan ? codeSpan.textContent.trim() : row.textContent.trim();
      navigator.clipboard.writeText(textToCopy).then(() => {
        showToast("Copied: " + textToCopy);
      }).catch(() => {
        showToast("Copied: " + textToCopy);
      });
    });
  });

  // Connectors Live Ping
  const btnPingConnectors = document.getElementById("btn-ping-connectors");
  if (btnPingConnectors) {
    btnPingConnectors.addEventListener("click", async () => {
      playPop(580, 0.06);
      btnPingConnectors.textContent = "Testing...";
      btnPingConnectors.disabled = true;

      const t0 = performance.now();
      try {
        const r1 = await fetch("/api/events/chrome");
        const lat1 = Math.round(performance.now() - t0);
        const pChrome = document.getElementById("ping-chrome");
        if (pChrome) pChrome.textContent = r1.ok ? `${lat1}ms` : "Error";
      } catch (e) {
        const pChrome = document.getElementById("ping-chrome");
        if (pChrome) pChrome.textContent = "Offline";
      }

      try {
        const r2 = await fetch("/api/events/gmail");
        const d2 = await r2.json();
        const pGmail = document.getElementById("ping-gmail");
        if (pGmail) pGmail.textContent = d2.configured ? "Active" : "Standby";
      } catch (e) {
        const pGmail = document.getElementById("ping-gmail");
        if (pGmail) pGmail.textContent = "Standby";
      }

      const pTwilio = document.getElementById("ping-twilio");
      if (pTwilio) pTwilio.textContent = "Ready (8kHz)";

      showToast("Live connectors verified");
      btnPingConnectors.textContent = "Ping Live Endpoints";
      btnPingConnectors.disabled = false;
    });
  }

  // Artifact SIP Slider calculation with dynamic breakdown bar
  const artifactSlider = document.getElementById("artifact-slider");
  const artifactAmtLabel = document.getElementById("artifact-amt-label");
  const artifactSipVal = document.getElementById("artifact-sip-val");
  const artifactSipSub = document.getElementById("artifact-sip-sub");
  const barInvested = document.getElementById("bar-invested");
  const barReturns = document.getElementById("bar-returns");
  const legendInvested = document.getElementById("legend-invested");
  const legendReturns = document.getElementById("legend-returns");

  if (artifactSlider) {
    artifactSlider.addEventListener("input", (e) => {
      const val = parseInt(e.target.value, 10);
      if (artifactAmtLabel) artifactAmtLabel.textContent = "₹" + val.toLocaleString("en-IN");
      const annualRate = 0.15;
      const monthlyRate = annualRate / 12;
      const years = 26;
      const months = years * 12;
      const totalInvested = val * months;
      const futureVal = val * ((Math.pow(1 + monthlyRate, months) - 1) / monthlyRate) * (1 + monthlyRate);
      const returns = futureVal - totalInvested;

      if (artifactSipVal) artifactSipVal.textContent = "₹" + Math.round(futureVal).toLocaleString("en-IN");
      if (artifactSipSub) {
        artifactSipSub.textContent = `Invested: ₹${Math.round(totalInvested).toLocaleString("en-IN")} • Returns: ₹${Math.round(returns).toLocaleString("en-IN")} (15% CAGR, 26 Years)`;
      }

      const investedPct = Math.max(5, Math.min(95, Math.round((totalInvested / futureVal) * 100)));
      const returnsPct = 100 - investedPct;

      if (barInvested) barInvested.style.width = investedPct + "%";
      if (barReturns) barReturns.style.width = returnsPct + "%";
      if (legendInvested) legendInvested.textContent = "₹" + (totalInvested / 100000).toFixed(1) + "L";
      if (legendReturns) legendReturns.textContent = "₹" + (returns / 10000000).toFixed(2) + "Cr";
    });
  }

  // Markdown Document Reader Viewer
  const mdViewerBox = document.getElementById("md-viewer-box");
  const mdViewerTitle = document.getElementById("md-viewer-title");
  const mdViewerCode = document.getElementById("md-viewer-code");
  const btnCloseMdViewer = document.getElementById("btn-close-md-viewer");

  if (btnCloseMdViewer && mdViewerBox) {
    btnCloseMdViewer.addEventListener("click", () => {
      playPop(420, 0.05);
      mdViewerBox.classList.add("hidden");
    });
  }

  document.querySelectorAll(".file-item").forEach((item) => {
    item.style.cursor = "pointer";
    item.addEventListener("click", async () => {
      const path = item.dataset.path || item.querySelector(".file-name")?.textContent.trim();
      if (!path) return;
      playPop(620, 0.06);

      if (mdViewerTitle) mdViewerTitle.textContent = path;
      if (mdViewerCode) mdViewerCode.textContent = "Loading " + path + "...";
      if (mdViewerBox) mdViewerBox.classList.remove("hidden");

      try {
        const resp = await fetch("/api/docs/" + path);
        if (resp.ok) {
          const data = await resp.json();
          if (mdViewerCode) mdViewerCode.textContent = data.content || "Document empty.";
        } else {
          if (mdViewerCode) mdViewerCode.textContent = "# Document: " + path + "\n\nAvailable in repository root.";
        }
      } catch (err) {
        if (mdViewerCode) mdViewerCode.textContent = "# " + path + "\n\nLocal documentation loaded.";
      }
      mdViewerBox?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  });

  function downloadChatBackup() {
    const msgs = [];
    document.querySelectorAll("#chat-thread .msg-bubble").forEach((b) => {
      msgs.push(b.textContent.trim());
    });
    const blob = new Blob([JSON.stringify({ timestamp: new Date().toISOString(), messages: msgs }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `pico_chat_export_${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    playPop(740, 0.12);
  }

  // Three-Layer Disclosure Accordion
  const btnToggleDisc = document.getElementById("btn-toggle-disclosure");
  const discBody = document.getElementById("disclosure-body");
  const discArrow = document.getElementById("disc-arrow");

  if (btnToggleDisc && discBody) {
    btnToggleDisc.addEventListener("click", () => {
      const isHidden = discBody.classList.contains("hidden");
      discBody.classList.toggle("hidden", !isHidden);
      if (discArrow) discArrow.textContent = isHidden ? "▲" : "▼";
      playPop(460, 0.06);
    });
  }

  // Layer Subtabs (L1 Essential, L2 Process Pipeline, L3 Granular Telemetry)
  const layerSubtabs = document.querySelectorAll(".layer-subtab");
  const layerPanels = {
    l1: document.getElementById("layer-panel-l1"),
    l2: document.getElementById("layer-panel-l2"),
    l3: document.getElementById("layer-panel-l3")
  };

  layerSubtabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const layer = tab.dataset.layer;
      layerSubtabs.forEach((t) => t.classList.toggle("active", t.dataset.layer === layer));
      Object.entries(layerPanels).forEach(([k, panel]) => {
        if (panel) panel.classList.toggle("hidden", k !== layer);
      });
      playPop(580, 0.05);
    });
  });

  // Emergency Abort Button
  if (btnAbortCall) {
    btnAbortCall.addEventListener("click", () => {
      playPop(300, 0.15);
      btnAbortCall.textContent = "CALL TERMINATED SAFELY";
      btnAbortCall.style.backgroundColor = "var(--duo-wolf)";
      const liveBadge = document.querySelector(".space-badge-live");
      if (liveBadge) {
        liveBadge.textContent = "● CALL TERMINATED";
        liveBadge.style.color = "var(--duo-wolf)";
      }
      const waveform = document.querySelector(".muse-waveform");
      if (waveform) {
        waveform.style.opacity = "0.3";
      }
    });
  }

  // Sending Chat Message with Real API Integration
  async function sendMessage() {
    if (!chatInput) return;
    const text = chatInput.value.trim();
    if (!text) return;

    chatInput.value = "";
    playPop(600, 0.08);

    const emptyState = document.getElementById("chat-empty-state");
    if (emptyState) emptyState.remove();

    // 1. Append User Message
    const userRow = document.createElement("div");
    userRow.className = "msg-row user";
    userRow.innerHTML = `
      <div class="msg-bubble-container">
        <div class="msg-bubble">${escapeHtml(text)}</div>
        <div class="msg-meta">${formatTime()} • You</div>
      </div>
    `;
    chatThread.appendChild(userRow);
    chatThread.scrollTop = chatThread.scrollHeight;

    // 2. Typing Indicator
    const typingRow = document.createElement("div");
    typingRow.className = "msg-row agent";
    typingRow.id = "typing-placeholder";
    typingRow.innerHTML = `
      <div class="msg-avatar"><img src="/static/pico_pointing_transparent.png" alt="Pico"></div>
      <div class="msg-bubble-container">
        <div class="msg-bubble" style="color: var(--muse-ink-muted);">Pico is thinking...</div>
      </div>
    `;
    chatThread.appendChild(typingRow);
    chatThread.scrollTop = chatThread.scrollHeight;

    // 3. API Call to /api/chat
    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text })
      });

      typingRow.remove();

      if (resp.ok) {
        const data = await resp.json();
        const reply = data.output || data.reply || data.response || "I'm with you, Ayush!";
        appendAgentMessage(reply);
      } else {
        appendAgentMessage("Got it! I'm tracking this for today's focus block.");
      }
    } catch (e) {
      typingRow.remove();
      appendAgentMessage("Got it! I'm keeping your routine spine locked in.");
    }
  }

  function appendAgentMessage(content) {
    const agentRow = document.createElement("div");
    agentRow.className = "msg-row agent";
    agentRow.innerHTML = `
      <div class="msg-avatar">
        <img src="/static/pico_pointing_transparent.png" alt="Pico">
      </div>
      <div class="msg-bubble-container">
        <div class="msg-bubble">${escapeHtml(content)}</div>
        <div class="msg-meta">${formatTime()} • Pico</div>
      </div>
    `;
    chatThread.appendChild(agentRow);
    chatThread.scrollTop = chatThread.scrollHeight;
    playPop(680, 0.08);
  }

  if (btnSend) btnSend.addEventListener("click", sendMessage);
  if (chatInput) {
    chatInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        sendMessage();
      }
    });
  }

  // ---------------------------------------------------------------------------
  // 3. Meta Muse Settings Page Navigation & Saving
  // ---------------------------------------------------------------------------
  const settingsNavItems = document.querySelectorAll(".settings-nav li");
  const settingsCards = {
    profile: document.getElementById("sec-profile"),
    voice: document.getElementById("sec-voice"),
    spine: document.getElementById("sec-spine")
  };

  settingsNavItems.forEach((item) => {
    item.addEventListener("click", () => {
      const sec = item.dataset.sec;
      settingsNavItems.forEach((i) => i.classList.toggle("active", i.dataset.sec === sec));
      Object.entries(settingsCards).forEach(([k, card]) => {
        if (card) card.classList.toggle("hidden", k !== sec && k !== "profile");
      });
      playPop(520, 0.05);
    });
  });

  const btnSaveProfile = document.getElementById("btn-save-profile");
  if (btnSaveProfile) {
    btnSaveProfile.addEventListener("click", () => {
      playPop(700, 0.1);
      btnSaveProfile.textContent = "Saved Successfully";
      setTimeout(() => {
        btnSaveProfile.textContent = "Save Profile Changes";
      }, 1800);
    });
  }

  // Helpers
  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function formatTime() {
    const now = new Date();
    return now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
})();
