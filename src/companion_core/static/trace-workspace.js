/* Presentation only. The chat and native-work controllers own all authority and data. */
(() => {
  if (window.nexusComparisonLayout || document.body.dataset.workEnabled !== 'true') return;
  const body = document.body;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const preferenceKey = 'nexus.trace.material.v1';
  const scroller = document.getElementById('chat-messages');
  const template = document.getElementById('trace-presence-template');
  const materialButton = template.content.querySelector('.trace-material-toggle');
  let enabled = true;
  try { enabled = localStorage.getItem(preferenceKey) !== 'off'; } catch {}
  let presence, stage, toggle, inView = false, mount, initializing, failed = false, suspended = false;
  let frame = 640;
  const intersection = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (entry.target === stage) inView = entry.isIntersecting;
    }
    sync();
  });

  function release() {
    if (!mount) return;
    frame = mount.getCurrentFrame();
    const active = mount;
    mount = null;
    active.dispose();
  }

  function canRender() {
    return Boolean(stage?.isConnected && inView && enabled && !failed &&
      !document.hidden && !suspended && !reduced.matches &&
      body.dataset.motion !== 'reduced' && body.dataset.quality !== 'low');
  }

  function sync() {
    if (!canRender()) { release(); return; }
    if (mount || initializing) return;
    initializing = import('/trace-liquid-metal.js').then(({createMaterial}) => {
      if (!canRender()) return;
      const started = performance.now();
      mount = createMaterial(stage, frame);
      stage.dataset.renderMs = String(Math.round(performance.now() - started));
      const active = mount;
      active.canvasElement.addEventListener('webglcontextlost', () => {
        if (mount !== active) return;
        failed = true;
        release();
      }, {once:true});
    }).catch(() => {
      failed = true;
      stage?.querySelector('canvas')?.remove();
    }).finally(() => { initializing = null; });
  }

  function updatePresence() {
    if (presence?.isConnected) return;
    release();
    if (stage) intersection.unobserve(stage);
    presence = stage = toggle = null;
    inView = false;
  }

  new MutationObserver(updatePresence).observe(scroller, {childList:true});
  new MutationObserver(sync).observe(body, {attributes:true, attributeFilter:['data-motion','data-quality']});
  reduced.addEventListener('change',sync);
  document.addEventListener('visibilitychange',sync);
  window.addEventListener('pagehide',() => {suspended = true; release();});
  window.addEventListener('pageshow',() => {suspended = false; sync();});

  function renderPresence(container) {
    updatePresence();
    if (presence) return;
    const content = template.content.cloneNode(true);
    presence = content.firstElementChild;
    stage = content.querySelector('.trace-material');
    toggle = content.querySelector('.trace-material-toggle');
    function label() {
      toggle.setAttribute('aria-pressed',String(enabled));
      toggle.textContent = enabled ? materialButton.textContent + '：開' : materialButton.textContent + '：關';
    }
    toggle.onclick = () => {
      enabled = !enabled;
      try { localStorage.setItem(preferenceKey,enabled ? 'on' : 'off'); } catch {}
      label();
      sync();
    };
    label();
    container.append(presence);
    intersection.observe(stage);
  }

  const eventNames = Object.freeze({
    connecting:'主機開始連接原生 Codex', session_bound:'已取得原生 thread',
    turn_bound:'已取得原生 turn', receiving_result:'收到模型內容事件',
    cancel_requested:'已向原生執行提出停止請求', completed:'原生執行回報完成',
    failed:'已記錄執行失敗', cancelled:'已確認停止', unknown:'終態仍未確認',
    reconciled:'已嘗試核對原生紀錄'
  });

  function element(tag, value, className) {
    const result = document.createElement(tag);
    result.textContent = value;
    if (className) result.className = className;
    return result;
  }

  function timeline(events, {empty = true} = {}) {
    if (!Array.isArray(events) || !events.length) {
      return empty ? element('p','目前沒有已記錄的原生執行事件。','trace-empty') : null;
    }
    const list = element('ol','','trace-events');
    list.setAttribute('aria-label','主機已記錄的工作事件');
    for (const event of events) {
      const entry = element('li','');
      const name = Object.hasOwn(eventNames,event.kind) ? eventNames[event.kind] : '主機記錄的事件';
      const parsed = new Date(typeof event.at === "string" ? event.at : NaN);
      const timestamp = element('time',Number.isFinite(parsed.getTime())
        ? parsed.toLocaleString('zh-TW',{hour12:false}) : '時間未確認');
      if (Number.isFinite(parsed.getTime())) {
        timestamp.dateTime = parsed.toISOString();
        timestamp.title = parsed.toISOString();
      }
      entry.append(timestamp,element('span',name));
      list.append(entry);
    }
    return list;
  }

  window.NexusTrace = {renderPresence,timeline};
})();

