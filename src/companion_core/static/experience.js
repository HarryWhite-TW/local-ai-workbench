// Appended only by the opt-in synthetic fixture. Reuse the incumbent API,
// cancellation, stale-read guards and exact Task / Result / Review bindings.
const incumbentExperience = {render, renderObservation, selectTask, openReader, toggleReaderFocus};
const experienceEase = "cubic-bezier(.16,1,.3,1)";
let experiencePresented = null, experienceScenario = "";

function experienceBoxes() {
  return new Map(["vessel","monitor"].map(id => {
    const element=$(id), box=element.getBoundingClientRect();
    return [id, box.width && box.height ? box : null];
  }));
}
function experienceLayout(update) {
  // Capture an interrupted animation at its current visual position, then
  // apply the final layout immediately. There is no input lock or delayed state.
  const before=experienceBoxes();
  cancelAnimations();update();
  for (const [id,after] of experienceBoxes()) {
    if (!after) continue;
    const old=before.get(id), element=$(id);
    if (old) {
      animate(element,[
        {transformOrigin:"0 0",transform:`translate(${old.left-after.left}px,${old.top-after.top}px) scale(${old.width/after.width},${old.height/after.height})`},
        {transformOrigin:"0 0",transform:"none"}
      ],{duration:620,easing:experienceEase});
    } else {
      animate(element,[{opacity:0,transform:"translateX(68px)"},{opacity:1,transform:"none"}],{duration:520,easing:experienceEase});
    }
  }
  morphCount++;
}

transition = function(next,focus=true) {
  if (!["glance","expanded","observe"].includes(next) || next===view || (next!=="glance" && !task())) return;
  const previous=view;
  experienceLayout(()=>{
    if(next!=="observe") observationReading=false;
    view=next;interactionCount++;render();
  });
  const content=next==="glance" ? $("vessel-intro") : $("expanded-content");
  animate(content,[{opacity:.1,transform:`translateY(${next==="glance" ? -32 : 40}px)`},{opacity:1,transform:"none"}],{duration:480,easing:experienceEase});
  const indicator=document.querySelector(".switch-indicator"), index=["glance","expanded","observe"];
  animate(indicator,[{transform:`translateX(calc(${index.indexOf(previous)} * (100% + 3px)))`},{transform:`translateX(calc(${index.indexOf(next)} * (100% + 3px)))`}],{duration:460,easing:experienceEase});
  if(focus) $(next==="observe" ? "monitor-heading" : "task-title").focus({preventScroll:true});
};

selectTask = function(id) {
  if(id===selected || !tasks.some(t=>t.task_id===id)) return;
  const direction=tasks.findIndex(t=>t.task_id===id)>=tasks.findIndex(t=>t.task_id===selected) ? 1 : -1;
  incumbentExperience.selectTask(id);
  animate($("vessel"),[{opacity:.2,transform:`translateY(${direction*48}px)`},{opacity:1,transform:"none"}],{duration:500,easing:experienceEase});
  animate($("vessel-intro"),[{opacity:0,transform:`translateX(${direction*60}px)`},{opacity:1,transform:"none"}],{duration:540,easing:experienceEase});
  if(view==="observe") animate($("observation-scroll"),[{opacity:.1,transform:`translateY(${direction*36}px)`},{opacity:1,transform:"none"}],{duration:460,easing:experienceEase});
};

setObservationReading = function(expanded,focus=true) {
  if(view!=="observe" || expanded===observationReading) return;
  if(expanded) observationScroll=$("observation-scroll").scrollTop;
  experienceLayout(()=>{observationReading=expanded;render();});
  if(!expanded) $("observation-scroll").scrollTo(0,observationScroll);
  if(focus) $(expanded ? "observation-scroll" : "expand-observation").focus({preventScroll:true});
};

switchObservation = function(next) {
  if(next===observationView) return;
  const direction=next==="details" ? 1 : -1;
  observationView=next;render();$("observation-scroll").scrollTo(0,0);
  animate($(next==="details" ? "observation-detail-panel" : "observation-summary-panel"),
    [{opacity:0,transform:`translateX(${direction*44}px)`},{opacity:1,transform:"none"}],{duration:430,easing:experienceEase});
};

