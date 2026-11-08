/* Navigation and read-only projections of the existing Companion surface. */
(() => {
  if(document.body.dataset.workEnabled!=='true')return;
  const el=id=>document.getElementById(id),body=document.body;
  const titles={overview:'總覽',project:'專案情境',chat:'對話',work:'工作',execute:'執行',monitor:'監控',documents:'文件',links:'連結',navigator:'星系導覽'};
  const names=window.CompanionReading.states;
  const concepts={
    monitor:['讓狀態清楚可見。','系統健康、資源與長期監控尚未接通。單一工作的已回報事件，仍可從「工作 → 觀察」閱讀。','沒有背景監控、資源用量數字或推定的健康狀態。'],
    navigator:['讓專案找到自己的位置。','星球、衛星與航線的空間索引概念。尚未接入專案關係資料。','下方軌道只是設計語言，沒有真實節點、活動量或依賴關係。']
  };
  let route='',syncing=false,signature='',current={tasks:[],offline:true},restoring=false,navigation=0,scrollRestore=0,peekId='';
  let projectData=null,projectEpoch=0,projectLoading=false,projectStamp='';
  const text=(tag,value)=>{const n=document.createElement(tag);n.textContent=value;return n;};
  body.dataset.nexus='true';
  el('chat-question').setAttribute('aria-describedby','nexus-draft-note');
  const draftNote=text('small','支援的日用入口會將草稿與偏好加密保存於本機，依帳戶與工作區隔離；請以輸入框的保存狀態為準。資料分享仍須重新選取與預覽。');
  draftNote.id='nexus-draft-note';draftNote.className='nexus-footnote';el('help-dialog').append(draftNote);
  el('help-dialog').querySelector('.help-steps li p').textContent='從總覽、工作或執行入口選取工作；在工作中閱讀成果、展開觀察，或詢問 Companion。';
  for(const id of ['companion-task-state','nexus-peek-state'])el(id).classList.add('work-status');
  el('nexus-sidebar').hidden=el('nexus-topbar').hidden=false;
  // Keep the existing controls and their handlers; there is only one chat/work controller.
  for(const [id,destination] of [['open-chat','chat'],['open-workspace','work']]) {
    const old=el('nexus-navigation').querySelector('[data-route="'+destination+'"]'),button=el(id);
    button.replaceChildren(...old.childNodes);button.dataset.route=destination;old.replaceWith(button);
  }
  el('space-nav').hidden=true;
  el('nexus-topbar').append(el('help'),el('preferences'));
  const sidebarKey='nexus-layout-sidebar-mode-v2';
  let sidebarPreference=null;
  try {const saved=localStorage.getItem(sidebarKey);if(['expanded','collapsed'].includes(saved))sidebarPreference=saved;}catch{}
  for(const button of el('nexus-navigation').querySelectorAll('button')) {
    const label=text('span',titles[button.dataset.route]);label.className='nexus-nav-label';
    for(const node of [...button.childNodes])if(node.nodeType===Node.TEXT_NODE)node.remove();
    button.querySelector('span').after(label);
    const name=titles[button.dataset.route]+(concepts[button.dataset.route]?' · 未連接／概念':'');
    button.setAttribute('aria-label',name);button.title=name;
  }
  const pin=el('nexus-project').closest('button');pin.title='目前工作區 · 專案情境';pin.setAttribute('aria-label',pin.title);
  function setSidebar(mode,remember=false) {
    body.dataset.sidebar=mode;
    const expanded=mode==='expanded',overlay=expanded&&innerWidth<=780;
    body.dataset.menu=String(overlay);el('nexus-scrim').hidden=!overlay;
    el('nexus-sidebar').inert=false;
    for(const id of ['nexus-sidebar-toggle','nexus-menu']) {
      const button=el(id);button.setAttribute('aria-expanded',String(expanded));
      button.title=expanded?'收合左側導覽':'展開左側導覽';button.setAttribute('aria-label',button.title);
    }
    if(remember){sidebarPreference=mode;try{localStorage.setItem(sidebarKey,mode);}catch{}window.dispatchEvent(new Event('companion-preferences-change'));}
    window.dispatchEvent(new Event('nexus-layout'));
  }
  const defaultSidebar=()=>innerWidth<=1050?'collapsed':'expanded';
  window.companionSidebarPreference=()=>sidebarPreference;
  window.companionRestoreSidebar=mode=>{
    if(mode!==null&&!['expanded','collapsed'].includes(mode))return;
    sidebarPreference=mode;
    try{if(mode===null)localStorage.removeItem(sidebarKey);else localStorage.setItem(sidebarKey,mode);}catch{}
    setSidebar(innerWidth<=780?'collapsed':mode||defaultSidebar());
  };
  setSidebar(innerWidth<=780?'collapsed':sidebarPreference||defaultSidebar());
  window.dispatchEvent(new Event('companion-preferences-ready'));
  function menu(open) {
    if(innerWidth<=780)setSidebar(open?'expanded':'collapsed');
  }
  function go(next,fromCompanion=false,replace=false,taskId='') {
    if(!titles[next])next='overview';
    if(syncing)return;syncing=true;++navigation;++projectEpoch;scrollRestore=0;
    window.closeCompanionFloating?.(false);
    if(route!==next||taskId)window.companionClearSourceConsent?.();
    window.companionSaveChat?.();
    if(next!=='work')window.cancelCompanionWorkNavigation?.();
    route=next;body.dataset.route=next;body.dataset.workDetail=String(next==='work'&&!!taskId);menu(false);
    if(!fromCompanion&&(next==='chat'||next==='work'))window.companionNavigate(next,false);
    else if(next!=='chat'&&next!=='work')body.dataset.space=next;
    for(const [id,visible] of [['chat-space',next==='chat'],['work-space',next==='work'],['nexus-overview',next==='overview'],['nexus-project-page',next==='project'],['nexus-execute',next==='execute'],['nexus-documents',next==='documents'],['nexus-links',next==='links'],['nexus-concept',!!concepts[next]]])el(id).hidden=!visible;
    if(next==='project')pin.setAttribute('aria-current','page');else pin.removeAttribute('aria-current');
    el('nexus-location').textContent=titles[next];document.title=titles[next]+' · NEXUS';
    for(const b of el('nexus-navigation').querySelectorAll('button')) {
      if(b.dataset.route===next)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');
    }
    if(concepts[next]) {
      const [heading,description,boundary]=concepts[next];
      el('nexus-concept-title').textContent=heading;el('nexus-concept-description').textContent=description;el('nexus-concept-boundary').textContent=boundary;
      el('nexus-concept-art').textContent=next==='navigator'?'◎':{monitor:'⌁',documents:'▤',links:'↗'}[next];
    }
    const target=next==='chat'?'chat-title':next==='work'?'task-title':next==='project'?'project-title':next==='overview'?'nexus-home-title':next==='execute'?'nexus-execute-title':next==='documents'?'documents-title':next==='links'?'links-title':'nexus-concept-title';
    el('skip-main').href='#'+target;el('skip-main').textContent='跳至'+titles[next];
    const chatId=next==='chat'?window.companionChatSelection?.():'';
    const hash='#'+next+(taskId?'?task='+encodeURIComponent(taskId):chatId?'?chat='+encodeURIComponent(chatId):'');
    if(!restoring&&location.hash!==hash)history[replace?'replaceState':'pushState'](null,'',hash);
    if(!fromCompanion)el(target).focus({preventScroll:true});
    syncing=false;
    if(next==='project'){projectStamp='';clearProject('正在確認目前專案…');void loadProject();}
    resourceNavigation(next);
  }
  for(const b of document.querySelectorAll('[data-route]'))b.addEventListener('click',()=>go(b.dataset.route));
  window.addEventListener('companion-space',e=>go(e.detail,true));
  async function restoreRoute() {
    const [next,query]=location.hash.slice(1).split('?'),params=new URLSearchParams(query);
    const top=history.state?.workY||0;
    restoring=true;go(next||'overview',false,true,params.get('task')||'');
    restoring=false;const mine=navigation;scrollRestore=mine;
    if(next==='work'&&params.get('task'))await window.openCompanionWork(params.get('task'));
    if(next==='chat')window.openCompanionChat?.(params.get('chat')||'');
    requestAnimationFrame(()=>{if(mine!==navigation)return;scrollTo(0,next==='work'?top:0);scrollRestore=0;});
  }
  history.scrollRestoration='manual';
  window.addEventListener('scroll',()=>{if(!scrollRestore&&route==='work'&&body.dataset.workDetail==='true')history.replaceState({...history.state,workY:scrollY},'');},{passive:true});
  window.addEventListener('popstate',restoreRoute);
  window.addEventListener('companion-chat-selected',e=>{
    if(route!=='chat'||restoring)return;
    const hash='#chat'+(e.detail.id?'?chat='+encodeURIComponent(e.detail.id):'');
    if(location.hash!==hash)history[e.detail.replace?'replaceState':'pushState'](null,'',hash);
  });
  const toggleSidebar=()=>setSidebar(body.dataset.sidebar==='expanded'?'collapsed':'expanded',innerWidth>780);
  el('nexus-sidebar-toggle').onclick=el('nexus-menu').onclick=toggleSidebar;
  el('nexus-scrim').onclick=()=>{menu(false);el('nexus-sidebar-toggle').focus();};
  window.addEventListener('resize',()=>setSidebar(innerWidth<=780?'collapsed':sidebarPreference||defaultSidebar()));
  document.addEventListener('keydown',e=>{
    if(body.dataset.menu!=='true')return;
    if(e.key==='Escape'){e.preventDefault();menu(false);el('nexus-sidebar-toggle').focus();}
    if(e.key==='Tab'){
      const nodes=[...el('nexus-sidebar').querySelectorAll('button')].filter(n=>n.getClientRects().length);
      const first=nodes[0],last=nodes.at(-1);
      if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}
      else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
    }
  });
  el('nexus-focus').onclick=()=>{
    const focus=body.dataset.focus!=='true';body.dataset.focus=String(focus);
    el('nexus-focus').setAttribute('aria-pressed',String(focus));el('nexus-focus').textContent=focus?'顯示導覽':'專注模式';
    window.dispatchEvent(new Event('nexus-layout'));
  };
  async function openWork(id) {
    go('work',false,false,id);scrollTo(0,0);try{await window.openCompanionWork(id);}catch{el('nexus-execution-notice').textContent='工作目前無法讀取；狀態未確認。';}
  }
  window.nexusOpenWork=openWork;
  function projectSignature() {return JSON.stringify([current.tasks,current.selected,current.offline,window.companionProjectStatus?.().account]);}
  function clearProject(message) {
    projectData=null;el('nexus-project-page').dataset.project='';el('project-title').textContent='目前專案';
    el('project-notice').textContent=message;el('project-workspace').textContent='尚未確認';el('project-viewing').textContent='目前專案尚未確認';
    el('project-current-name').textContent='未確認';el('project-availability').textContent='工作狀態未確認';
    for(const id of ['project-tasks','project-chats'])el(id).replaceChildren(text('p',message));
    projectContextStatus();
  }
  function projectContextStatus() {
    const s=window.companionProjectStatus?.();
    el('project-current-chat').textContent=!projectData?'關聯尚未確認':!s?.chat?'未選取已保存對話':s.status!=='ready'?'關聯尚未確認':s.association?'已關聯：'+s.association.project.name:'未關聯專案';
    el('project-current-sources').textContent=s?.sources?s.sources+' 項 · '+(s.preview?'已預覽，傳送時才分享':'尚待預覽'):'0 項 · 本次未選取';
  }
  async function loadProject() {
    if(route!=='project'||projectLoading)return;
    projectLoading=true;const mine=++projectEpoch,stamp=projectSignature();
    try {
      const data=await window.companionProjectContext();
      if(route!=='project'||mine!==projectEpoch)return;
      if(data.account!==window.companionProjectStatus().account||data.project.id!==data.work.workspace||!Array.isArray(data.chats)||!Array.isArray(data.work.tasks))throw Error('專案身分無法確認。');
      const tasks=[...data.work.tasks];if(data.work.active&&!tasks.some(t=>t.task_id===data.work.active.task_id))tasks.unshift(data.work.active);
      if(!tasks.every(t=>typeof t.task_id==='string'&&typeof t.intent==='string'&&Object.hasOwn(names,t.state)))throw Error('工作狀態無法確認。');
      projectData=data;projectStamp=stamp;el('nexus-project-page').dataset.project=data.project.id;
      el('project-title').textContent=el('project-current-name').textContent=data.project.name;
      el('project-viewing').textContent='目前查看：'+data.project.name;el('project-workspace').textContent=data.project.workspace;
      el('project-notice').textContent='';el('project-availability').textContent=data.work.runtime==='bounded-python-source-audit-v1'?'有限唯讀工作已接通':'執行端：'+(data.work.runtime||'未確認');
      rows(el('project-tasks'),tasks,false);
      const chats=el('project-chats');chats.replaceChildren();
      for(const c of data.chats){
        const button=text('button',c.title);button.className='project-chat-row';button.dataset.chat=c.id;
        button.onclick=async()=>{try{await window.openProjectConversation(c.id);}catch(e){el('project-notice').textContent=e.message;}};
        chats.append(button);
      }
      if(!data.chats.length)chats.append(text('p','尚無明確關聯的對話。既有對話仍可正常使用，可到對話中自行確認關聯。'));
      projectContextStatus();
    }catch(e){if(route==='project'&&mine===projectEpoch){projectStamp=stamp;clearProject(e.message||'專案資料目前不可用。');}}
    finally{projectLoading=false;}
  }
  function updateChatEntry(){
    const chatAction=el('nexus-overview').querySelector('.nexus-home-actions [data-route="chat"]');
    const resume=window.companionResumeStatus?.(),card=el('nexus-resume');
    card.hidden=!resume;
    el('nexus-resume-title').textContent=resume?.title||'';
    el('nexus-resume-copy').textContent=!resume?'':resume.error?'本機保存尚未確認。開啟對話後，可重試保存或核對已保存版本。':
      resume.hasDraft?(resume.saved?'有未送出的草稿，已加密保存於本機。':resume.saving?'草稿正在加密保存，請稍候再關閉。':'有未送出的草稿，目前尚未確認跨次開啟可接續。'):
      '開啟後可繼續閱讀或提問。';
    card.dataset.state=resume?.error?'error':resume?.saving?'saving':'ready';
    chatAction.textContent=resume?.error?'核對接續內容 →':resume?.hasDraft?'繼續草稿 →':resume?'繼續對話 ↗':'開始對話 ↗';
  }
  window.addEventListener('companion-continuity',updateChatEntry);
  window.addEventListener('companion-project',()=>{
    updateChatEntry();
    projectContextStatus();
    if(route==='project'){
      if(projectData?.account!==window.companionProjectStatus().account){++projectEpoch;projectStamp='';clearProject('正在確認目前帳戶的專案…');}
      if(projectStamp!==projectSignature())void loadProject();
    }
  });
  function renderPeek() {
    if(current.offline)peekId='';
    else if(!current.tasks.some(t=>t.task_id===peekId))peekId=current.tasks.find(t=>t.task_id===current.selected)?.task_id||current.tasks[0]?.task_id||'';
    const task=current.tasks.find(t=>t.task_id===peekId);
    el('nexus-work-peek').dataset.task=task?.task_id||'';
    el('nexus-peek-title').textContent=task?.intent||(current.offline?'連線未確認':'尚無可見工作');
    el('nexus-peek-state').textContent=task?(names[task.state]||names.UNKNOWN):'';
    el('nexus-peek-state').dataset.state=task?.state||'UNKNOWN';
    const facts={UNKNOWN:'尚無足夠執行資訊，不能確認工作是否完成。',CREATED:'工作已建立，正在等待執行端回報。',RUNNING:'執行端已回報工作進行中；沒有可確認的完成比例。',CANCEL_REQUESTED:'已提出停止要求，仍在等待取消確認。',CANCELLED:'執行端已確認取消。',FAILED:'執行端已回報失敗；沒有可當作成功的成果。',RESULT_PENDING_REVIEW:'可信成果已保存，等待你閱讀與審查。',ACCEPTED:'人類接受成果的審查決定已保存；不等於整套功能通過驗證。',REJECTED:'人類拒絕成果的決定已保存；原始成果仍保留。',REVISION_REQUESTED:'調整方向已記錄；不會自動執行新工作。'};
    el('nexus-peek-confirmed').textContent=current.offline?'目前無法確認工作狀態，不顯示上次連線的摘要。':task?facts[task.state]||facts.UNKNOWN:'目前沒有可顯示的工作。從對話形成提案，預覽並確認範圍後才會執行。';
    el('nexus-peek-open').disabled=!task||current.offline;
    for(const row of el('nexus-recent').querySelectorAll('[data-task]'))row.setAttribute('aria-pressed',String(row.dataset.task===peekId));
  }
  el('nexus-peek-open').onclick=()=>{if(!current.offline&&current.tasks.some(t=>t.task_id===peekId))openWork(peekId);};
  el('nexus-recent-shortcut').onclick=()=>{el('nexus-recent-section').scrollIntoView({block:'start'});el('nexus-peek-open').focus({preventScroll:true});};
  function rows(parent,items,offline) {
    parent.replaceChildren();
    if(offline){parent.append(text('p','連線未確認，無法確認目前工作的狀態。'));return;}
    if(!items.length){parent.append(text('p','目前沒有可顯示的工作。從對話建立提案，確認範圍後再開始。'));return;}
    for(const t of items){
      const row=text('button','');row.className='nexus-work-row';row.dataset.task=t.task_id;row.dataset.state=t.state;
      const title=text('strong',t.intent),state=text('span',names[t.state]||names.UNKNOWN);state.className='work-status';state.dataset.state=t.state;
      const badge=text('div','');badge.append(state);row.append(title,badge,text('span','↗'));
      row.setAttribute('aria-pressed',String(t.task_id===current.selected));
      if(parent.id==='nexus-recent'){
        row.setAttribute('aria-controls','nexus-work-peek');row.setAttribute('aria-pressed',String(t.task_id===peekId));
        row.onclick=()=>{peekId=t.task_id;renderPeek();};
      }else row.onclick=()=>openWork(t.task_id);
      parent.append(row);
    }
  }
  window.addEventListener('companion-state',e=>{
    current=e.detail;
    if(route==='project'&&projectStamp!==projectSignature())void loadProject();
    renderPeek();
    const selected=current.tasks.find(t=>t.task_id===current.selected);
    const steps={UNKNOWN:'先查看已回報事件，或回原對話釐清缺少的證據；不要把未知當作完成。',CREATED:'等待執行端回報。可展開執行觀察；目前沒有完成比例。',RUNNING:'查看已回報事件；如需中止，提出停止要求後仍須等待確認。',CANCEL_REQUESTED:'等待取消確認。停止要求不代表工作已取消。',CANCELLED:'這項工作已取消；如需繼續，回原對話重新確認工作範圍。',FAILED:'查看執行事件與失敗資訊，再回原對話討論下一步；不會自動重試。',RESULT_PENDING_REVIEW:'先閱讀確認範圍與限制，再接受、拒絕或記錄調整方向。接受成果不代表整套功能已通過驗證。',ACCEPTED:'審查決定已保存。可以返回原對話繼續討論尚未回答的問題。',REJECTED:'原始成果仍保留。返回原對話說明需要補充的證據。',REVISION_REQUESTED:'調整方向已保存。返回原對話確認後續提案；沒有自動執行新工作。'};
    el('nexus-next-step').textContent=current.offline?'連線未確認，請稍後重新讀取；目前不能作出審查決定。':selected?steps[selected.state]:'找不到此工作。請返回工作列表選取目前可見的工作，不會顯示其他工作的成果。';
    el('nexus-task-code').textContent=current.offline?'UNKNOWN':selected?.state||'UNKNOWN';
    const key=JSON.stringify([current.tasks,current.selected,current.offline,current.workspace,current.runtime]);if(signature===key)return;signature=key;
    el('nexus-project').textContent=current.workspace?.split(/[\\/]/).filter(Boolean).at(-1)||'目前工作區';
    el('nexus-project').title=current.workspace||'';
    const notice=current.offline?'本機連線未確認 · UNKNOWN':current.runtime==='bounded-python-source-audit-v1'?'受限唯讀查核已連接 · 不提供任意工程執行':current.runtime==='synthetic-no-ai'?'合成驗證環境 · 非真實模型執行':current.runtime||'執行端未確認';
    el('nexus-state-notice').textContent=el('nexus-execution-notice').textContent=notice;
    el('nexus-state-notice').hidden=el('nexus-execution-notice').hidden=!current.offline&&current.runtime==='bounded-python-source-audit-v1';
    rows(el('nexus-recent'),current.tasks.slice(0,4),current.offline);
    const execution=el('nexus-execution-list');execution.replaceChildren();
    if(current.offline){rows(execution,[],true);return;}
    for(const [heading,states,empty] of [
      ['進行中',['CREATED','RUNNING','CANCEL_REQUESTED'],'目前沒有準備中或執行中的工作。'],
      ['需要處理',['UNKNOWN','FAILED'],'目前沒有狀態未確認或失敗的工作。'],
      ['等待你審查',['RESULT_PENDING_REVIEW'],'目前沒有等待審查的成果。']]){
      const section=text('section',''),list=text('div',''),items=current.tasks.filter(t=>states.includes(t.state));
      section.append(text('h2',heading),list);execution.append(section);
      if(items.length)rows(list,items,false);else list.append(text('p',empty));
    }
    execution.append(text('p','已取消及已完成審查的工作，請至「工作」查看完整紀錄。這裡不推定完成比例，也不重播未保存的執行進度。'));
  });
  // A dedicated work-list entrance, ahead of the single result reader.
  const tray=document.querySelector('.task-tray');el('work-space').insertBefore(tray,el('stage'));
  for(const id of ['task-items','nexus-recent','nexus-execution-list','project-tasks'])el(id).addEventListener('keydown',e=>{
    if(!['ArrowDown','ArrowUp','ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;
    const buttons=[...el(id).querySelectorAll('button[data-task]')].filter(b=>!b.disabled&&b.getClientRects().length),at=buttons.indexOf(document.activeElement);
    if(at<0)return;
    e.preventDefault();const next=e.key==='Home'?0:e.key==='End'?buttons.length-1:Math.max(0,Math.min(buttons.length-1,at+(['ArrowDown','ArrowRight'].includes(e.key)?1:-1)));
    buttons[next]?.focus();
  });
  el('work-space').querySelector('.workspace-name h1').textContent='工作與成果';
  const back=text('button','← 所有工作');back.className='text-button';back.id='nexus-work-list';back.onclick=()=>go('work');
  el('work-space').insertBefore(back,el('stage'));
  const next=text('section','');next.className='nexus-next';next.append(text('h3','下一步'));
  const copy=text('p','');copy.id='nexus-next-step';next.append(copy);el('vessel-intro').after(next);
  const code=text('code','');code.id='nexus-task-code';el('task-id').parentElement.append(text('p','狀態代碼'),code);
  const scope=text('p','');scope.id='nexus-work-scope';next.prepend(scope);
  window.addEventListener('companion-work-origin',e=>{
    const p=e.detail;
    scope.textContent=p?'授權查核範圍：'+p.selection.map(k=>k+'.py').join('、')+'。僅查核來源結構，不執行功能測試。':'';
  });
  el('nexus-execute-title').nextElementSibling.textContent='集中查看進行中的工作、需要處理的問題及待審查成果。完整紀錄保留在「工作」。';
  // UX-05 shares the existing project identity and API boundary. Browsing these
  // pages never selects chat sources or sends a model request.
  let resourceEpoch=0,resourceContext=null,resourceLoading=false,documents=[],documentSelected=null;
  let documentSearchTimer=null;
  let documentPreview=null,sourceReview=null,requestedDocument=null,documentReturn=null;
  let documentFilter='all',linkFilter='all',resourceLinks=[],linkSelected=null,referenceApproval=null;
  const resourceRoutes=new Set(['documents','links']);
  for(const r of resourceRoutes){
    const nav=el('nexus-navigation').querySelector(`[data-route="${r}"]`);nav.querySelector('small')?.remove();
    const card=el('nexus-overview').querySelector(`[data-route="${r}"]`);
    card.querySelector('.module-bottom').replaceChildren(document.createTextNode(r==='documents'?'有限索引 · 唯讀預覽 ':'參考網址 · 本機保存 '),text('b','↗'));
  }
  const projectResources=document.querySelector('.project-stack>.nexus-panel:last-child');
  projectResources.querySelector('p').textContent='目前工作區的有限文件索引與帳戶專屬參考網址。外部工具與服務仍未連接。';
  projectResources.querySelector('button').textContent='查看專案文件 ↗';
  const linkEntry=text('button','查看參考連結 ↗');linkEntry.className='text-button';linkEntry.onclick=()=>go('links');projectResources.append(linkEntry);
  async function resourceAPI(action,body){
    const r=await fetch('/api/chat/resource-'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify(body)});
    const data=await r.json();if(!r.ok)throw Error(data.error||'資源目前不可用。');return data;
  }
  function resourceOwner(data){const owner=window.companionProjectStatus?.();return resourceContext && data.workspace===resourceContext.workspace && data.account===resourceContext.account && data.account===owner?.account && data.workspace===owner?.workspace;}
  function clearSourceReview(){
    sourceReview=null;
    for(const id of ['document-source-name','document-source-identity','document-source-chat','document-source-content','document-source-error','document-selection-note'])el(id).textContent='';
  }
  function clearDocument(){
    documentPreview=null;documentReturn=null;clearSourceReview();el('document-discuss').disabled=true;
    el('document-return-location').hidden=true;
    if(el('document-source-review').open)el('document-source-review').close();
    documentSelected=null;el('document-title').textContent='選取一份文件';el('document-relative').textContent='';el('document-type').textContent='—';
    el('document-project').textContent=resourceContext?.name||'尚未確認';el('document-source').textContent='尚未選取';
    el('document-content').textContent='';el('document-content').hidden=true;el('document-preview').disabled=true;
    el('document-notice').textContent='從索引選取文件，再開啟唯讀預覽。';
  }
  function resourceNavigation(next){
    clearTimeout(documentSearchTimer);
    if(requestedDocument)el('documents-search').value='';
    el('documents-index').open=!requestedDocument;
    const owner=window.companionProjectStatus?.();
    if(next!=='documents'||requestedDocument&&(requestedDocument.account!==owner?.account||requestedDocument.workspace!==owner?.workspace))requestedDocument=null;
    ++resourceEpoch;resourceLoading=false;resourceContext=null;documents=[];resourceLinks=[];linkSelected=null;referenceApproval=null;
    if(el('resource-confirm').open)el('resource-confirm').close();
    el('reference-open').removeAttribute('href');el('link-add-panel').hidden=true;clearDocument();
    el('link-title').textContent='選取一個連結';el('link-description').textContent='';el('link-type').textContent=el('link-purpose').textContent='—';el('link-open').disabled=true;el('link-notice').textContent='';
    for(const id of ['documents-list','links-list'])el(id).replaceChildren(text('p','正在確認目前帳戶及工作區…'));
    for(const id of ['documents-status','links-status'])el(id).textContent='尚未確認';
    document.querySelectorAll('[data-resource-project]').forEach(e=>e.textContent='正在確認目前專案');
    if(resourceRoutes.has(next))void loadResources();
  }
  async function loadResources(){
    if(!resourceRoutes.has(route)||resourceLoading)return;
    resourceLoading=true;const mine=++resourceEpoch,screen=route;
    try{
      const project=await window.companionProjectContext();
      if(mine!==resourceEpoch)return;
      if(project.account!==window.companionProjectStatus?.().account)throw Error('目前帳戶尚未確認。');
      resourceContext={account:project.account,workspace:project.project.id,name:project.project.name};
      const query=el('documents-search').value.trim();
      const data=await resourceAPI(screen==='documents'?'documents':'links',{workspace:resourceContext.workspace,...(screen==='documents'&&query?{query}:{})});
      if(mine!==resourceEpoch)return;if(!resourceOwner(data))throw Error('專案資源身分不一致。');
      document.querySelectorAll('[data-resource-project]').forEach(e=>e.textContent=resourceContext.name);
      if(screen==='documents'){
        documents=data.documents;clearDocument();el('documents-scope').textContent=data.scope;
        el('documents-status').textContent=`${documents.length} 份 · 有限唯讀索引`;renderDocuments();
        if(requestedDocument){
          const wanted=requestedDocument;requestedDocument=null;
          const current=documents.find(d=>d.relative===wanted.relative);
          if(current){
            documentFilter='all';el('documents-search').value='';
            document.querySelectorAll('[data-document-filter]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.documentFilter==='all')));renderDocuments();
            el('documents-list').querySelector(`[data-document="${current.id}"]`)?.click();
            documentReturn=wanted;
            el('document-notice').textContent=current.version===wanted.version?'已找到相同文件版本；歷史實際使用範圍保存在原回答。':'目前文件與歷史版本不同或已不可讀；請重新預覽。原回答仍保留當時的實際來源。';
            if(current.available)el('document-preview').click();
          }else el('document-notice').textContent='目前索引找不到原文件；歷史來源快照仍保存在原回答。';
        }
      }else{
        resourceLinks=[{id:'project',name:resourceContext.name,type:'project',available:true},...data.links.map(r=>({...r,type:'reference'})),{id:'unconnected',name:'外部工具與服務',type:'tool',available:false}];
        el('links-status').textContent=`${data.links.length} 筆參考網址 · 外部整合未接通`;renderLinks();selectLink(resourceLinks[0]);
      }
    }catch(e){if(mine===resourceEpoch){
      resourceContext=null;clearDocument();el(screen+'-status').textContent=e.message;
      el(screen+'-list').replaceChildren(text('p','目前無法取得資源；沒有顯示先前帳戶資料。'));
      if(!window.companionProjectStatus?.().account){
        const account=text('button','查看帳戶與登入');account.id=screen+'-account-open';
        account.type='button';account.className='secondary-button';
        account.onclick=()=>el('chat-signin-open').click();el(screen+'-list').append(account);
      }
    }}
    finally{if(mine===resourceEpoch)resourceLoading=false;}
  }
  function renderDocuments(){
    const list=el('documents-list');list.replaceChildren();
    for(const item of documents.filter(d=>documentFilter==='all'||d.category===documentFilter)){
      const b=text('button',''),info=text('span','');b.className='resource-row';b.dataset.document=item.id;b.setAttribute('aria-pressed',String(documentSelected?.id===item.id));
      info.append(text('strong',item.name),text('small',item.relative),text('small',item.available?'可唯讀預覽':'預覽受限'));b.append(text('span','▤'),info);
      b.onclick=()=>{window.companionClearSourceConsent?.();clearDocument();documentSelected=item;el('document-title').textContent=item.name;el('document-relative').textContent=item.relative;el('document-type').textContent=item.type;el('document-source').textContent=item.available?'尚未預覽 · 未提供給模型':'無法安全預覽';el('document-notice').textContent=item.status;el('document-preview').disabled=!item.available;renderDocuments();resourceDetailFocus('document');};list.append(b);
    }
    if(!list.children.length)list.append(text('p',documents.length||el('documents-search').value.trim()?'沒有符合條件的文件。':'此工作區目前沒有可列出的文件。'));
  }
  el('documents-search').oninput=()=>{
    ++resourceEpoch;resourceLoading=false;clearTimeout(documentSearchTimer);
    documents=[];clearDocument();el('documents-list').replaceChildren(text('p','正在搜尋目前可讀文件…'));
    el('documents-status').textContent='搜尋中';
    documentSearchTimer=setTimeout(()=>{if(route==='documents')resourceNavigation('documents');},150);
  };
  document.querySelectorAll('[data-document-filter]').forEach(b=>b.onclick=()=>{documentFilter=b.dataset.documentFilter;document.querySelectorAll('[data-document-filter]').forEach(e=>e.setAttribute('aria-pressed',String(e===b)));renderDocuments();});
  el('document-preview').onclick=async()=>{
    if(!documentSelected||!resourceContext)return;
    el('document-return-location').hidden=true;
    const item=documentSelected,mine=resourceEpoch;documentPreview=null;el('document-discuss').disabled=true;el('document-preview').disabled=true;el('document-content').textContent='';el('document-content').hidden=true;
    try{const data=await resourceAPI('preview',{workspace:resourceContext.workspace,id:item.id,version:item.version});if(mine!==resourceEpoch||documentSelected!==item)return;if(!resourceOwner(data))throw Error('文件身分不一致。');documentPreview=data;el('document-discuss').disabled=false;el('document-content').textContent=data.text;el('document-content').hidden=false;el('document-source').textContent=data.status;el('document-notice').textContent='原始文字 · 僅於本頁閱讀';locateReturnedExcerpt(data);}
    catch(e){if(mine===resourceEpoch&&documentSelected===item){el('document-source').textContent='預覽未確認';el('document-notice').textContent=e.message;}}
    finally{if(mine===resourceEpoch&&documentSelected===item)el('document-preview').disabled=!item.available;}
  };
  const documentLines=value=>{
    if(!value)return [];
    const lines=value.split(/\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]/);
    if(lines.at(-1)==='')lines.pop();return lines;
  };
  function focusReturnedExcerpt(){
    const marker=el('document-source-location');if(!marker)return;
    marker.scrollIntoView({block:'center',inline:'nearest'});marker.focus({preventScroll:true});
  }
  function locateReturnedExcerpt(data){
    const wanted=documentReturn;el('document-return-location').hidden=true;
    if(!wanted||wanted.account!==data.account||wanted.workspace!==data.workspace||wanted.relative!==data.relative)return;
    if(wanted.version!==data.version){el('document-notice').textContent='目前文件與歷史版本不同，未定位舊節錄。請核對目前內容；原回答仍保留當時的來源。';return;}
    if(wanted.scope!=='excerpt'){el('document-notice').textContent='已開啟相同版本的來源文件；當時只提供文件名稱，沒有節錄位置。';return;}
    const lines=documentLines(data.text),start=wanted.start_line,end=wanted.end_line;
    if(!Number.isInteger(start)||!Number.isInteger(end)||start<1||end<start||end>lines.length||lines.slice(start-1,end).join('\n')!==wanted.text){
      el('document-notice').textContent='歷史節錄位置無法核對；請閱讀目前原文，並回原回答查看來源快照。';return;
    }
    // Preserve the exact text and line endings, including CRLF. Markup is
    // display-only; selecting or locating text grants no model authority.
    const ranges=[];let cursor=0,match;const breaks=/\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]/g;
    while((match=breaks.exec(data.text))){ranges.push({start:cursor,end:match.index});cursor=breaks.lastIndex;}
    if(cursor<data.text.length)ranges.push({start:cursor,end:data.text.length});
    const from=ranges[start-1].start,to=ranges[end-1].end,marker=text('mark',data.text.slice(from,to));
    marker.id='document-source-location';marker.tabIndex=-1;marker.setAttribute('aria-label','原節錄 L'+start+'–L'+end);
    el('document-content').replaceChildren(document.createTextNode(data.text.slice(0,from)),marker,document.createTextNode(data.text.slice(to)));
    el('document-return-location').textContent='定位原節錄 L'+start+'–L'+end;el('document-return-location').hidden=false;
    el('document-notice').textContent='已核對相同文件版本，定位原節錄 L'+start+'–L'+end+'；目前只供閱讀，未加入本輪對話資料。';
    focusReturnedExcerpt();
  }
  el('document-return-location').onclick=focusReturnedExcerpt;
  function selectedDocumentLines(){
    const selection=getSelection(),content=el('document-content');
    if(!selection||selection.rangeCount!==1||selection.isCollapsed||content.hidden)return null;
    const range=selection.getRangeAt(0);
    if(!content.contains(range.startContainer)||!content.contains(range.endContainer)||!range.toString().trim())return null;
    const before=range.cloneRange(),through=range.cloneRange();
    before.selectNodeContents(content);before.setEnd(range.startContainer,range.startOffset);
    through.selectNodeContents(content);through.setEnd(range.endContainer,range.endOffset);
    // Match Python splitlines; a selection ending at the next line's start
    // excludes that untouched line. Only whole, visibly reviewed lines transfer.
    const start=(before.toString().match(/\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]/g)||[]).length+1;
    return {start,end:documentLines(through.toString()).length};
  }
  function sourceScope(){
    const p=sourceReview?.preview,scope=document.querySelector('input[name="document-scope"]:checked').value;
    const start=scope==='excerpt'?Number(el('document-excerpt-start').value):null,end=scope==='excerpt'?Number(el('document-excerpt-end').value):null;
    const lines=documentLines(p?.text||'');
    const content=scope==='name'?p?.relative.split('/').at(-1)||'':lines.slice(start-1,end).join('\n');
    const valid=scope==='name'||(Number.isInteger(start)&&Number.isInteger(end)&&start>=1&&end>=start&&end<=lines.length&&end-start<40&&content.trim()&&new TextEncoder().encode(content).length<=8192);
    el('document-excerpt-controls').hidden=scope!=='excerpt';el('document-source-content').textContent=content;
    el('document-source-confirm').disabled=!valid;el('document-source-error').textContent=valid?'':'請選擇有效的連續 1–40 行，最多 8 KiB。';
    return {scope,start,end,content,valid};
  }
  el('document-discuss').onclick=()=>{
    const status=window.companionProjectStatus?.();
    if(!documentPreview||!resourceOwner(documentPreview)||!status?.account)return;
    const excerpt=selectedDocumentLines();
    sourceReview={preview:documentPreview,account:status.account,chat:status.chat||null,epoch:resourceEpoch};
    el('document-source-name').textContent=documentPreview.relative;
    el('document-source-identity').textContent='文件版本 SHA-256 '+documentPreview.version;
    el('document-source-chat').textContent=status.chat?'沿用目前選取的對話；不改變專案關聯。':'在現有 Companion 建立新對話；不改變專案關聯。';
    document.querySelector('input[name="document-scope"][value="'+(excerpt?'excerpt':'name')+'"]').checked=true;
    el('document-excerpt-start').value=excerpt?.start||1;el('document-excerpt-end').value=excerpt?.end||Math.min(20,documentLines(documentPreview.text).length);
    el('document-selection-note').hidden=!excerpt;
    el('document-selection-note').textContent=excerpt?'已將選取內容擴展為整行；可展開「調整分享範圍」修改。':'';
    el('document-source-adjust').open=!excerpt;
    sourceScope();el('document-source-review').showModal();
  };
  for(const input of document.querySelectorAll('input[name="document-scope"],#document-excerpt-start,#document-excerpt-end'))input.addEventListener('input',sourceScope);
  el('document-source-review').addEventListener('close',clearSourceReview);
  el('document-source-confirm').onclick=async()=>{
    const pending=sourceReview,scope=sourceScope();if(!pending||!scope.valid)return;
    el('document-source-confirm').disabled=true;
    let granted;
    try{
      granted=await resourceAPI('source-preview',{workspace:pending.preview.workspace,id:pending.preview.id,version:pending.preview.version,chat:pending.chat,scope:scope.scope,start:scope.start,end:scope.end});
      const status=window.companionProjectStatus?.();
      if(sourceReview!==pending||pending.epoch!==resourceEpoch||status?.account!==pending.account||(status.chat||null)!==pending.chat)throw Error('帳戶、文件或對話已變更，請重新確認。');
      const current=sourceScope();
      if(current.scope!==scope.scope||current.start!==scope.start||current.end!==scope.end||granted.source.text!==scope.content)throw Error('本次提供範圍已變更，請重新確認。');
      el('document-source-review').close();window.openDocumentCompanion(granted);
    }catch(e){
      if(granted)void resourceAPI('source-cancel',{workspace:granted.workspace,key:granted.source.key}).catch(()=>{});
      if(sourceReview===pending&&el('document-source-review').open){el('document-source-error').textContent=e.message;el('document-source-confirm').disabled=false;}
      if(pending.epoch===resourceEpoch)el('document-notice').textContent=e.message;
    }
  };
  window.nexusReturnDocument=source=>{
    const owner=window.companionProjectStatus?.();
    if(!owner?.account||!owner.workspace||typeof source?.relative!=='string'||typeof source.version!=='string')return;
    requestedDocument={account:owner.account,workspace:owner.workspace,relative:source.relative,version:source.version,
      scope:source.scope,start_line:source.start_line,end_line:source.end_line,text:source.text};
    if(route==='documents'&&window.companionLocateDocument?.())resourceNavigation('documents');
    else go('documents');
  };
  function renderLinks(){
    const list=el('links-list');list.replaceChildren();
    for(const item of resourceLinks.filter(r=>linkFilter==='all'||r.type===linkFilter)){
      const b=text('button',''),info=text('span','');b.className='resource-row';b.dataset.link=item.id;b.setAttribute('aria-pressed',String(linkSelected?.id===item.id));
      info.append(text('strong',item.name),text('small',item.type==='project'?'專案導覽':item.type==='tool'?'未接通 · 不能操作':item.available?'參考網址 · 已保存':'參考網址不可用'));
      b.append(text('span',item.type==='project'?'◎':'↗'),info);b.onclick=()=>{selectLink(item);resourceDetailFocus('link');};list.append(b);
    }
    if(!list.children.length)list.append(text('p','目前沒有這類參考連結。'));
  }
  function selectLink(item){
    linkSelected=item;el('link-title').textContent=item.name;el('link-description').textContent=item.url|| (item.type==='project'?'目前啟動的本機工作區。':'沒有登入、同步或工具操作能力。');
    el('link-type').textContent=item.type==='reference'?'外部參考網址':item.type==='project'?'NEXUS 內部導覽':'外部工具與服務';
    el('link-purpose').textContent=item.type==='reference'?'手動開啟網頁':item.type==='project'?'返回專案情境':'尚未接通';
    el('link-open').disabled=!item.available;el('link-open').textContent=item.type==='reference'?'檢查並開啟網址 ↗':item.type==='project'?'查看專案情境 ↗':'尚未接通';
    el('link-notice').textContent=item.type==='reference'?'保存網址不會自動存取網站；開啟前會再次確認。':'此入口不會授予檔案、帳戶或外部工具權限。';renderLinks();
  }
  function resourceDetailFocus(kind){
    if(innerWidth>1100)return;
    const title=el(kind+'-title');title.tabIndex=-1;
    el(kind+'-detail').scrollIntoView({block:'start'});title.focus({preventScroll:true});
  }
  document.querySelectorAll('[data-link-filter]').forEach(b=>b.onclick=()=>{linkFilter=b.dataset.linkFilter;document.querySelectorAll('[data-link-filter]').forEach(e=>e.setAttribute('aria-pressed',String(e===b)));renderLinks();});
  function confirmReference(data,opening){
    el('resource-confirm-name').textContent=data.name;el('resource-confirm-url').textContent=data.url;
    el('resource-confirm-copy').textContent=opening?'接下來由瀏覽器開啟外部網頁；NEXUS 不會讀取網站或登入。':'只保存這筆參考網址至目前帳戶與工作區；不會存取網站或授權模型。';
    el('resource-confirm-error').textContent='';el('reference-save').hidden=opening;el('reference-open').hidden=!opening;
    el('reference-open').removeAttribute('href');if(opening)el('reference-open').href=data.url;
    el('resource-confirm').showModal();
  }
  el('link-open').onclick=async()=>{
    if(linkSelected?.type==='project'){go('project');return;}if(!resourceContext||!linkSelected?.available)return;
    const mine=resourceEpoch,item=linkSelected;el('link-open').disabled=true;
    try{const data=await resourceAPI('link-open',{workspace:resourceContext.workspace,id:item.id});if(mine!==resourceEpoch||item!==linkSelected)return;if(!resourceOwner(data))throw Error('參考網址身分不一致。');confirmReference(data,true);}
    catch(e){if(mine===resourceEpoch)el('link-notice').textContent=e.message;}
    finally{if(mine===resourceEpoch&&item===linkSelected)el('link-open').disabled=!item.available;}
  };
  el('reference-open').onclick=()=>el('resource-confirm').close();
  el('link-add').onclick=()=>{el('link-add-panel').hidden=false;el('reference-notice').textContent='';el('reference-name').focus();};
  el('link-add-close').onclick=()=>{el('link-add-panel').hidden=true;el('link-add').focus();};
  el('reference-form').onsubmit=async e=>{
    e.preventDefault();if(!resourceContext)return;const mine=resourceEpoch;
    try{const data=await resourceAPI('link-preview',{workspace:resourceContext.workspace,name:el('reference-name').value,url:el('reference-url').value});if(mine!==resourceEpoch)return;if(!resourceOwner(data))throw Error('目前帳戶已變更。');referenceApproval=data;confirmReference(data,false);}
    catch(error){if(mine===resourceEpoch)el('reference-notice').textContent=error.message;}
  };
  el('reference-save').onclick=async()=>{
    const pending=referenceApproval,mine=resourceEpoch;if(!pending||!resourceContext)return;el('reference-save').disabled=true;referenceApproval=null;
    try{const data=await resourceAPI('link-confirm',{workspace:pending.workspace,approval:pending.approval});if(mine!==resourceEpoch)return;if(!resourceOwner(data))throw Error('目前帳戶已變更。');el('resource-confirm').close();el('reference-form').reset();await loadResources();el('link-add-panel').hidden=false;el('reference-notice').textContent='已保存參考網址；沒有存取網站。';const item=resourceLinks.find(r=>r.id===data.id);if(item)selectLink(item);}
    catch(e){if(mine===resourceEpoch)el('resource-confirm-error').textContent=e.message;}
    finally{el('reference-save').disabled=false;}
  };
  el('resource-confirm').addEventListener('close',()=>{referenceApproval=null;el('reference-open').removeAttribute('href');});
  el('documents-refresh').onclick=el('links-refresh').onclick=()=>resourceNavigation(route);
  window.addEventListener('companion-project',()=>{
    const owner=window.companionProjectStatus?.();
    if(resourceRoutes.has(route)&&(!resourceContext||resourceContext.account!==owner?.account||resourceContext.workspace!==owner?.workspace))resourceNavigation(route);
  });
  for(const id of ['documents-list','links-list'])el(id).addEventListener('keydown',e=>{
    if(!['ArrowDown','ArrowUp','Home','End'].includes(e.key))return;const buttons=[...el(id).querySelectorAll('button')],i=buttons.indexOf(document.activeElement);if(i<0)return;e.preventDefault();buttons[e.key==='Home'?0:e.key==='End'?buttons.length-1:Math.max(0,Math.min(buttons.length-1,i+(e.key==='ArrowDown'?1:-1)))]?.focus();
  });
  const initial=location.hash.slice(1).split('?')[0]||'overview';
  if(initial==='work'&&location.hash.includes('?'))restoreRoute();
  else {restoring=true;go(initial,false,true);restoring=false;}
  updateChatEntry();
})();
