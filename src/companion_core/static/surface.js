"use strict";
// View and material preferences are local; all task facts are read from Surface.
const $ = id => {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Required studio element missing: ${id}`);
  return element;
};
const prefKey = "companion.ceramic.preferences.v1";
const media = matchMedia("(prefers-reduced-motion: reduce)");

const labels = (document.body.dataset.workEnabled==='true'&&window.CompanionReading?.states)||{UNKNOWN:"執行狀態未確認", CREATED:"正在準備", RUNNING:"正在執行", CANCEL_REQUESTED:"已請求停止，尚未確認取消",
  CANCELLED:"已確認取消", FAILED:"執行失敗", RESULT_PENDING_REVIEW:"成果等待審查",
  ACCEPTED:"成果已接受", REJECTED:"成果已拒絕", REVISION_REQUESTED:"已要求調整 · 新工作未執行"};
const resultStates = new Set(["RESULT_PENDING_REVIEW","ACCEPTED","REJECTED","REVISION_REQUESTED"]);
let tasks = [], selected = "", view = "glance", tab = "brief", offline = true;
let snapshot = null, target = null, initialized = false, selectionVersion = 0, readEpoch = 0;
let refreshPending = null, targetPending = null, starting = false, deciding = false;
let observationView = "summary", observationReading = false, observationScroll = 0, presentedState = null;
let readerTarget = null, readerRect = null, readerRestore = null, readerFocused = false, readerGesture = null;
const stopSubmitted = new Set(), reviewUncertain = new Set();
let prefs = {theme: "obsidian", motion: "auto", quality: "high"};
let storageAvailable = true, toastTimer, morph = null, pointerFrame = 0, revisionTarget = null;
let interactionCount = 0, morphCount = 0, interruptedCount = 0;
const animations = new Set();
const targetAnimations = new WeakMap();
const task = () => tasks.find(t => t.task_id === selected);
const reduced = () => prefs.motion === "reduced" || media.matches;
const contentText = (id, value) => { if ($(id).textContent !== value) $(id).textContent = value; };
try {
  const saved = JSON.parse(localStorage.getItem(prefKey));
  if (saved && ["obsidian", "umber", "porcelain"].includes(saved.theme)) prefs.theme = saved.theme;
  if (saved && ["auto", "full", "reduced"].includes(saved.motion)) prefs.motion = saved.motion;
  if (saved && ["high", "low"].includes(saved.quality)) prefs.quality = saved.quality;
} catch { storageAvailable = false; }

function animate(element, frames, options) {
  if (reduced() || !element.animate) return null;
  // Each persistent target owns one finite animation; replacement cancels its predecessor.
  const previous = targetAnimations.get(element);
  if (previous) previous.cancel();
  const animation = element.animate(frames, options);
  animations.add(animation);
  targetAnimations.set(element, animation);
  const release = () => {
    animations.delete(animation);
    if (targetAnimations.get(element) === animation) targetAnimations.delete(element);
  };
  animation.addEventListener("finish", release, {once: true});
  animation.addEventListener("cancel", release, {once: true});
  return animation;
}
function cancelAnimations() {
  for (const animation of animations) animation.cancel();
  animations.clear(); morph = null;
}
function toast(message) {
  contentText("toast", message);
  $("toast").classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("toast").classList.remove("visible"), 3600);
}
function applyPreferences(save = false) {
  document.body.dataset.theme = prefs.theme;
  document.body.dataset.motion = reduced() ? "reduced" : "full";
  document.body.dataset.quality = prefs.quality;
  $("motion-setting").value = prefs.motion;
  $("quality-setting").value = prefs.quality;
  document.querySelectorAll("[data-theme]").forEach(button => {
    if (button.tagName === "BUTTON") button.setAttribute("aria-pressed", String(button.dataset.theme === prefs.theme));
  });
  contentText("material-name", {obsidian: "OBSIDIAN", umber: "SMOKED UMBER", porcelain: "MOON PORCELAIN"}[prefs.theme]);
  contentText("motion-label", reduced() ? "低動態 · 即時切換" : "空間轉場 · 標準");
  if (reduced()) cancelAnimations();
  if (save) {
    try { localStorage.setItem(prefKey, JSON.stringify(prefs)); }
    catch { storageAvailable = false; }
    window.dispatchEvent(new Event('companion-preferences-change'));
  }
  contentText("preference-storage", storageAvailable ? "偏好僅儲存在此瀏覽器" : "瀏覽器未開放保存 · 偏好僅限本次");
}

window.companionMaterialPreferences = () => ({...prefs});
window.companionRestoreMaterial = value => {
  if (!value || !['obsidian','umber','porcelain'].includes(value.theme) || !['auto','full','reduced'].includes(value.motion) || !['high','low'].includes(value.quality)) return;
  prefs = {...value}; applyPreferences(false);
};

// Analytic damped spring: bounded undershoot/overshoot, sampled for native WAAPI.
// Geometry is interpolated on one persistent element, so text is never scaled.
function spring(t) {
  const damping = 8.7, frequency = 10.5;
  return 1 - Math.exp(-damping * t) * (Math.cos(frequency * t) + damping / frequency * Math.sin(frequency * t));
}
function geometry(box) {
  const stage = $("stage").getBoundingClientRect();
  // DOM rectangles include CSS zoom; WAAPI geometry uses unzoomed CSS units.
  const zoom = parseFloat(getComputedStyle(document.body).zoom) || 1;
  return {left: (box.left - stage.left) / zoom, top: (box.top - stage.top) / zoom,
    width: box.width / zoom, height: box.height / zoom};
}
function transition(next, focus = true) {
  if(document.body.dataset.chatEnabled === "true" && document.body.dataset.space === "chat") return;
  if (!["glance", "expanded", "observe"].includes(next) || next === view || (next !== "glance" && !task())) return;
  const element = $("vessel");
  const before = geometry(element.getBoundingClientRect());
  const oldRadius = parseFloat(getComputedStyle(element).borderTopLeftRadius);
  if (morph && morph.playState === "running") interruptedCount++;
  cancelAnimations();
  const oldView = view;
  if (next !== "observe") observationReading=false;
  view = next; interactionCount++;
  render();
  const after = geometry(element.getBoundingClientRect());
  const radius = parseFloat(getComputedStyle(element).borderTopLeftRadius);
  if (!reduced()) {
    const frames = Array.from({length: 42}, (_, i) => {
      const p = i / 41, s = i === 41 ? 1 : spring(p);
      const frame = {offset: p, borderRadius: `${oldRadius + (radius - oldRadius) * s}px`};
      for (const key of Object.keys(before)) frame[key] = `${before[key] + (after[key] - before[key]) * s}px`;
      return frame;
    });
    morph = animate(element, frames, {duration: 610, easing: "linear"});
    morphCount++;
    animate(next === "glance" ? $("glance-content") : $("expanded-content"), [{opacity: .25, transform: "translateY(7px)"}, {opacity: 1, transform: "translateY(0)"}], {duration: 270, delay: 70, easing: "cubic-bezier(.2,.75,.25,1)"});
    if (next === "observe" && oldView !== "observe") animate($("monitor"), [{opacity: 0, transform: "translateX(-24px)"}, {opacity: 1, transform: "translateX(0)"}], {duration: 360, delay: 100, easing: "cubic-bezier(.2,.8,.2,1)"});
    const index = ["glance", "expanded", "observe"].indexOf(next);
    const oldIndex = ["glance", "expanded", "observe"].indexOf(oldView);
    animate(document.querySelector(".switch-indicator"), [{transform: `translateX(calc(${oldIndex} * (100% + 3px)))`}, {transform: `translateX(calc(${index} * (100% + 3px)))`}], {duration: 370, easing: "cubic-bezier(.2,.85,.3,1)"});
  }
  // Prevent focus scrolling from fighting the object morph; narrow layouts scroll on demand.
  if (focus) $(next === "observe" ? "monitor-heading" : "task-title").focus({preventScroll: true});
}

function buildTaskTray() {
  const existing = [...$("task-items").children].map(b => b.dataset.task).join("|");
  if (existing !== tasks.map(t => t.task_id).join("|")) {
    $("task-items").replaceChildren(...tasks.map(t => {
      const button = document.createElement("button"); button.className = "task-tile"; button.dataset.task = t.task_id;
      const top = document.createElement("span"); top.className = "tile-top"; top.textContent = "唯讀工作";
      const title = document.createElement("span"); title.className = "tile-title"; title.textContent = t.intent;
      const status = document.createElement("span"); status.className = "tile-state work-status";
      button.append(top,title,status); button.onclick = () => window.nexusOpenWork ? window.nexusOpenWork(t.task_id) : selectTask(t.task_id); return button;
    }));
  }
  for (const button of $("task-items").children) {
    const t = tasks.find(t => t.task_id === button.dataset.task);
    button.setAttribute("aria-pressed", String(t.task_id === selected));
    button.dataset.state=button.querySelector('.tile-state').dataset.state=offline?'UNKNOWN':t.state;
    button.querySelector(".tile-state").textContent = offline ? "狀態未確認" : labels[t.state];
    button.setAttribute("aria-label", t.intent + "，" + (offline ? "狀態未確認" : labels[t.state]));
  }
}
function readyForReview() {
  return !offline && !deciding && target?.task_id === selected && target?.state === "RESULT_PENDING_REVIEW"
    && task()?.state === target.state && !reviewUncertain.has(selected);
}
function render() {
  const value = task(), state = value?.state, ownActive = selected && snapshot?.active?.task_id === selected;
  const workUnavailable = snapshot?.runtime === "工作執行端未連接；可查看與審查既有成果";
  const proposalRequired = snapshot?.runtime === "bounded-python-source-audit-v1";
  const saved = snapshot?.tasks.some(t => t.task_id === selected);
  const descriptions = {
    UNKNOWN:"此工作缺少可核對的執行結束記錄；不推定失敗、取消或完成。",
    CREATED:"正在準備工作，尚未取得執行進度。",
    RUNNING:"執行端正在處理。展開觀察可閱讀已回報事件；完成比例未提供。",
    CANCEL_REQUESTED:"停止要求已提出，仍等待執行端確認收尾。這不是已取消。",
    CANCELLED:"執行端已確認取消，此工作沒有可供審查的成果。",
    FAILED:"此次執行未取得可確認的成功結果。失敗不等於已確認取消。",
    RESULT_PENDING_REVIEW:saved ? "成果已保存，等待你閱讀並作出審查決定。" : "執行已有結果，但尚未讀到可安全審查的保存記錄。",
    ACCEPTED:"成果已接受，沒有授予寫檔、Git 或外部操作權限。",
    REJECTED:"成果已拒絕，保存的原始內容仍可閱讀。",
    REVISION_REQUESTED:"調整方向已保存，新工作尚未執行。"
  };
  const description = offline ? "目前資料未確認。斷線不代表工作已取消或成果已接受。" :
    value ? descriptions[state] : selected ? "此工作沒有可讀回的狀態；不推定完成或取消。" : workUnavailable ? "工程執行端尚未連接。可選取既有成果閱讀與審查，或返回對話。" : "可以交代閱讀公開內容、整理重點或釐清問題的唯讀工作。";
  const status = offline ? "狀態未確認" : labels[state] || (selected ? "工作狀態不可確認" : "尚未建立工作");
  document.body.dataset.view = view; document.body.dataset.offline = String(offline);
  $("studio-note").hidden = view !== "glance";
  $("glance-content").hidden = view !== "glance"; $("expanded-content").hidden = view === "glance";
  $("monitor").hidden = view !== "observe"; $("return").hidden = view === "glance";
  $("expand").hidden = view !== "glance"; $("observe").hidden = view === "glance";
  $("expand").disabled = !value; $("observe").disabled = !value;
  $("observe").setAttribute("aria-expanded",String(view === "observe"));
  $("observe").querySelector("span").textContent = view === "observe" ? "收合觀察" : "展開觀察";
  for (const b of document.querySelectorAll(".view-switch button")) {
    b.setAttribute("aria-pressed",String(b.dataset.view === view));
    b.disabled = b.dataset.view !== "glance" && !value;
  }
  document.querySelector(".switch-indicator").style.transform =
    `translateX(calc(${["glance","expanded","observe"].indexOf(view)} * (100% + 3px)))`;
  contentText("workspace-summary", offline ? "工作與待審成果目前未確認。" :
    (snapshot?.busy ? "有一項工作正在執行。" : workUnavailable ? "工程執行端尚未連接。" : "目前可以交代新工作。") + "\n" +
    (snapshot?.tasks.filter(t => t.state === "RESULT_PENDING_REVIEW").length || 0) + " 份成果等待審查。");
  contentText("runtime-label", workUnavailable ? "工程執行端未連接" : snapshot?.runtime === "synthetic-no-ai" ? "驗證環境 · 合成執行器，非實際 AI" : "本機 Companion · 唯讀執行");
  $("work-availability").hidden = !workUnavailable && (!proposalRequired || document.body.dataset.nexus==='true');
  contentText("work-availability",proposalRequired ? "受限專案查核已連接。請從對話建立提案，預覽並確認後才開始；不提供任意工程執行。" : workUnavailable ? "工程執行端尚未連接。這裡可閱讀與審查既有成果；目前無法開始新工作。" : "");
  contentText("task-number", "READ-ONLY WORK");
  contentText("task-title", value?.intent || (selected ? "選取的工作目前無法讀回" : workUnavailable ? "你的工作空間" : "交代一項工作"));
  contentText("project-label","LOCAL COMPANION"); contentText("task-description", description);
  contentText("task-id", selected || "尚未建立");
  contentText("monitor-id",ownActive ? ["RUNNING","CANCEL_REQUESTED"].includes(state) ? "目前執行工作" : "本次工作" : "已保存成果");
  contentText("monitor-task",value?.intent || "尚未選取工作");
  contentText("status-label",status); $("state-pill").dataset.state = offline ? "UNKNOWN" : state || "";
  contentText("execution-label", offline ? "目前未確認" : resultStates.has(state) ? "已取得結果" : status);
  contentText("review-label", offline ? "目前未確認" : resultStates.has(state) ? status : "尚未取得成果");
  contentText("glance-status",description); contentText("footer-status",status);
  contentText("detail-heading","工作內容"); contentText("detail-text",value?.intent || "尚未建立工作。");
  contentText("expected-output", resultStates.has(state) ? "已取得結果。請切換至「成果」閱讀保存的內容。" :
    "以本次工作內容為準；後端沒有提供另一份成果規格或完成比例。");
  contentText("task-notice", ownActive ? snapshot?.notice || "" : "");
  contentText("monitor-state",status); contentText("monitor-copy", description);
  $("monitor").dataset.state=offline ? "UNKNOWN" : state || "UNKNOWN";
  $("monitor").dataset.taskId=selected;
  contentText("monitor-execution",offline || !value ? "執行未確認" : resultStates.has(state) ? "執行已完成" :
    {UNKNOWN:"執行未確認",CREATED:"尚未開始",RUNNING:"執行中",CANCEL_REQUESTED:"取消待確認",CANCELLED:"已取消",FAILED:"執行失敗"}[state]);
  contentText("monitor-review",offline || !value ? "審查未確認" :
    {RESULT_PENDING_REVIEW:saved ? "等待人類審查" : "保存尚待確認",ACCEPTED:"成果已接受",REJECTED:"成果已拒絕",REVISION_REQUESTED:"調整方向已記錄"}[state] || "尚無可審查成果");
  contentText("monitor-origin",offline ? "連線或資料未確認" : ownActive ? "本機狀態讀回" : "已保存成果讀回");
  contentText("connection-label", offline ? "連線或資料未確認" : "已連接本機端");
  contentText("connection-banner", offline ? "連線或資料未確認；操作暫停，不代表停止或接受。" : "已連接本機端 · 成果與審查由後端保存");
  const uncertainStop = stopSubmitted.has(selected) && state === "RUNNING";
  if (uncertainStop) {
    contentText("footer-status","停止要求已送出，尚待確認；不會自動重試。");
    contentText("monitor-copy","停止要求是否送達尚未確認；不推定已取消，也不會自動重試。");
  }
  const lines = offline ? ["進度目前未確認。"] : ownActive ? snapshot.progress : [];
  const shown = lines.length ? lines : [ownActive ? "尚無可確認的進度事件。" : "歷史執行事件未保存，沒有可回放的進度。"];
  const key = JSON.stringify([selected,shown]);
  if ($("event-list").dataset.key !== key) {
    $("event-list").replaceChildren(...shown.map((line,i) => {
      const li=document.createElement("li"), number=document.createElement("span"), label=document.createElement("span");
      number.className="event-number"; number.textContent=String(i+1).padStart(2,"0");
      label.textContent=line; li.append(number,label); return li;
    })); $("event-list").dataset.key=key;
  }
  $("stop").hidden = !ownActive || !["RUNNING","CANCEL_REQUESTED"].includes(state);
  $("stop").disabled = offline || !ownActive || state !== "RUNNING" || stopSubmitted.has(selected);
  contentText("stop",state === "CANCEL_REQUESTED" ? "停止待確認" : "要求停止");
  $("new-task").disabled = offline || starting || !!snapshot?.busy || workUnavailable || proposalRequired;
  $("start").disabled = offline || starting || !!snapshot?.busy || workUnavailable || proposalRequired;
  $("result-tab").disabled = offline || !saved || !resultStates.has(state);
  $("reload-result").disabled = offline || !saved || !resultStates.has(state) || deciding || !!targetPending;
  if (!resultStates.has(state)) tab="brief";
  $("brief-tab").setAttribute("aria-selected",String(tab === "brief"));
  $("result-tab").setAttribute("aria-selected",String(tab === "result"));
  $("brief-content").hidden = tab !== "brief"; $("result-content").hidden = tab !== "result";
  const ownTarget = target?.task_id === selected;
  contentText("result-id", ownTarget ? target.result_id : "尚未讀取");
  contentText("result-title", "工作成果");
  if(ownTarget&&document.body.dataset.workEnabled==='true') window.CompanionReading.result($("result-text"),target.result,target.provider==='bounded-python-source-audit-v1');
  else { if(document.body.dataset.workEnabled==='true')window.CompanionReading.result($("result-text"),'');contentText("result-text", ownTarget ? target.result : offline ? "成果目前無法確認，請重新連線後讀取。" :
    reviewUncertain.has(selected) ? "審查是否保存尚未確認。請按「重新讀取成果」確認指定工作；不會自動重試。" :
    targetPending ? "正在讀取指定成果…" : "尚未讀取指定成果，請重新讀取。"); }
  $("review-actions").hidden = !saved || !resultStates.has(state) || (ownTarget && target.state !== "RESULT_PENDING_REVIEW");
  for (const id of ["accept","revise","reject"]) $(id).disabled = !readyForReview();
  $("revision-submit").disabled = !readyForReview() || !revisionTarget ||
    revisionTarget.taskId !== selected || revisionTarget.resultId !== target?.result_id;
  $("review-receipt").hidden = !ownTarget || !["ACCEPTED","REJECTED","REVISION_REQUESTED"].includes(target.state);
  contentText("receipt-label",ownTarget ? labels[target.state] : "");
  contentText("revision-receipt", ownTarget && target.revision ? "已記錄調整方向：" + target.revision.intent + "。新工作尚未執行。" : "");
  buildTaskTray();
  window.dispatchEvent(new CustomEvent('companion-state',{detail:{tasks,selected,offline,workspace:snapshot?.workspace,runtime:snapshot?.runtime}}));
  $("open-reader").disabled = offline || !ownTarget;
  $("detail-main").setAttribute("aria-busy",String(!!targetPending));
  contentText("start",starting ? "正在提交，等待確認…" : "建立並開始工作");
  renderObservation(ownActive);
  renderReader();
  // Only a freshly observed change on this same task earns an attention cue.
  // Polling, replaying history, and selecting another task do not replay completion.
  if (presentedState?.id===selected && !presentedState.offline && !offline && presentedState.state!==state) {
    animate($("state-pill"),[{opacity:.45},{opacity:1}],{duration:360,easing:"ease-out"});
    animate(document.querySelector(".monitor-state"),[{opacity:.55,transform:"translateY(4px)"},{opacity:1,transform:"none"}],{duration:300,easing:"ease-out"});
    if(state==="RESULT_PENDING_REVIEW" && saved) animate($(view==="glance" ? "expand" : "result-tab"),
      [{boxShadow:"inset 0 -2px 0 transparent"},{boxShadow:"inset 0 -2px 0 var(--accent)",offset:.35},{boxShadow:"inset 0 -2px 0 transparent"}],
      {duration:1200,easing:"ease-out"});
  }
  presentedState={id:selected,state,offline};
}
function renderObservation(ownActive) {
  document.body.dataset.observationReading=String(observationReading);
  $("monitor").dataset.reading=String(observationReading);
  $("expand-observation").setAttribute("aria-expanded",String(observationReading));
  $("expand-observation").setAttribute("aria-label",observationReading ? "返回觀察面板" : "展開觀察閱讀");
  $("expand-observation").querySelector("use").setAttribute("href",observationReading ? "#i-back" : "#i-expand");
  $("close-monitor").setAttribute("aria-label",observationReading ? "返回觀察面板" : "收合觀察");
  $("close-monitor").querySelector("use").setAttribute("href",observationReading ? "#i-back" : "#i-close");
  $("observation-summary").setAttribute("aria-pressed",String(observationView === "summary"));
  $("observation-details").setAttribute("aria-pressed",String(observationView === "details"));
  $("observation-summary-panel").hidden = observationView !== "summary";
  $("observation-detail-panel").hidden = observationView !== "details";
  const observation = !offline && ownActive && snapshot.observation?.task_id === selected ? snapshot.observation : null;
  const events = observation?.events || [];
  contentText("observation-availability",offline ? "連線或資料未確認，詳細事件暫時不可讀取。" :
    !ownActive ? "歷史事件沒有保存；只有已保存成果與審查可讀回。" :
    !observation ? "目前未提供詳細事件。" :
    "Core 階段回報；工具名稱、命令、工具輸出與逐項完成狀態未提供。" +
      (observation.omitted ? " 僅保留最近 128 個事件，較早事件已省略。" : ""));
  contentText("observation-error",!offline && ownActive ? snapshot.notice || "" : "");
  const key = JSON.stringify([selected,events]);
  if ($("detail-events").dataset.key !== key) {
    $("detail-events").replaceChildren(...events.map(event => {
      const li=document.createElement("li"),title=document.createElement("strong"),status=document.createElement("small"),detail=document.createElement("p");
      li.dataset.sequence=String(event.sequence);li.dataset.kind=event.kind;li.dataset.confirmation=event.confirmation;li.dataset.taskId=event.task_id;
      title.textContent=event.title;status.textContent=event.confirmation === "confirmed" ? "Core 已確認" : "事件已回報 · 未提供逐項完成狀態";
      detail.textContent=event.detail;li.append(title,status,detail);return li;
    }));$("detail-events").dataset.key=key;
  }
}
function switchObservation(next) {
  if(next===observationView) return;
  observationView=next;render();
  $("observation-scroll").scrollTo(0,0);
  animate($(next==="details" ? "observation-detail-panel" : "observation-summary-panel"),
    [{opacity:.35,transform:"translateY(7px)"},{opacity:1,transform:"none"}],{duration:220,easing:"cubic-bezier(.2,.8,.2,1)"});
}
function setObservationReading(expanded,focus=true) {
  if(view!=="observe" || observationReading===expanded) return;
  if(expanded) observationScroll=$("observation-scroll").scrollTop;
  observationReading=expanded;render();
  if(!expanded) $("observation-scroll").scrollTo(0,observationScroll);
  animate($("monitor"),[{opacity:.6,transform:"translateY(8px)"},{opacity:1,transform:"none"}],{duration:260,easing:"cubic-bezier(.2,.8,.2,1)"});
  if(focus) $(expanded ? "observation-scroll" : "expand-observation").focus({preventScroll:true});
}
function renderReader() {
  if (!$("reader").open || !readerTarget) return;
  const saved=snapshot?.tasks.find(t=>t.task_id===readerTarget.task_id);
  contentText("reader-context",readerTarget.task_id === selected ? "目前工作的完整成果。閱讀不會作出審查決定。" : "正在閱讀另一項工作的成果。返回會選取這份成果所屬的工作。");
  contentText("reader-status",offline ? "離線 · 顯示上次讀取的成果，審查狀態未確認。" :
    saved ? labels[saved.state] : "此工作的最新狀態未確認；顯示上次讀取的成果。");
  $("reader-return").disabled = !tasks.some(t=>t.task_id===readerTarget.task_id);
}
function fitReader(rect) {
  const maxW=Math.max(1,innerWidth-24),maxH=Math.max(1,innerHeight-24);
  const width=Math.min(maxW,Math.max(Math.min(420,maxW),rect.width));
  const height=Math.min(maxH,Math.max(Math.min(360,maxH),rect.height));
  return {width,height,left:Math.max(12,Math.min(innerWidth-width-12,rect.left)),
    top:Math.max(12,Math.min(innerHeight-height-12,rect.top))};
}
function placeReader(rect) {
  readerRect=fitReader(rect);
  for(const [name,value] of Object.entries(readerRect)) $("reader").style[name]=value+"px";
}
function endReaderGesture() {
  if(readerGesture) {
    if(readerGesture.element.hasPointerCapture(readerGesture.id)) readerGesture.element.releasePointerCapture(readerGesture.id);
    readerGesture=null;
  }
}
function openReader() {
  if(offline || !target || target.task_id !== selected) return;
  readerTarget={task_id:target.task_id,result_id:target.result_id,result:target.result,intent:target.intent};
  contentText("reader-title",readerTarget.intent);
  if(document.body.dataset.workEnabled==='true')window.CompanionReading.result($("reader-text"),readerTarget.result,target.provider==='bounded-python-source-audit-v1');
  else contentText("reader-text",readerTarget.result);
  contentText("reader-task-id",readerTarget.task_id);contentText("reader-result-id",readerTarget.result_id);
  readerFocused=false;$("reader").dataset.focused="false";$("reader-focus").setAttribute("aria-pressed","false");
  contentText("reader-focus","專注閱讀");
  placeReader(readerRect || {width:Math.min(960,innerWidth*.86),height:Math.min(760,innerHeight*.86),left:innerWidth*.07,top:innerHeight*.07});
  if(!$("reader").open) $("reader").show();
  renderReader();$("reader-body").scrollTo(0,0);
  animate($("reader"),[{opacity:.3,transform:"translateY(12px) scale(.985)"},{opacity:1,transform:"none"}],{duration:280,easing:"cubic-bezier(.2,.8,.2,1)"});
  $("reader-body").focus({preventScroll:true});
}
function closeReader(focus=true) {
  endReaderGesture();
  targetAnimations.get($("reader"))?.cancel();
  $("reader").close();readerTarget=null;
  if(readerFocused && readerRestore) placeReader(readerRestore);
  readerFocused=false;
  if(focus) ($("open-reader").disabled ? $("task-title") : $("open-reader")).focus({preventScroll:true});
}
function toggleReaderFocus() {
  endReaderGesture();readerFocused=!readerFocused;
  if(readerFocused) {readerRestore={...readerRect};placeReader({left:12,top:12,width:innerWidth-24,height:innerHeight-24});}
  else if(readerRestore) placeReader(readerRestore);
  $("reader").dataset.focused=String(readerFocused);$("reader-focus").setAttribute("aria-pressed",String(readerFocused));
  contentText("reader-focus",readerFocused ? "恢復視窗" : "專注閱讀");
  animate($("reader-body"),[{opacity:.5,transform:"translateY(5px)"},{opacity:1,transform:"none"}],{duration:220,easing:"ease-out"});
}
function readerPointer(element,mode) {
  element.addEventListener("pointerdown",event=>{
    if(event.button !== 0 || readerFocused || (mode==="move" && event.target.closest("button"))) return;
    event.preventDefault();endReaderGesture();targetAnimations.get($("reader"))?.cancel();
    readerGesture={element,id:event.pointerId,mode,x:event.clientX,y:event.clientY,rect:{...readerRect}};
    element.setPointerCapture(event.pointerId);
  });
  element.addEventListener("pointermove",event=>{
    if(!readerGesture || readerGesture.element!==element || readerGesture.id!==event.pointerId) return;
    const {rect,mode,x,y}=readerGesture,dx=event.clientX-x,dy=event.clientY-y;
    placeReader(mode==="move" ? {...rect,left:rect.left+dx,top:rect.top+dy} : {...rect,width:rect.width+dx,height:rect.height+dy});
  });
  for(const event of ["pointerup","pointercancel","lostpointercapture"]) element.addEventListener(event,()=>{readerGesture=null;});
  element.addEventListener("keydown",event=>{
    if(event.target!==element || readerFocused || !["ArrowLeft","ArrowRight","ArrowUp","ArrowDown"].includes(event.key)) return;
    event.preventDefault();const amount=event.shiftKey ? 60 : 24;
    const dx=event.key==="ArrowLeft" ? -amount : event.key==="ArrowRight" ? amount : 0;
    const dy=event.key==="ArrowUp" ? -amount : event.key==="ArrowDown" ? amount : 0;
    placeReader(mode==="move" ? {...readerRect,left:readerRect.left+dx,top:readerRect.top+dy} : {...readerRect,width:readerRect.width+dx,height:readerRect.height+dy});
  });
}
async function api(path,body) {
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(),8000);
  try {
    const response = await fetch(path,{method:body === undefined ? "GET" : "POST", cache:"no-store",signal:controller.signal,
      headers:body === undefined ? {} : {"Content-Type":"application/json","X-Companion-UI":"1"},
      body:body === undefined ? undefined : JSON.stringify(body)});
    if (!response.ok) throw new Error("Operation unconfirmed");
    return await response.json();
  } finally { clearTimeout(timer); }
}
function disconnected() {
  offline = true; target=null; selectionVersion++; render();
}
function validTask(t) {
  return t && typeof t.task_id === "string" && typeof t.intent === "string" && Object.hasOwn(labels,t.state);
}
async function refresh() {
  if (refreshPending) { await refreshPending; return; }
  const epoch=readEpoch;
  refreshPending=(async () => {
    try {
      const state=await api("/api/state");
      if (epoch !== readEpoch) return;
      if (!Array.isArray(state.tasks) || !state.tasks.every(validTask) || !Array.isArray(state.progress) ||
        !state.progress.every(s => typeof s === "string") || typeof state.busy !== "boolean" || state.authority !== "READ_ONLY" ||
        (state.active !== null && !validTask(state.active))) throw new Error("Unknown state");
      if (state.observation && (state.observation.task_id !== (state.active?.task_id || null) ||
        !Array.isArray(state.observation.events) || state.observation.events.length>128 ||
        !state.observation.events.every(e=>e.task_id===state.observation.task_id && Number.isInteger(e.sequence) && e.sequence>0 &&
          typeof e.title==="string" && typeof e.detail==="string" && typeof e.kind==="string" &&
          ["reported","confirmed"].includes(e.confirmation)))) throw new Error("Unknown observation identity");
      const previousState=task()?.state;
      snapshot=state; offline=false;
      tasks=[...state.tasks];
      if (state.active && !tasks.some(t => t.task_id === state.active.task_id)) tasks.unshift(state.active);
      if (!initialized) {initialized=true; if (state.active) selected=state.active.task_id;}
      if (target && (target.task_id !== selected || task()?.state !== target.state)) {target=null;selectionVersion++;}
      render();
      // A persisted summary authorizes a read, never a decision or new execution.
      if (tab === "result" && !target && !deciding && !reviewUncertain.has(selected) &&
        state.tasks.some(t=>t.task_id===selected) && (!targetPending || previousState !== task()?.state)) void openTarget();
    } catch {if (epoch === readEpoch) disconnected();}
  })();
  try {await refreshPending;} finally {refreshPending=null;}
}
async function freshAfterMutation() {
  ++readEpoch;
  if (refreshPending) await refreshPending;
  await refresh();
}
function selectTask(id) {
  if (id === selected || !tasks.some(t=>t.task_id===id)) return;
  selected=id; target=null; selectionVersion++; tab="brief"; interactionCount++; render();
  animate($("vessel-intro"),[{opacity:.35,transform:"translateY(5px)"},{opacity:1,transform:"none"}],{duration:250,easing:"ease-out"});
  animate($("brief-content"),[{opacity:.3,transform:"translateY(6px)"},{opacity:1,transform:"none"}],{duration:220,easing:"ease-out"});
  if(view==="observe") animate($("observation-scroll"),[{opacity:.4},{opacity:1}],{duration:220,easing:"ease-out"});
  $("detail-main").scrollTo(0,0);
}
async function openTarget(explicit=false) {
  if (offline || !selected || !resultStates.has(task()?.state) || !snapshot.tasks.some(t=>t.task_id===selected) || deciding) return;
  const id=selected,version=++selectionVersion;
  target=null; render();
  const request=(async () => {
    try {
      const value=await api("/api/target",{task_id:id});
      if (id !== selected || version !== selectionVersion) return;
      if (value.task_id !== id || typeof value.result_id !== "string" || !value.result_id ||
        typeof value.result !== "string" || value.authority !== "READ_ONLY" || !resultStates.has(value.state)) throw new Error("Identity mismatch");
      target=value;
      animate($("result-text"),[{opacity:.3,transform:"translateY(5px)"},{opacity:1,transform:"none"}],{duration:240,easing:"ease-out"});
      if (explicit) reviewUncertain.delete(id);
    } catch {if(id===selected && version===selectionVersion) disconnected();}
  })();
  targetPending=request;
  render();
  try {await request;} finally {if(targetPending===request) targetPending=null;render();}
}
async function decide(action,revision=null,exact=null) {
  if (!readyForReview()) return false;
  if (exact && (exact.taskId !== target.task_id || exact.resultId !== target.result_id)) return false;
  const identity={task_id:target.task_id,result_id:target.result_id},version=selectionVersion;
  deciding=true; ++readEpoch; render(); let confirmed=false;
  try {
    const value=await api("/api/review",{...identity,action,revision_intent:revision});
    if (value.task_id !== identity.task_id || value.result_id !== identity.result_id ||
      value.state !== {accept:"ACCEPTED",reject:"REJECTED",revise:"REVISION_REQUESTED"}[action]) throw new Error("Identity mismatch");
    confirmed=true;
    if(selected===identity.task_id && version===selectionVersion) target=value;
    toast("審查決定已保存，未授予額外執行或外部權限。");
  } catch {
    reviewUncertain.add(identity.task_id);
    if(selected===identity.task_id && version===selectionVersion) disconnected();
    toast("審查是否保存尚未確認。請重新開啟指定成果讀回；不會自動重試。");
  } finally {deciding=false; await freshAfterMutation();render();}
  return confirmed;
}
function showDialog(id) {
  endReaderGesture(); cancelAnimations(); $(id).showModal();
  animate($(id),[{opacity:0,transform:"translateY(10px) scale(.97)"},{opacity:1,transform:"none"}],{duration:240,easing:"cubic-bezier(.2,.8,.2,1)"});
}
for (const button of document.querySelectorAll(".view-switch button")) button.onclick=()=>transition(button.dataset.view);
$("expand").onclick=()=>transition("expanded"); $("return").onclick=()=>transition("glance");
$("observe").onclick=()=>transition(view === "observe" ? "expanded" : "observe");
$("close-monitor").onclick=()=>observationReading ? setObservationReading(false) : transition("expanded");
$("expand-observation").onclick=()=>setObservationReading(!observationReading);
$("observation-preferences").onclick=()=>showDialog("settings-dialog");
$("brief-tab").onclick=()=>{tab="brief";render();$("detail-main").scrollTo(0,0);};
$("result-tab").onclick=async()=>{if($("result-tab").disabled)return;tab="result";render();await openTarget(true);$("detail-main").scrollTo(0,0);};
$("reload-result").onclick=()=>openTarget(true);
$("open-reader").onclick=()=>openReader();
$("reader-close").onclick=()=>closeReader();
$("reader-focus").onclick=()=>toggleReaderFocus();
$("reader-preferences").onclick=()=>showDialog("settings-dialog");
$("reader-return").onclick=async()=>{
  const id=readerTarget?.task_id;if(!id || !tasks.some(t=>t.task_id===id)) return;
  closeReader(false);selectTask(id);transition("expanded",false);tab="result";render();await openTarget(true);$("task-title").focus();
};
$("observation-summary").onclick=()=>switchObservation("summary");
$("observation-details").onclick=()=>switchObservation("details");
readerPointer($("reader-handle"),"move");readerPointer($("reader-resize"),"resize");
$("refresh").onclick=async()=>{await refresh();if(!offline && tab === "result") await openTarget(true);};
$("stop").onclick=async()=>{
  const value=task();
  if (offline || $("stop").disabled || value?.task_id !== snapshot?.active?.task_id ||
    value?.state !== "RUNNING" || stopSubmitted.has(selected)) return;
  const id=selected; stopSubmitted.add(id);++readEpoch;render();
  try {
    const value=await api("/api/cancel",{task_id:id});
    if(value.task_id!==id || !["CANCEL_REQUESTED","CANCELLED","FAILED","RESULT_PENDING_REVIEW"].includes(value.state)) throw new Error("Identity mismatch");
  } catch {disconnected();toast("停止要求未確認，不會自動重試。斷線不代表已停止。");}
  await freshAfterMutation();
};
$("accept").onclick=()=>decide("accept"); $("reject").onclick=()=>decide("reject");
$("revise").onclick=()=>{
  if(!readyForReview()) return;
  revisionTarget={taskId:target.task_id,resultId:target.result_id};
  contentText("revision-target",task().intent); contentText("revision-message","");
  $("revision-intent").value="";render();showDialog("revision-dialog");
};
$("revision-form").onsubmit=async event=>{
  event.preventDefault(); const intent=$("revision-intent").value.trim();
  if(!intent) {$("revision-intent").focus();return;}
  if(await decide("revise",intent,revisionTarget)) $("revision-dialog").close();
  else contentText("revision-message","調整是否保存尚未確認，請關閉後重新讀取指定成果。");
};
$("preferences").onclick=()=>showDialog("settings-dialog"); $("help").onclick=()=>showDialog("help-dialog");
$("new-task").onclick=()=>{if($("new-task").disabled)return;$("new-intent").value="";contentText("start-message","");showDialog("new-dialog");};
$("new-form").onsubmit=async event=>{
  event.preventDefault();const intent=$("new-intent").value.trim();
  if(!intent || starting || offline || snapshot?.busy || $("start").disabled) return;
  starting=true;++readEpoch;render();contentText("start-message","正在提交工作，等待本機端確認…");
  try {
    const value=await api("/api/start",{intent});
    if(typeof value.task_id !== "string" || !value.task_id) throw new Error("Unknown task");
    selected=value.task_id;target=null;++selectionVersion;tab="brief";$("new-dialog").close();
    toast("工作已建立。展開或返回只改變檢視。");
  } catch {disconnected();contentText("start-message","工作是否建立尚未確認；不會自動重試。請先關閉並讀回目前工作。");}
  finally {starting=false;await freshAfterMutation();render();}
};
for (const button of document.querySelectorAll("button[data-theme]")) button.onclick = () => {
  prefs.theme = button.dataset.theme; applyPreferences(true); interactionCount++;
};
$("motion-setting").onchange = () => {prefs.motion = $("motion-setting").value; applyPreferences(true);};
$("quality-setting").onchange = () => {prefs.quality = $("quality-setting").value; applyPreferences(true);};
media.addEventListener("change", () => applyPreferences());
for (const button of document.querySelectorAll("[data-close]")) button.onclick = () => button.closest("dialog").close();
for (const dialog of document.querySelectorAll("dialog")) dialog.addEventListener("click", event => {
  if (event.target !== dialog) return;
  const box = dialog.getBoundingClientRect();
  if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
});
document.addEventListener("keydown", event => {
  if(document.body.dataset.chatEnabled === "true" && document.body.dataset.space === "chat") return;
  if ($("reader").open && event.key==="Escape" && !event.target.closest('#companion-panel, #companion-mini') && !document.querySelector("dialog[open]:not(#reader):not(#companion-panel)")) {
    event.preventDefault();closeReader();return;
  }
  if (document.querySelector("dialog[open]:not(#companion-panel)") || event.altKey || event.ctrlKey || event.metaKey || event.target.closest("input, textarea, select, [contenteditable], #companion-panel, #companion-mini")) return;
  if(event.key==="Escape" && observationReading) {event.preventDefault();setObservationReading(false);return;}
  if (["1", "2", "3"].includes(event.key)) {event.preventDefault(); transition({1: "glance", 2: "expanded", 3: "observe"}[event.key]);}
  if (event.key === "Escape" && view !== "glance") {event.preventDefault(); transition(view === "observe" ? "expanded" : "glance");}
  if (event.key === "?") showDialog("help-dialog");
});
$("vessel").addEventListener("pointermove", event => {
  if (reduced() || prefs.quality !== "high" || event.pointerType === "touch" || pointerFrame) return;
  const x = event.clientX, y = event.clientY;
  pointerFrame = requestAnimationFrame(() => {
    pointerFrame = 0;
    if (reduced() || prefs.quality !== "high") return;
    const box = $("vessel").getBoundingClientRect();
    $("vessel").querySelector(".material-light").style.setProperty("--px", `${(x - box.left) / box.width * 100}%`);
    $("vessel").querySelector(".material-light").style.setProperty("--py", `${(y - box.top) / box.height * 100}%`);
  });
}, {passive: true});
window.addEventListener("resize", () => {
  cancelAnimations();endReaderGesture();
  if($("reader").open) placeReader(readerFocused ? {left:12,top:12,width:innerWidth-24,height:innerHeight-24} : readerRect);
});
document.addEventListener("visibilitychange", () => {if (document.hidden) cancelAnimations();});

// Read-only projection for browser evidence. It offers no execution or review setter.
window.surfaceInspection = () => ({view,selected,tab,offline,reduced:reduced(),preferences:{...prefs},
  task:task() ? {...task()} : null,result:target ? {task_id:target.task_id,result_id:target.result_id,state:target.state} : null,
  observationView,observationReading,reader:readerTarget ? {task_id:readerTarget.task_id,result_id:readerTarget.result_id,focused:readerFocused,bounds:{...readerRect}} : null,
  activeAnimations:[...animations].filter(a=>a.playState==="running").length,morphs:morphCount,interrupted:interruptedCount});

// Navigation only: the destination is re-read from the existing Surface.
let workNavigation = 0;
window.cancelCompanionWorkNavigation = () => { ++workNavigation; };
window.openCompanionWork = async id => {
  const navigation=++workNavigation;
  // Clear the previous identity before the read: a missing destination must never
  // leave another task's result or review controls on screen.
  if ($('reader').open) closeReader(false);
  initialized=true;selected=id;target=null;++selectionVersion;tab='brief';render();
  await refresh();if(navigation!==workNavigation)return;
  if(offline || !task()){view='glance';render();return;}
  transition('expanded');
  if (resultStates.has(task()?.state)) {tab='result';await openTarget();if(navigation===workNavigation)render();}
};
async function poll() {
  if (!starting && !deciding) await refresh();
  setTimeout(poll,1000);
}
applyPreferences();render();poll();