function experienceEvent(event,detailed) {
  const row=document.createElement("li"), symbol=document.createElement("span"), title=document.createElement("strong"), badge=document.createElement("small");
  row.className="experience-event";
  for(const name of ["task_id","sequence","kind","confirmation"]) row.dataset[name==="task_id" ? "taskId" : name]=String(event[name]);
  const confirmed=event.confirmation==="confirmed", failed=["failed","execution_failed"].includes(event.kind);
  row.dataset.tone=failed ? "failed" : confirmed ? "confirmed" : "reported";
  symbol.className="event-symbol";symbol.setAttribute("aria-hidden","true");
  symbol.textContent=failed ? "!" : confirmed ? "✓" : "◇";
  title.textContent=event.title;
  badge.textContent=failed ? (confirmed ? "失敗已確認 · Core" : "失敗回報 · 收尾未確認") :
    confirmed ? (event.kind==="working" ? "Core 已確認 · 當時開始執行" : "Core 已確認") : "階段回報 · 非工具完成證據";
  row.append(symbol,title,badge);
  if(detailed) {const detail=document.createElement("p");detail.textContent=event.detail;row.append(detail);}
  return row;
}

renderObservation = function(ownActive) {
  incumbentExperience.renderObservation(ownActive);
  const observation=!offline && ownActive && snapshot.observation?.task_id===selected ? snapshot.observation : null;
  const events=observation?.events || [];
  const key=JSON.stringify([selected,offline,events]);
  for(const [id,detailed] of [["event-list",false],["detail-events",true]]) {
    const list=$(id);
    if(list.dataset.experienceKey===key) continue;
    const previousCount=Number(list.dataset.experienceCount||0), previousId=list.dataset.experienceTask;
    list.replaceChildren(...events.map(event=>experienceEvent(event,detailed)));
    if(!events.length) {
      const empty=document.createElement("li");empty.className="experience-empty";
      empty.textContent=offline ? "狀態未知 · 連線未確認，沒有可確認的即時事件。" :
        !ownActive ? "這是已保存成果。歷程沒有持久保存，無法重播；請閱讀成果或啟動新的合成情境。" : "尚未收到可確認的事件。";
      list.append(empty);
    } else if(previousId===selected && previousCount<events.length) {
      [...list.children].slice(previousCount).forEach((row,i)=>animate(row,
        [{opacity:0,transform:"translateY(28px)"},{opacity:1,transform:"none"}],{duration:420,delay:Math.min(i*65,260),easing:experienceEase}));
    }
    list.dataset.experienceKey=key;list.dataset.experienceCount=String(events.length);list.dataset.experienceTask=selected;
  }
  const label=$("close-monitor").querySelector(".monitor-return-label");
  label.textContent=observationReading ? "返回" : "收合";
  for(const heading of document.querySelectorAll(".observation-scroll h4")) heading.firstChild.textContent="歷程事件 ";
  contentText("monitor-origin",offline ? "尚未確認 · 連線不可用" : ownActive ? "現在狀態 · 本機 Core 讀回" : "已保存成果 · 本機記錄讀回");
  // Only the narrow full-screen lens needs isolation. Desktop keeps the work
  // rail available; the Result Reader and modal dialogs retain their own layer.
  const isolated=observationReading && innerWidth<=560;
  for(const element of document.querySelectorAll(".app-header,.workspace-bar,.scenario-bar,.task-tray,.app-footer,.stage-caption")) element.inert=isolated;
};

