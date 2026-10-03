"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const renderer = new SanctuaryWorld($("living-world"), (zone,kind) => selectZone(zone,kind,true));
  let envelope=null, receivedAt=0, activityDeadline=0, inFlight=false, disposed=false;
  let presentation=null, connectionFailure=null, selectedZone=null, selectedEvent=null, timelineKey="";
  let lastDelivery=null, suspended=document.hidden, continuityNote="", completedIdentity=null;
  const poseLabels={idle:"基地待命",arriving:"請求已偵測",working:"已觀察到活動",settled:"執行已停下",review:"候選／結果待審",attention:"技術待辦",accepted:"最終接受證據已確認",blocked:"工作已阻擋",uncertain:"目前無法確認"};
  const zoneNames={core:"Command Core",library:"Library",research:"Research Wing",workshop:"Workshop",test:"Test Bench",review:"Review Bay"};
  const owners={UNKNOWN:"接手方未確認",SYSTEM:"系統處理",TECHNICAL_ACTION:"技術處理",CHATGPT_REVIEW:"最終技術審查",NONE:"無待辦交接"};
  const tests=new Set(["pytest","pytest.exe","vitest","jest","ctest"]);
  function testFramework(e){
    if(e.source!=="codex_exec_jsonl"||!/^codex\.command\.(started|updated|completed|failed)$/.test(e.kind))return null;
    const p=e.payload||{};
    if(Object.hasOwn(p,"activity_kind"))return p.activity_kind==="test"&&["pytest","vitest","jest","ctest"].includes(p.test_framework)?p.test_framework:null;
    const name=String(p.command_name).toLowerCase();return tests.has(name)?name.replace(/\.exe$/,""):null;
  }
  function testEvidence(e){
    const framework=testFramework(e);if(!framework)return null;
    const finished=["codex.command.completed","codex.command.failed"].includes(e.kind);
    const code=Number.isInteger(e.payload?.exit_code)?" · exit "+e.payload.exit_code:" · exit 未提供";
    return framework+" · "+(finished?"已結束"+code:"曾觀察到啟動／更新；完成狀態未提供");
  }
  const safe=value=>typeof value==="string"||typeof value==="number"?String(value):"尚未提供";
  function put(id,value){$(id).textContent=value===0?"0":value||"尚未提供";}
  function facts(id,entries){const nodes=[];for(const [key,value] of entries){const dt=document.createElement("dt"),dd=document.createElement("dd");dt.textContent=key;dd.textContent=safe(value);nodes.push(dt,dd);}$(id).replaceChildren(...nodes);}
  function currentEvents(){if(!envelope)return[];const s=envelope.snapshot;return envelope.events.filter(e=>e.request_id===s.current_task.request_id&&e.run_id===s.observability.run_id).sort((a,b)=>a.sequence-b.sequence);}
  function eventContext(e){
    const p=e.payload||{},kind=e.kind;
    let label=kind,zone=null;
    if(kind.startsWith("codex.command.")){const framework=testFramework(e);label=framework?"測試指令 · "+testEvidence(e):"指令 · "+safe(p.command_name);zone=framework?"test":"workshop";}
    else if(kind.startsWith("codex.file.")){label="檔案活動 · "+(Array.isArray(p.paths)?p.paths.join("、"):"路徑未提供");zone="workshop";}
    else if(kind.startsWith("codex.tool.")){label="工具活動 · "+safe(p.tool_kind);zone="workshop";}
    else if(kind==="execution.started"){label="已觀察到執行開始";zone="workshop";}
    else if(kind==="process.completed"){label="執行程序已結束";zone="core";}
    else if(kind.startsWith("codex.turn.")){label="Codex 回合 · "+kind.split(".").at(-1);zone="workshop";}
    return{label,zone};
  }
  function taskLabel(s){const task=s.current_task;return(task.issue_number?"Issue #"+task.issue_number:"目前任務")+" · "+(task.action||"操作未提供");}
  function showEvent(sequence,locate=false){
    const e=currentEvents().find(e=>e.sequence===sequence);if(!e){selectedEvent=null;$("event-detail").replaceChildren();return;}
    selectedEvent=sequence;const context=eventContext(e),p=e.payload||{};
    const title=document.createElement("h4"),detail=document.createElement("dl"),button=document.createElement("button");
    title.textContent="#"+e.sequence+" · "+context.label;detail.id="selected-event-facts";
    $("event-detail").replaceChildren(title,detail);
    facts(detail.id,[["觀察時間",e.observed_at_utc],["事件",e.kind],["來源",e.source],["request",e.request_id],["run",e.run_id],["狀態",p.status],["測試活動",testEvidence(e)||"未辨識測試語意"],["exit code",p.exit_code],["證據界線","指令結束或 exit code 不等於完整測試通過或最終接受。"]]);
    if(context.zone){button.textContent="定位 "+zoneNames[context.zone];button.addEventListener("click",()=>{selectZone(context.zone,"event",false);$("expert-dialog").close();document.querySelector(`[data-zone="${context.zone}"]`).focus();});$("event-detail").append(button);}
    if(locate&&context.zone)selectZone(context.zone,"event",false);
    document.querySelectorAll("[data-event]").forEach(b=>b.setAttribute("aria-pressed",String(Number(b.dataset.event)===sequence)));
  }
  function showExpert(){
    put("expert-freshness",connectionFailure?"來源不可用："+connectionFailure+"。以下是最後讀取的證據，並非目前活動。":"最近讀取："+(envelope?.snapshot.observed_at_utc||"尚未取得")+(continuityNote?" · "+continuityNote:""));
    if(!envelope)return;
    const {snapshot:s,world:w}=envelope,task=s.current_task,review=s.review,h=presentation.human;
    put("expert-task",taskLabel(s));put("expert-purpose","任務標題／目的：目前來源未提供。以下保留可核對的 Issue、action 與 request 身分。");
    facts("expert-facts",[["目前狀態",presentation.title],["接手方",h.owner],["下一步類別",owners[h.kind]||"尚無法確認"],["停住／等待原因",h.why],["來源建議",s.system.next_action],["request",task.request_id],["run",s.observability.run_id],["Lifecycle",task.lifecycle.stage],["判定依據",task.lifecycle.basis]]);
    const verdict=review.final_verdict||{},evidence=review.evidence||{};
    const latestTest=currentEvents().filter(e=>testFramework(e)).at(-1);
    // Durable history is independent of the current pose and never extends motion.
    const testHistory=latestTest?testEvidence(latestTest):"目前保留的事件中沒有可辨識測試；不代表未執行";
    const testNav=document.querySelector('[data-zone="test"]');
    testNav.textContent=latestTest?"Test Bench · 測試紀錄":"Test Bench";
    testNav.title=testHistory;
    facts("review-facts",[["成果證據",evidence.status==="available"?evidence.summary:"尚無可核對的成果證據"],["證據位置",evidence.pointer],["最終審查",verdict.status==="available"?verdict.verdict:"尚未取得最終審查"],["審查者",verdict.reviewer],["審查證據",verdict.evidence_pointer],["Candidate 身分",s.source_status.review_candidate],["Changed files 彙總",review.changed_files?.status==="available"?JSON.stringify(review.changed_files.items):"unavailable · 檔案事件不等於已核對的變更清單"],["Test summary",review.test_summary?.status==="available"?review.test_summary.summary:"unavailable · 測試指令事件不等於測試報告"],["人類決策提案","unavailable · 目前 canonical source 未提供可信提案與操作範圍"]]);
    const testTerm=document.createElement("dt"),testValue=document.createElement("dd");
    testTerm.textContent="已觀察測試活動";testValue.textContent=testHistory;
    $("review-facts").append(testTerm,testValue);
    $("locate-artifact").disabled=!presentation.artifact;
    const events=currentEvents(),key=JSON.stringify([s.current_task.request_id,s.observability.run_id,events]);
    if(key!==timelineKey){
      const focusedEvent=document.activeElement?.dataset.event,focusedDetail=$("event-detail").contains(document.activeElement);
      timelineKey=key;const list=[];
      for(const e of events){const li=document.createElement("li"),button=document.createElement("button"),context=eventContext(e);button.type="button";button.dataset.event=String(e.sequence);button.textContent="#"+e.sequence+" · "+context.label+" · "+safe(e.payload?.status||e.kind.split(".").at(-1));button.setAttribute("aria-pressed",String(e.sequence===selectedEvent));button.addEventListener("click",()=>showEvent(e.sequence,true));li.append(button);list.push(li);}
      $("activity-timeline").replaceChildren(...list);
      if(selectedEvent!==null)showEvent(selectedEvent);
      if(focusedEvent)document.querySelector(`[data-event="${Number(focusedEvent)}"]`)?.focus({preventScroll:true});
      else if(focusedDetail)$("event-detail").focus({preventScroll:true});
    }
    put("timeline-empty",events.length?"顯示此 run 最近 "+events.length+" 筆已驗證事件。":"目前沒有可核對的此 run 事件；不由其他任務補入。");
    put("diagnostic-summary",[...s.diagnostics,...(presentation.reasons||[])].join(" · ")||"目前未回報來源診斷。");
    put("expert-request","request: "+(task.request_id||"UNKNOWN"));put("expert-run","run: "+(s.observability.run_id||"UNKNOWN"));put("expert-stage","lifecycle: "+task.lifecycle.stage);
    put("expert-snapshot",JSON.stringify(s,null,2));put("expert-events",JSON.stringify(events,null,2));put("expert-projection",JSON.stringify({source_projection:w,displayed_projection:presentation,connection_failure:connectionFailure},null,2));
  }
  function renderContext(w){
    document.body.dataset.pose=w.pose;
    put("task-label",envelope?taskLabel(envelope.snapshot):"等待任務來源");
    put("world-title",w.title);put("world-description",w.description);put("context-title",w.title);put("result-badge",poseLabels[w.pose]);
    put("context-summary",w.description);put("what",w.description);put("why",envelope?.snapshot.review.warning_or_error?.code||w.human.why);
    $("artifact-preview").dataset.kind=w.artifact||"none";
    put("next-owner",w.human.owner);put("human-what",w.human.what);put("human-why",w.human.why);put("human-operation",w.human.operation);put("human-scope",w.human.scope);
    $("human-context").dataset.attention=String(w.human.attention);$("human-callout").hidden=!w.human.attention;
    const pointer=w.human.evidence,s=envelope?.snapshot,repo=s?.operator?.state?.repository,issue=s?.current_task?.issue_number;
    const comment=typeof pointer==="string"?/^issue_comment:([1-9][0-9]{0,18})$/.exec(pointer):null,link=$("evidence-link");
    link.hidden=true;link.removeAttribute("href");$("evidence-missing").hidden=false;
    if(comment&&typeof repo==="string"&&/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repo)&&Number.isSafeInteger(issue)&&issue>0){link.href=`https://github.com/${repo}/issues/${issue}#issuecomment-${comment[1]}`;link.hidden=false;$("evidence-missing").hidden=true;}
    document.querySelectorAll("[data-zone]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.zone===(selectedZone||w.station))));
  }
  function stopPresentation(reason,health="offline"){
    connectionFailure=reason;
    const w={protocol:"lawb.sanctuary_projection.v1",identity:envelope?.world.identity||{},pose:"uncertain",station:"core",artifact:null,actor:null,semantic_motion:false,activity:null,health,
      title:health==="stale"?"訊號已過期，動態已停止":"目前連不上 Workflow",description:"無法確認目前工作；保留最後讀取的證據供查閱。",reasons:[reason],
      human:{kind:"UNKNOWN",owner:"尚無法確認",attention:false,what:"目前無法確認下一步接手方。",why:"請核對既有 Workflow 連線與證據。",operation:"尚無可信的人類決策提案。",scope:"目前證據不可用。",evidence:null,write_enabled:false}};
    presentation=w;renderer.update(w);renderContext(w);put("connection",health==="stale"?"來源過期 · 動態停止":"本機來源不可用");$("connection").dataset.health=health;showExpert();
  }
  function validEnvelope(v){return Boolean(v&&v.snapshot?.protocol==="lawb.workflow_panel.v1"&&v.snapshot.mode==="read_only"&&v.snapshot.bind==="loopback"&&v.snapshot.current_task?.lifecycle&&v.snapshot.observability&&v.world?.protocol==="lawb.sanctuary_projection.v1"&&v.world.human?.write_enabled===false&&Array.isArray(v.events)&&typeof v.delivery?.session==="string"&&v.delivery.session.length>0&&Number.isSafeInteger(v.delivery.sequence)&&v.delivery.sequence>0);}
  async function refresh(){
    if(inFlight||disposed||suspended)return;
    inFlight=true;$("refresh").disabled=true;
    const abort=new AbortController(),timeout=setTimeout(()=>abort.abort(),4000);
    try{
      const response=await fetch("/api/sanctuary",{cache:"no-store",signal:abort.signal});if(!response.ok)throw Error("snapshot_unavailable");
      const next=await response.json();if(suspended)return;if(!validEnvelope(next))throw Error("snapshot_contract_invalid");
      const observed=Date.parse(next.snapshot.observed_at_utc);
      // Wall-clock age checks freshness; server session/sequence orders deliveries.
      // A clock correction may move observed_at backwards without blocking forever.
      if(!Number.isFinite(observed)||Date.now()-observed>10000||observed-Date.now()>2000)throw Error("snapshot_stale_or_invalid");
      if(lastDelivery?.session===next.delivery.session&&next.delivery.sequence<=lastDelivery.sequence)throw Error("delivery_replayed_or_reordered");
      const s=next.snapshot,w=next.world;
      if(w.identity.request_id!==s.current_task.request_id||w.identity.run_id!==s.observability.run_id||w.source_lifecycle!==s.current_task.lifecycle.stage)throw Error("projection_identity_mismatch");
      // A remembered runner completion fences contradictory replay after truncation.
      // This is disposable observation memory, not a lifecycle or recovery decision.
      const incomingIdentity=JSON.stringify(w.identity);
      if(s.observability.run_completed===true)completedIdentity=incomingIdentity;
      if(w.semantic_motion&&incomingIdentity===completedIdentity)throw Error("completed_run_activity_conflict");
      const previous=envelope?.world,sameRequest=previous?.identity.request_id&&previous.identity.request_id===w.identity.request_id;
      const identityChanged=JSON.stringify(previous?.identity)!==JSON.stringify(w.identity);
      const sourceReset=envelope&&(envelope.snapshot.observability.latest_sequence||0)>0&&(s.observability.source_id!==envelope.snapshot.observability.source_id||(s.observability.latest_sequence||0)<(envelope.snapshot.observability.latest_sequence||0));
      const restarted=lastDelivery&&lastDelivery.session!==next.delivery.session;
      const continuous=sameRequest&&((previous.pose==="arriving"&&!previous.identity.run_id&&w.pose==="working")||(!w.identity.run_id&&["settled","review","attention","accepted","blocked"].includes(w.pose)));
      if((identityChanged&&!continuous)||connectionFailure||sourceReset||restarted)renderer.clearTransition();
      if(identityChanged||sourceReset){selectedZone=null;selectedEvent=null;renderer.focus(null);put("selection-context","來源或任務已更新，請重新選取證據。");$("event-detail").replaceChildren();}
      continuityNote=restarted?"觀察服務已重新連線；未觸發工作":sourceReset?"事件來源已重置；未重播歷史旅程":"";
      envelope=next;lastDelivery=next.delivery;receivedAt=performance.now();
      activityDeadline=receivedAt+Math.max(0,Date.parse(w.activity_until_utc)-observed);
      presentation=w;connectionFailure=null;renderer.update(w);renderContext(w);showExpert();
      const health=s.system.operator;put("connection",health==="online"?"本機來源連線中 · 唯讀":health==="stale"?"Operator 訊號過期":"Operator 不可用 · 唯讀");$("connection").dataset.health=health;
    }catch(error){stopPresentation(error.message);}
    finally{clearTimeout(timeout);inFlight=false;$("refresh").disabled=false;}
  }
  function openInspector(){showExpert();if(!$("expert-dialog").open)$("expert-dialog").show();}
  function selectZone(zone,kind="station",open=false){
    if(!presentation||!zoneNames[zone])return;
    selectedZone=zone;renderer.focus(zone);
    put("selection-context","已定位 "+zoneNames[zone]+(kind==="actor"?" 的 Builder":kind==="artifact"?" 的成果":"")+"；選取只用於查閱，不代表此區正在執行。");
    document.querySelectorAll("[data-zone]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.zone===zone)));
    if(open){openInspector();const matching=currentEvents().filter(e=>eventContext(e).zone===zone);if(matching.length)showEvent(matching.at(-1).sequence);else{selectedEvent=null;$("event-detail").textContent=zone==="review"?"目前成果與審查證據見下方。":"此區沒有可核對的目前 run 活動。";}}
  }
  $("expert-open").addEventListener("click",openInspector);
  $("expert-close").addEventListener("click",()=>{$("expert-dialog").close();$("expert-open").focus();});
  document.addEventListener("keydown",e=>{if(e.key==="Escape"&&$("expert-dialog").open){$("expert-dialog").close();$("expert-open").focus();}});
  $("refresh").addEventListener("click",refresh);
  $("human-details").addEventListener("click",openInspector);
  $("locate-artifact").addEventListener("click",()=>{selectZone(presentation.station,"artifact");$("expert-dialog").close();document.querySelector(`[data-zone="${presentation.station}"]`).focus();});
  document.querySelectorAll("[data-zone]").forEach(b=>b.addEventListener("click",()=>selectZone(b.dataset.zone,"station",true)));
  document.addEventListener("visibilitychange",()=>{suspended=document.hidden;stopPresentation(suspended?"page_suspended":"page_resuming","stale");if(!suspended){renderer.clearTransition();refresh();}});
  window.addEventListener("pageshow",e=>{if(e.persisted){renderer.clearTransition();stopPresentation("page_restored","stale");refresh();}});
  const poll=setInterval(refresh,1500);
  const freshness=setInterval(()=>{if(!envelope||suspended)return;if(performance.now()-receivedAt>6000)stopPresentation("connection_stale","stale");else if(envelope.world.semantic_motion&&performance.now()>activityDeadline)stopPresentation("activity_expired","stale");},250);
  window.addEventListener("beforeunload",()=>{disposed=true;clearInterval(poll);clearInterval(freshness);renderer.destroy();});
  window.sanctuaryInspection=()=>({source:envelope?.snapshot||null,projection:envelope?.world||null,presentation,connectionFailure,delivery:lastDelivery,selectedEvent,selectedZone,rendered:renderer.inspect(),receivedAgeMs:performance.now()-receivedAt});
  refresh();
})();
