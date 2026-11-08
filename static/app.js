/**
 * Pico Companion — Modern Frontend Engine
 * Spec: Ui Design Brief12.md (Tactile Companion Minimalist)
 * Pure vanilla ES6, zero external CDN dependencies, zero emojis.
 */

(function () {
  'use strict';

  // Application State
  const state = {
    currentMode: 'today',      // 'today' | 'memory' | 'settings'
    previousMode: 'today',
    currentView: 'chat',       // 'chat' | 'panel' (for mobile toggling between chat and right canvas)
    activeRightTab: 'routine', // 'routine' | 'artifacts' | 'skills' | 'connectors' | 'mdfiles'
    soundEnabled: true,
    stealthMode: false,
    online: false,
    chatHistory: [],
    audioCtx: null,
    lastEscPress: 0,
    mascotClickCount: 0
  };

  // DOM Query Helpers
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  // Strip Unicode Emojis from any string
  function stripEmojis(str) {
    if (!str || typeof str !== 'string') return '';
    return str.replace(/[\U00010000-\U0010ffff]|[\u2600-\u27ff]/gu, '').trim();
  }

  // Generic API Helper
  async function api(path, options = {}) {
    try {
      const res = await fetch(path, options);
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      return await res.json();
    } catch (err) {
      console.warn(`[API] ${path} error:`, err.message);
      return null;
    }
  }

  // Web Audio Pop (Soft Marimba / Woodblock tap)
  function playPop() {
    if (!state.soundEnabled) return;
    try {
      if (!state.audioCtx) {
        state.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      }
      if (state.audioCtx.state === 'suspended') {
        state.audioCtx.resume();
      }
      const osc = state.audioCtx.createOscillator();
      const gain = state.audioCtx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(580, state.audioCtx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(840, state.audioCtx.currentTime + 0.05);
      gain.gain.setValueAtTime(0.12, state.audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, state.audioCtx.currentTime + 0.08);
      osc.connect(gain);
      gain.connect(state.audioCtx.destination);
      osc.start();
      osc.stop(state.audioCtx.currentTime + 0.09);
    } catch (e) {
      // AudioContext policy
    }
  }

  // Toast Notifications
  function showToast(message, duration = 2800) {
    const container = $('#toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = stripEmojis(message);
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(8px)';
      toast.style.transition = 'all 150ms ease';
      setTimeout(() => toast.remove(), 160);
    }, duration);
  }

  // ==========================================================================
  // NAVIGATION & VIEW SWITCHER
  // ==========================================================================

  function switchMode(mode, panel = null) {
    if (mode === 'settings') {
      state.previousMode = state.currentMode;
      const settingsModal = $('#mode-settings');
      if (settingsModal) settingsModal.classList.add('active');
      playPop();
      return;
    }

    state.currentMode = mode;
    $$('.mode-panel').forEach(p => p.classList.remove('active'));

    const targetPanel = $(`#mode-${mode}`);
    if (targetPanel) targetPanel.classList.add('active');

    // Update active nav rail items
    $$('.nav-item').forEach(item => {
      if (item.dataset.mode === mode && (!panel || item.dataset.panel === panel)) {
        item.classList.add('active');
      } else if (item.dataset.mode === mode && !panel && !item.dataset.panel) {
        item.classList.add('active');
      } else {
        item.classList.remove('active');
      }
    });

    // Update active mobile nav items
    $$('.mobile-nav-item').forEach(item => {
      if (item.dataset.mode === mode && (!panel || item.dataset.panel === panel)) {
        item.classList.add('active');
      } else {
        item.classList.remove('active');
      }
    });

    // Panel switching on Today view
    if (mode === 'today') {
      const centerCol = $('#panel-chat');
      const rightCanvas = $('#right-canvas');

      if (panel === 'chat' || !panel) {
        state.currentView = 'chat';
        if (centerCol) centerCol.classList.add('active-view');
        if (rightCanvas) rightCanvas.classList.remove('active-view');
      } else {
        // One of the workspace tabs (schedule, artifacts, skills, connectors, mdfiles)
        state.currentView = 'panel';
        if (centerCol) centerCol.classList.remove('active-view');
        if (rightCanvas) rightCanvas.classList.add('active-view');
        switchRightTab(panel);
      }
    }

    playPop();
  }

  function switchRightTab(tabKey) {
    const canonicalKey = (tabKey === 'schedule' || tabKey === 'routine') ? 'routine' : tabKey;
    state.activeRightTab = canonicalKey;

    // Update Tab Switcher Buttons
    $$('#right-canvas-tabs .tab-btn').forEach(btn => {
      if (btn.dataset.tab === canonicalKey || (canonicalKey === 'routine' && btn.dataset.tab === 'routine')) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    const panelMap = {
      routine: 'panel-schedule',
      schedule: 'panel-schedule',
      artifacts: 'panel-artifacts',
      skills: 'panel-skills',
      connectors: 'panel-connectors',
      mdfiles: 'panel-mdfiles'
    };

    const targetPanelId = panelMap[canonicalKey] || `panel-${canonicalKey}`;
    $$('.right-canvas .tab-panel').forEach(p => p.classList.remove('active'));
    const target = $(`#${targetPanelId}`);
    if (target) target.classList.add('active');

    // On mobile, ensure right-canvas is active-view when a tab is clicked
    const centerCol = $('#panel-chat');
    const rightCanvas = $('#right-canvas');
    if (window.innerWidth <= 768) {
      if (centerCol) centerCol.classList.remove('active-view');
      if (rightCanvas) rightCanvas.classList.add('active-view');
    }
  }

  // ==========================================================================
  // STATUS & HEALTH POLLING
  // ==========================================================================

  async function checkHealth() {
    const data = await api('/api/health');
    const dot = $('#status-dot');
    const rightDot = $('#pico-right-dot');
    const profileDot = $('#pico-profile-dot');
    const text = $('#status-text');

    if (data && data.status === 'healthy') {
      state.online = true;
      if (dot) dot.className = 'status-dot online';
      if (rightDot) rightDot.className = 'status-dot status-dot-sm online';
      if (profileDot) profileDot.className = 'status-dot status-dot-sm online';
      if (text) text.textContent = 'Pico is active & watching';
    } else {
      state.online = false;
      if (dot) dot.className = 'status-dot offline';
      if (rightDot) rightDot.className = 'status-dot status-dot-sm offline';
      if (profileDot) profileDot.className = 'status-dot status-dot-sm offline';
      if (text) text.textContent = 'Companion offline - retrying';
    }
  }

  async function pollHeartbeat() {
    const beat = await api('/api/heartbeat', { method: 'POST' });
    if (beat && state.online) {
      const text = $('#status-text');
      const rightSub = $('#pico-right-sub');
      if (text && beat.outcome) {
        text.textContent = `Pico beat #${beat.beat_number} (${beat.outcome})`;
      }
      if (rightSub && beat.outcome) {
        rightSub.textContent = `Heartbeat #${beat.beat_number} active`;
      }
    }
  }

  async function loadScorecard() {
    const card = await api('/api/scorecard');
    if (card) {
      const score = card.total_score !== undefined ? card.total_score : 1;
      const pill = $('#streak-count');
      if (pill) pill.textContent = score;
    }
  }

  // ==========================================================================
  // CONVERSATION & COMPOSER
  // ==========================================================================

  function appendMessage(sender, text) {
    const thread = $('#chat-thread');
    if (!thread) return;

    const msg = document.createElement('div');
    msg.className = sender === 'user' ? 'msg-user' : 'msg-pico';
    msg.textContent = stripEmojis(text);
    thread.appendChild(msg);

    thread.scrollTop = thread.scrollHeight;
    state.chatHistory.push({ sender, text, timestamp: new Date().toISOString() });
  }

  async function sendMessage(text) {
    const cleaned = text.trim();
    if (!cleaned) return;

    appendMessage('user', cleaned);
    playPop();

    const thread = $('#chat-thread');
    const typing = document.createElement('div');
    typing.className = 'msg-pico mono';
    typing.id = 'pico-typing';
    typing.textContent = 'Pico is thinking...';
    if (thread) {
      thread.appendChild(typing);
      thread.scrollTop = thread.scrollHeight;
    }

    const res = await api('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: cleaned })
    });

    const typingEl = $('#pico-typing');
    if (typingEl) typingEl.remove();

    if (res && (res.output || res.reply || res.message)) {
      const reply = res.output || res.reply || res.message;
      appendMessage('pico', reply);
      playPop();
    } else {
      appendMessage('pico', 'I processed your request, but received an empty response. How can I help further?');
    }

    loadTokens();
  }

  // ==========================================================================
  // ROUTINE SPINE & LIVING ARTIFACTS
  // ==========================================================================

  async function loadRoutineSpine() {
    const data = await api('/api/path');
    const list = $('#routine-list');
    const dropdownItems = $('#task-dropdown-items');
    const dropdownCount = $('#task-dropdown-count');

    if (!data || !data.day_path || data.day_path.length === 0) {
      if (list) list.innerHTML = '<div class="empty-state">No scheduled routine blocks found.</div>';
      return;
    }

    if (dropdownCount) dropdownCount.textContent = `${data.day_path.length} steps`;

    const html = data.day_path.map(item => {
      let savedCompleted = false;
      try {
        savedCompleted = localStorage.getItem(`pico_step_${item.id}`) === '1';
      } catch (e) {}
      return `
        <div class="routine-item ${savedCompleted ? 'completed' : ''}" data-id="${item.id}">
          <div class="routine-item-left">
            <div class="routine-checkbox" data-id="${item.id}">${savedCompleted ? '✓' : ''}</div>
            <div>
              <div class="routine-name">${stripEmojis(item.name)}</div>
              <div class="routine-time mono">${item.time}</div>
            </div>
          </div>
          <span class="mono-badge">${item.mode || 'routine'}</span>
        </div>
      `;
    }).join('');

    if (list) list.innerHTML = html;
    if (dropdownItems) dropdownItems.innerHTML = html;

    // Attach checkbox click events
    $$('.routine-checkbox').forEach(box => {
      box.addEventListener('click', (e) => {
        e.stopPropagation();
        const id = box.dataset.id;
        const parent = box.closest('.routine-item');
        if (!parent) return;

        const isDone = parent.classList.toggle('completed');
        box.textContent = isDone ? '✓' : '';
        try {
          if (isDone) {
            localStorage.setItem(`pico_step_${id}`, '1');
          } else {
            localStorage.removeItem(`pico_step_${id}`);
          }
        } catch (err) {}
        playPop();
      });
    });
  }

  async function loadArtifacts() {
    // 1. SIP Artifact
    const sip = await api('/api/artifacts/sip?amt=5000&cagr=15&years=26');
    if (sip) {
      const primary = $('#sip-primary-val');
      const secondary = $('#sip-secondary-val');
      const hisLine = $('#sip-his-line');
      if (primary && sip.primary) primary.textContent = sip.primary;
      if (secondary && sip.secondary) secondary.textContent = sip.secondary;
      if (hisLine && sip.his_line) hisLine.textContent = sip.his_line;
    }

    // 2. Goal Artifact
    const goal = await api('/api/artifacts/goal');
    if (goal) {
      const title = $('#goal-artifact-title');
      const primary = $('#goal-primary-val');
      const secondary = $('#goal-secondary-val');
      const hisLine = $('#goal-his-line');
      if (title && goal.title) title.textContent = goal.title;
      if (primary && goal.primary) primary.textContent = goal.primary;
      if (secondary && goal.secondary) secondary.textContent = goal.secondary;
      if (hisLine && goal.his_line) hisLine.textContent = goal.his_line;
    }
  }

  async function recalculateSIP() {
    const amt = $('#sip-input-amt')?.value || 5000;
    const cagr = $('#sip-input-cagr')?.value || 15;
    const years = $('#sip-input-years')?.value || 26;

    const data = await api(`/api/artifacts/sip?amt=${amt}&cagr=${cagr}&years=${years}`);
    if (data) {
      const primary = $('#sip-primary-val');
      const secondary = $('#sip-secondary-val');
      const hisLine = $('#sip-his-line');
      if (primary && data.primary) primary.textContent = data.primary;
      if (secondary && data.secondary) secondary.textContent = data.secondary;
      if (hisLine && data.his_line) hisLine.textContent = data.his_line;
      showToast('SIP recalculation updated');
      playPop();
    }
  }

  // ==========================================================================
  // MARKDOWN VIEWER & CONNECTORS
  // ==========================================================================

  async function loadMarkdownDoc() {
    const select = $('#doc-file-select');
    const viewer = $('#md-viewer-content');
    if (!select || !viewer) return;

    const filename = select.value;
    viewer.textContent = `Loading ${filename}...`;

    const data = await api(`/api/docs/${encodeURIComponent(filename)}`);
    if (data && data.content) {
      viewer.textContent = data.content;
      showToast(`Loaded ${filename}`);
      playPop();
    } else {
      viewer.textContent = `Failed to load document: ${filename}`;
    }
  }

  async function checkConnectors() {
    // 1. Chrome Watcher
    const chromeData = await api('/api/events/chrome');
    const chromeDot = $('#conn-chrome-dot');
    const chromeStatus = $('#conn-chrome-status');
    const chromeModeDot = $('#chrome-dot');
    const chromeContainer = $('#chrome-tabs');

    if (chromeData) {
      if (chromeDot) chromeDot.className = 'status-dot status-dot-sm online';
      if (chromeModeDot) chromeModeDot.className = 'status-dot status-dot-sm online';
      if (chromeStatus) chromeStatus.textContent = `${chromeData.tab_count || 0} tabs`;

      if (chromeContainer && chromeData.recent_tabs && chromeData.recent_tabs.length > 0) {
        chromeContainer.innerHTML = chromeData.recent_tabs.map(t => `
          <div class="watcher-entry">
            <span>${stripEmojis(t.title || t.url)}</span>
            <span class="mono">${t.domain || ''}</span>
          </div>
        `).join('');
      }
    }

    // 2. Gmail Watcher
    const gmailData = await api('/api/events/gmail');
    const gmailDot = $('#conn-gmail-dot');
    const gmailStatus = $('#conn-gmail-status');
    const gmailModeDot = $('#gmail-dot');
    const gmailContainer = $('#gmail-signals');

    if (gmailData) {
      const isConf = gmailData.configured;
      if (gmailDot) gmailDot.className = `status-dot status-dot-sm ${isConf ? 'online' : ''}`;
      if (gmailModeDot) gmailModeDot.className = `status-dot status-dot-sm ${isConf ? 'online' : ''}`;
      if (gmailStatus) gmailStatus.textContent = isConf ? `${gmailData.count || 0} signals` : 'unconfigured';

      if (gmailContainer) {
        if (gmailData.events && gmailData.events.length > 0) {
          gmailContainer.innerHTML = gmailData.events.map(ev => `
            <div class="watcher-entry">
              <span>${stripEmojis(ev.title || 'Email signal')}</span>
              <span class="mono">${ev.type || 'receipt'}</span>
            </div>
          `).join('');
        } else {
          gmailContainer.innerHTML = '<div class="empty-state">No email alerts recorded</div>';
        }
      }
    }

    // 3. Twilio
    const twilioStatus = $('#conn-twilio-status');
    const twilioDot = $('#conn-twilio-dot');
    if (twilioStatus) twilioStatus.textContent = 'ready';
    if (twilioDot) twilioDot.className = 'status-dot status-dot-sm online';
  }

  // ==========================================================================
  // MODE 2: MEMORY & REFLECTION
  // ==========================================================================

  async function loadMemorySection() {
    // 1. Facts
    const data = await api('/api/what-i-know');
    const container = $('#memory-cards');
    const badge = $('#memory-count-badge');

    if (data && data.facts && data.facts.length > 0) {
      if (badge) badge.textContent = `${data.facts.length} facts`;
      container.innerHTML = data.facts.map(fact => `
        <div class="memory-card">
          <div class="memory-key">${stripEmojis(fact.key)}</div>
          <div class="memory-val">${stripEmojis(String(fact.value))}</div>
          <div class="memory-meta mono">Source: ${fact.source} | Mode: ${fact.mode || 'general'}</div>
        </div>
      `).join('');
    } else {
      if (container) container.innerHTML = '<div class="empty-state">Hermes is still learning your preferences.</div>';
    }

    // 2. Reflection
    const rev = await api('/api/review');
    const revContainer = $('#review-cards');
    if (rev && rev.evening_review && revContainer) {
      revContainer.textContent = stripEmojis(rev.evening_review);
    }
  }

  // ==========================================================================
  // TOKENS & SETTINGS MODAL
  // ==========================================================================

  async function loadTokens() {
    const data = await api('/api/tokens');
    if (!data) return;

    const remaining = data.remaining || 0;
    const quota = data.monthly_quota || 40000000;
    const used = data.used || (quota - remaining);
    const pct = Math.min(100, Math.max(0, (used / quota) * 100));

    const tokenBadge = $('#token-badge');
    if (tokenBadge) {
      const remM = (remaining / 1000000).toFixed(1);
      tokenBadge.textContent = `${remM}M tokens left`;
    }

    const settingsCount = $('#settings-token-count');
    if (settingsCount) {
      settingsCount.textContent = `${used.toLocaleString()} / ${(quota / 1000000)}M`;
    }

    const fill = $('#token-fill');
    if (fill) {
      fill.style.width = `${pct}%`;
    }
  }

  function exportTranscript() {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(state.chatHistory, null, 2));
    const dlAnchor = document.createElement('a');
    const dateStr = new Date().toISOString().slice(0, 10);
    dlAnchor.setAttribute('href', dataStr);
    dlAnchor.setAttribute('download', `pico_chat_export_${dateStr}.json`);
    document.body.appendChild(dlAnchor);
    dlAnchor.click();
    dlAnchor.remove();
    showToast('Exported chat transcript JSON');
    playPop();
  }

  // ==========================================================================
  // STEALTH SCREEN (Boss Key Cover)
  // ==========================================================================

  function toggleStealth(force = null) {
    const screen = $('#stealth-screen');
    if (!screen) return;

    if (force !== null) {
      state.stealthMode = force;
    } else {
      state.stealthMode = !state.stealthMode;
    }

    if (state.stealthMode) {
      screen.classList.remove('hidden');
    } else {
      screen.classList.add('hidden');
    }
    playPop();
  }

  // ==========================================================================
  // INITIALIZATION & EVENT LISTENERS
  // ==========================================================================

  function initEventListeners() {
    // 1. Nav rail buttons
    $$('.nav-item').forEach(btn => {
      btn.addEventListener('click', () => {
        const mode = btn.dataset.mode;
        const panel = btn.dataset.panel;
        if (mode) switchMode(mode, panel);
      });
    });

    // 2. Mobile bottom nav buttons
    $$('.mobile-nav-item').forEach(btn => {
      btn.addEventListener('click', () => {
        const mode = btn.dataset.mode;
        const panel = btn.dataset.panel;
        if (mode) switchMode(mode, panel);
      });
    });

    // 3. Right canvas tab switcher buttons
    $$('#right-canvas-tabs .tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;
        if (tab) switchRightTab(tab);
        playPop();
      });
    });

    // 4. Settings modal close button
    $('#btn-close-settings')?.addEventListener('click', () => {
      $('#mode-settings')?.classList.remove('active');
      playPop();
    });

    // 5. Sound toggle in header
    $('#btn-sound')?.addEventListener('click', () => {
      state.soundEnabled = !state.soundEnabled;
      const toggleInSettings = $('#toggle-sound');
      if (toggleInSettings) toggleInSettings.checked = state.soundEnabled;
      const btn = $('#btn-sound');
      if (btn) btn.classList.toggle('muted', !state.soundEnabled);
      showToast(state.soundEnabled ? 'Tactile sound enabled' : 'Tactile sound muted');
      if (state.soundEnabled) playPop();
    });

    // 6. Sound toggle in Settings
    $('#toggle-sound')?.addEventListener('change', (e) => {
      state.soundEnabled = e.target.checked;
      const btn = $('#btn-sound');
      if (btn) btn.classList.toggle('muted', !state.soundEnabled);
      if (state.soundEnabled) playPop();
    });

    // 7. Task Dropdown toggle
    $('#btn-pico-tasks')?.addEventListener('click', (e) => {
      e.stopPropagation();
      const dd = $('#task-dropdown');
      if (dd) dd.classList.toggle('hidden');
      playPop();
    });

    document.addEventListener('click', (e) => {
      const dd = $('#task-dropdown');
      if (dd && !dd.classList.contains('hidden')) {
        if (!e.target.closest('#task-dropdown') && !e.target.closest('#btn-pico-tasks')) {
          dd.classList.add('hidden');
        }
      }
    });

    // 8. Composer Input & Send Button
    const chatInput = $('#chat-input');
    const btnSend = $('#btn-send');

    btnSend?.addEventListener('click', () => {
      if (chatInput && chatInput.value) {
        sendMessage(chatInput.value);
        chatInput.value = '';
      }
    });

    chatInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (chatInput.value) {
          sendMessage(chatInput.value);
          chatInput.value = '';
        }
      }
    });

    // 9. Quick Prompt Chips
    $$('.quick-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const prompt = chip.dataset.prompt;
        if (prompt) sendMessage(prompt);
      });
    });

    // 10. SIP Recalculate Button
    $('#btn-recalc-sip')?.addEventListener('click', recalculateSIP);

    // 11. Markdown Loader Button
    $('#btn-load-doc')?.addEventListener('click', loadMarkdownDoc);

    // 12. Export Buttons
    $('#btn-export')?.addEventListener('click', exportTranscript);
    $('#nav-download')?.addEventListener('click', exportTranscript);

    // 13. Stealth Screen Buttons
    $('#btn-stealth-start')?.addEventListener('click', () => toggleStealth(false));
    $('#btn-stealth-login')?.addEventListener('click', () => toggleStealth(false));

    // 14. Mascot click and keyboard triggers
    $('#stealth-mascot')?.addEventListener('click', () => {
      state.mascotClickCount++;
      if (state.mascotClickCount >= 3) {
        state.mascotClickCount = 0;
        toggleStealth(false);
      }
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        const now = Date.now();
        if (now - state.lastEscPress < 450) {
          toggleStealth();
        }
        state.lastEscPress = now;
      }
      if ((e.ctrlKey || e.metaKey) && e.key === '.') {
        toggleStealth();
      }
    });
  }

  // Application Startup
  async function init() {
    initEventListeners();

    // Safely run initial fetches without blocking
    try { await checkHealth(); } catch (e) {}
    try { await pollHeartbeat(); } catch (e) {}
    try { await loadScorecard(); } catch (e) {}
    try { await loadRoutineSpine(); } catch (e) {}
    try { await loadArtifacts(); } catch (e) {}
    try { await checkConnectors(); } catch (e) {}
    try { await loadMemorySection(); } catch (e) {}
    try { await loadTokens(); } catch (e) {}

    // Recurring background polls
    setInterval(pollHeartbeat, 30000);
    setInterval(checkHealth, 60000);
  }

  // Boot on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