render = function() {
  const before=experiencePresented;
  incumbentExperience.render();
  contentText("task-number","SYNTHETIC / READ ONLY");contentText("project-label","A SPACE FOR YOUR WORK");
  for(const button of $("task-items").children) button.dataset.state=offline ? "UNKNOWN" : tasks.find(t=>t.task_id===button.dataset.task)?.state || "UNKNOWN";
  const busy=offline || starting || !!snapshot?.busy;
  for(const button of document.querySelectorAll("[data-scenario]")) {
    button.disabled=busy;button.setAttribute("aria-pressed",String(button.dataset.scenario===experienceScenario));
  }
  if(snapshot?.busy && !offline) contentText("scenario-message","合成工作正在執行。可觀察事件、切換已保存成果，或要求停止；收尾後可再選情境。");
  else if(!offline) contentText("scenario-message","所有情境均為 synthetic。可再次選擇情境；成果需要你另外作出審查決定。");
  else contentText("scenario-message","連線未確認 · 暫停啟動情境，不推定工作已停止。");
  const state=task()?.state;
  if(before?.id===selected && !before.offline && !offline && before.state!==state) {
    animate($("vessel-header"),[{opacity:.15,transform:"translateY(-25px)"},{opacity:1,transform:"none"}],{duration:520,easing:experienceEase});
    animate(document.querySelector(".monitor-state"),[{opacity:0,transform:"translateY(30px)"},{opacity:1,transform:"none"}],{duration:560,easing:experienceEase});
    if(state==="RESULT_PENDING_REVIEW" && snapshot?.tasks.some(t=>t.task_id===selected)) toast("合成成果已到達 · 現在可以閱讀與審查。");
    if(state==="FAILED") toast("合成失敗已確認 · 沒有可審查成果。");
  }
  experiencePresented={id:selected,state,offline};
};

openReader = function() {
  incumbentExperience.openReader();
  if($("reader").open) animate($("reader"),[{opacity:0,transform:"translateY(50px) scale(.94)"},{opacity:1,transform:"none"}],{duration:520,easing:experienceEase});
};
toggleReaderFocus = function() {
  const before=$("reader").getBoundingClientRect();
  incumbentExperience.toggleReaderFocus();
  const after=$("reader").getBoundingClientRect();
  animate($("reader"),[{transformOrigin:"0 0",transform:`translate(${before.left-after.left}px,${before.top-after.top}px) scale(${before.width/after.width},${before.height/after.height})`},{transformOrigin:"0 0",transform:"none"}],{duration:540,easing:experienceEase});
};

const monitorReturn=document.createElement("span");monitorReturn.className="monitor-return-label";$("close-monitor").append(monitorReturn);
document.querySelector(".workspace-name h1").firstChild.textContent="流動工作台";
document.querySelector(".brand-caption").textContent="LIVING WORKSPACE";
const modeNames={glance:"概覽",expanded:"工作",observe:"觀察"};
for(const button of document.querySelectorAll(".view-switch button")) button.firstChild.textContent=modeNames[button.dataset.view]+" ";
document.querySelector(".tray-label p").textContent="每份成果都有自己的身分。";
const scenarioIntents={running:"合成情境｜執行觀察 · 公開文件概覽",reading:"合成情境｜長篇成果 · 24 段閱讀筆記",failed:"合成情境｜失敗 · 未取得可確認成果"};
for(const button of document.querySelectorAll("[data-scenario]")) button.onclick=()=>{
  if(offline || starting || snapshot?.busy || snapshot?.runtime!=="synthetic-no-ai") return;
  experienceScenario=button.dataset.scenario;
  $("new-intent").value=scenarioIntents[experienceScenario];
  $("new-form").requestSubmit();
};
const experienceSubmit=$("new-form").onsubmit;
$("new-form").onsubmit=async event=>{
  const previous=selected;
  await experienceSubmit(event);
  if(!offline && selected!==previous && snapshot?.active?.task_id===selected) transition("observe");
};
document.addEventListener("keydown",event=>{
  if(event.key!=="Tab" || !observationReading || innerWidth>560 || document.querySelector("dialog[open]")) return;
  const focusable=[...$("monitor").querySelectorAll("button:not(:disabled),[tabindex='0']")].filter(e=>e.getClientRects().length);
  const first=focusable[0], last=focusable.at(-1);
  if(event.shiftKey && document.activeElement===first) {event.preventDefault();last.focus();}
  else if(!event.shiftKey && document.activeElement===last) {event.preventDefault();first.focus();}
});
window.addEventListener("resize",()=>render());
render();
