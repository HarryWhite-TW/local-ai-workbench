/* One conversation surface; only explicit Send invokes the existing chat API.
 * NEXUS can retain owner-scoped, DPAPI-encrypted drafts and preferences on the
 * local host. With host continuity, browser storage contains metadata only.
 */
(() => {
  if(document.body.dataset.chatEnabled!=='true')return;
  const el=id=>document.getElementById(id), drafts=new Map(), positions=new Map(), optionLists=new WeakMap();
  let state=null, selected='', sending=false, loading=false, connected=false, epoch=0, rendered='', renderedChat=null;
  let preview=null, sourceVersion=0, accountChoice, catalogAttempt=null, workScroll=0;
  let documentSource=null;
  let authChanging=false,authEpoch=0;
  let catalogLoading=false,catalogError='';
  const workEnabled=document.body.dataset.workEnabled==='true';
  const organizeEnabled=document.body.dataset.organizeEnabled==='true';
  let workspace='',sessionKey='',sessionReady=false,sessionSaved=false;
  let continuityReady=false,continuityLoading=false,continuityRevision=0,continuitySerial='',continuityError='';
  let continuityPending=false,continuitySaving=null,continuityTimer=null,continuityGeneration=0,authPreparing=false;
  let continuityRestored=null,continuityReview=null;
  let continuityPreferences=null;
  const initialParams=new URLSearchParams(location.hash.split('?')[1]);
  let requestedChat=location.hash.startsWith('#chat?')?initialParams.get('chat'):null;
  let workOrigin=null, proposal=null, approval=null;
  let floating=null,returnWork=null,contextEpoch=0,workFacts={tasks:[],offline:true};
  const reconcileFeedback=new Map();
  const nativeResults=new Map(),nativeLoading=new Map();
  let proposalOwner=null,proposalVersion=0;
  const windowKey='companion.nexus.window.v1';
  const windowModes=['floating','dock-left','dock-right','split-left','split-right','reading'];
  let windowMode='floating',windowRect=null,miniRect=null,windowGesture=null;
  let projectLink=null,projectLinkStatus='idle',projectKey='',projectRead=0,projectConfirm=null,projectEvent='';
  try{
    const saved=JSON.parse(localStorage.getItem(windowKey)||'null');
    if(saved){
      if(windowModes.includes(saved.mode))windowMode=saved.mode;
      if(saved.window&&['x','y','width','height'].every(k=>Number.isFinite(saved.window[k])))windowRect=saved.window;
      if(saved.mini&&['x','y','width','height'].every(k=>Number.isFinite(saved.mini[k])))miniRect=saved.mini;
    }
  }catch{}
  const chatHome=el('chat-space').parentElement,chatAnchor=el('chat-space').nextSibling;
  const workNames=window.CompanionReading?.states||{UNKNOWN:'執行狀態未確認',CREATED:'準備中',RUNNING:'執行中',CANCEL_REQUESTED:'停止待確認',CANCELLED:'已取消',FAILED:'執行失敗',RESULT_PENDING_REVIEW:'成果等待審查',ACCEPTED:'人類已接受成果',REJECTED:'人類已拒絕成果',REVISION_REQUESTED:'已記錄調整方向'};
  const text=(tag,value)=>{const n=document.createElement(tag);n.textContent=value;return n;};
  const notice=value=>{if(el('chat-notice').textContent!==value)el('chat-notice').textContent=value;};
  const chosen=()=>documentSource?[documentSource.source.key]:[...el('chat-sources').querySelectorAll('input:checked')].map(n=>n.value);
  const inChat=()=>document.body.dataset.space==='chat'||(!!floating?.ready&&!floating.minimized);
  function projectStatus() {
    return {account:!authChanging&&!state?.auth.pending?state?.auth.active||'':'',workspace,chat:selected,status:projectLinkStatus,
      association:projectLinkStatus==='ready'?projectLink?.association||null:null,
      sources:chosen().length,preview:!!preview};
  }
  function renderProjectBinding() {
    if(!workEnabled)return;
    el('project-chat-strip').hidden=false;
    const ready=projectLinkStatus==='ready',association=ready&&projectLink?.association;
    el('project-chat-binding').textContent=association?'已關聯：'+association.project.name:ready?'目前對話未關聯專案':
      !state?.auth.active||state.auth.pending?'請先完成登入':!selected?'新對話尚未保存':projectLinkStatus==='error'?'專案關聯無法確認':'正在確認專案關聯…';
    el('project-chat-help').textContent=!selected?'先傳送訊息保存對話，再自行確認專案關聯；不會自動分享資料。':'關聯只保存專案標記；資料仍須另外選取、預覽並傳送。';
    el('project-chat-link').disabled=!ready||!!association||sending||!!state?.busy;
    el('project-chat-unlink').hidden=!association;el('project-chat-unlink').disabled=!ready||sending||!!state?.busy;
    const value=JSON.stringify(projectStatus());
    if(value!==projectEvent){projectEvent=value;window.dispatchEvent(new CustomEvent('companion-project',{detail:projectStatus()}));}
  }
  function cancelProjectPreview() {
    projectConfirm=null;if(el('project-confirm').open)el('project-confirm').close();
  }
  async function readProjectLink(force=false) {
    if(!workEnabled)return;
    const key=JSON.stringify([workspace,state?.auth.active,!!state?.auth.pending,selected]);
    if(!force&&key===projectKey)return;
    projectKey=key;const mine=++projectRead;projectLink=null;projectLinkStatus='loading';cancelProjectPreview();
    if(!workspace||!state?.auth.active||state.auth.pending||!selected){projectLinkStatus='idle';renderProjectBinding();return;}
    renderProjectBinding();
    try {
      const value=await api('project-get',{chat:selected});
      if(mine!==projectRead)return;
      if(value.chat!==selected||value.account!==state.auth.active||value.workspace!==workspace)throw Error('專案關聯身分未確認。');
      projectLink=value;projectLinkStatus='ready';
    }catch{if(mine!==projectRead)return;projectLinkStatus='error';}
    renderProjectBinding();
  }
  async function previewProjectLink(action) {
    if(projectLinkStatus!=='ready'||!selected)return;
    const chat=selected,account=state.auth.active,mine=contextEpoch;
    try {
      const value=await api('project-preview',{chat,action});
      if(selected!==chat||state.auth.active!==account||mine!==contextEpoch)return;
      projectConfirm={chat,action,approval:value.approval,account,epoch:mine};
      el('project-confirm-title').textContent=action==='link'?'確認關聯專案':'確認解除關聯';
      el('project-confirm-copy').textContent=(action==='link'?'將目前對話關聯至：':'解除目前對話與此專案的關聯：')+value.project.name+'\n'+value.project.workspace;
      el('project-confirm-notice').textContent='';el('project-confirm-save').disabled=false;openAux('project-confirm');
    }catch(e){notice(e.message);}
  }
  async function api(path,body,options={}) {
    const r=await fetch('/api/chat/'+path,body===undefined?{cache:'no-store'}:{
      method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify(body),...options});
    const data=await r.json();if(!r.ok)throw new Error(data.error||'連線未確認成功，請重新讀取。');return data;
  }
  function options(node,values,value,empty) {
    const signature=JSON.stringify(values);
    if(optionLists.get(node)!==signature) {
      node.replaceChildren();if(empty)node.append(new Option(empty,''));
      for(const item of values)node.append(new Option(item.label,item.id));
      optionLists.set(node,signature);
    }
    if([...node.options].some(o=>o.value===value))node.value=value;
  }
  function windowBounds(rect,mini=false) {
    const maxW=Math.max(1,Math.min(innerWidth-16,mini?480:Infinity)),maxH=Math.max(1,Math.min(innerHeight-16,mini?160:Infinity));
    const width=Math.min(maxW,Math.max(Math.min(mini?210:300,maxW),rect.width));
    const height=Math.min(maxH,Math.max(Math.min(mini?60:440,maxH),rect.height));
    return {x:Math.max(8,Math.min(innerWidth-width-8,rect.x)),y:Math.max(8,Math.min(innerHeight-height-8,rect.y)),width,height};
  }
  function saveWindow(persist=true) {
    // Geometry is a preference only: no work/chat IDs, content or source authority.
    try{localStorage.setItem(windowKey,JSON.stringify({mode:windowMode,window:windowRect,mini:miniRect}));}catch{}
    if(persist)persistChat();
  }
  function placeWindow(node,rect) {
    for(const [key,value] of Object.entries(rect))node.style[{x:'left',y:'top'}[key]||key]=value+'px';
  }
  function layoutWindow() {
    const body=document.body,panel=el('companion-panel'),mini=el('companion-mini');
    body.dataset.companionLayout='';body.style.removeProperty('--companion-occupied');
    el('document-chat-toggle').hidden=!floating?.document;
    el('companion-read-document').hidden=!floating?.document;
    if(!floating){mini.hidden=true;return;}
    windowRect??={x:innerWidth-496,y:Math.max(8,innerHeight-856),width:480,height:Math.min(840,innerHeight-16)};
    miniRect??={x:innerWidth-256,y:innerHeight-88,width:240,height:64};
    mini.hidden=!floating.minimized;panel.hidden=!!floating.minimized;
    if(floating.minimized){placeWindow(mini,windowBounds(miniRect,true));return;}
    const top=innerWidth<=760?64:80;
    const sidebar=el('nexus-sidebar')?.getClientRects().length?parseFloat(getComputedStyle(body).getPropertyValue('--nexus-nav-width'))||0:0;
    const available=innerWidth-sidebar-24,compact=available<720;
    if(floating.document&&compact){
      panel.hidden=!!floating.reading;
      if(floating.reading)return;
      placeWindow(panel,{x:8,y:64,width:innerWidth-16,height:innerHeight-72});
      panel.dataset.mode='document-tabs';panel.dataset.compact=String(innerHeight<650);
      el('companion-window-resize').hidden=true;
      el('companion-window-status').textContent='閱讀文件與對話可隨時切換';
      return;
    }
    let rect=windowBounds(windowRect);
    if(windowMode==='reading')rect=windowBounds({x:sidebar+8,y:top,width:available+8,height:innerHeight-top-8});
    else if(windowMode!=='floating'){
      if(compact){
        rect=windowBounds({x:8,y:innerHeight-Math.min(innerHeight*.60,460)-8,width:innerWidth-16,height:Math.min(innerHeight*.60,460)});
        body.dataset.companionLayout='stacked';body.style.setProperty('--companion-occupied',(rect.height+16)+'px');
      }else{
        const split=windowMode.startsWith('split'),left=windowMode.endsWith('left');
        const width=split?(floating.document?Math.min(480,Math.floor(available*.42)):Math.floor(available/2)):Math.min(560,Math.max(340,Math.min(windowRect.width,available-340)));
        rect=windowBounds({x:left?sidebar+8:innerWidth-width-8,y:top,width,height:innerHeight-top-8});
        body.dataset.companionLayout=left?'left':'right';body.style.setProperty('--companion-occupied',(rect.width+16)+'px');
      }
    }
    body.style.setProperty('--companion-nav',sidebar+'px');
    const scroller=el('chat-messages'),scroll=scroller.scrollTop;
    placeWindow(panel,rect);panel.dataset.mode=windowMode;panel.dataset.compact=String(rect.height<570);
    el('companion-window-mode').value=windowMode;el('companion-window-resize').hidden=windowMode!=='floating';
    const label=compact&&windowMode!=='floating'&&windowMode!=='reading'?'窄視窗：上下並排':'';
    if(el('companion-window-status').textContent!==label)el('companion-window-status').textContent=label;
    fitInput();scroller.scrollTop=scroll;
  }
  function setWindowMode(mode) {
    if(!windowModes.includes(mode))return;
    windowMode=mode;if(floating?.ready)++contextEpoch;clearSources();saveWindow();layoutWindow();
  }
  function minimizeWindow() {
    if(!floating?.ready)return;
    saveDraft();floating.scroll=el('chat-messages').scrollTop;++contextEpoch;clearSources();floating.minimized=true;
    el('companion-panel').close();layoutWindow();saveWindow();updateContext();
    el('companion-restore').focus({preventScroll:true});
  }
  function restoreWindow() {
    if(!floating?.minimized)return;
    ++contextEpoch;clearSources();floating.minimized=false;
    el('companion-panel').hidden=false;el('companion-panel').show();layoutWindow();updateContext();
    el('chat-messages').scrollTop=floating.scroll||0;refresh();
    el('chat-question').focus({preventScroll:true});
  }
  function endWindowGesture() {
    if(!windowGesture)return;
    const {node,id}=windowGesture;windowGesture=null;
    if(node.hasPointerCapture(id))node.releasePointerCapture(id);saveWindow();
  }
  function windowControl(node,mini,size) {
    node.addEventListener('pointerdown',event=>{
      if(event.button!==0||!floating||!!floating.minimized!==mini||(!mini&&windowMode!=='floating'))return;
      if(!mini&&!size&&event.target.closest('button,select,input,textarea,a'))return;
      event.preventDefault();endWindowGesture();
      const box=(mini?el('companion-mini'):el('companion-panel')).getBoundingClientRect();
      windowGesture={node,id:event.pointerId,x:event.clientX,y:event.clientY,rect:{x:box.x,y:box.y,width:box.width,height:box.height},mini,size};
      node.setPointerCapture(event.pointerId);(node.id==='companion-window-header'?el('companion-panel-title'):node).focus({preventScroll:true});
    });
    node.addEventListener('pointermove',event=>{
      const g=windowGesture;if(!g||g.id!==event.pointerId||g.node!==node)return;
      const dx=event.clientX-g.x,dy=event.clientY-g.y;
      const rect=windowBounds(g.size?{...g.rect,width:g.rect.width+dx,height:g.rect.height+dy}:{...g.rect,x:g.rect.x+dx,y:g.rect.y+dy},g.mini);
      if(g.mini)miniRect=rect;else windowRect=rect;layoutWindow();
    });
    for(const event of ['pointerup','pointercancel','lostpointercapture'])node.addEventListener(event,endWindowGesture);
    const keyboard=node.id==='companion-window-header'?el('companion-panel-title'):node;
    keyboard.addEventListener('keydown',event=>{
      const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[event.key];
      if(!delta||!floating||!!floating.minimized!==mini)return;
      event.preventDefault();if(!mini&&windowMode!=='floating')setWindowMode('floating');
      const step=event.shiftKey?32:8,r=windowBounds((mini?miniRect:windowRect)||{x:8,y:8,width:480,height:700},mini);
      const rect=windowBounds(size?{...r,width:r.width+delta[0]*step,height:r.height+delta[1]*step}:{...r,x:r.x+delta[0]*step,y:r.y+delta[1]*step},mini);
      if(mini)miniRect=rect;else windowRect=rect;layoutWindow();saveWindow();
    });
  }
  function updateContext() {
    if(!workEnabled)return;
    const work=workFacts.tasks.find(t=>t.task_id===workFacts.selected);
    el('companion-ask').hidden=!work;
    el('companion-ask').disabled=!state||sending;
    el('companion-ask').setAttribute('aria-expanded',String(!!floating&&!floating.minimized));
    el('companion-minimize').disabled=!floating?.ready;
    el('companion-unlinked-task').textContent=floating&&work?work.intent+' · '+(workFacts.offline?workNames.UNKNOWN:workNames[work.state]||workNames.UNKNOWN):'';
    const context=returnWork?.chat===selected?workFacts.tasks.find(t=>t.task_id===returnWork.task):null;
    el('companion-context').hidden=!context;
    el('companion-context').dataset.task=context?.task_id||'';
    el('companion-panel').dataset.task=floating?.task||'';
    if(context){
      el('companion-task-name').textContent=context.intent;
      el('companion-task-state').textContent=workFacts.offline?workNames.UNKNOWN:workNames[context.state]||workNames.UNKNOWN;
      el('companion-task-state').dataset.state=workFacts.offline?'UNKNOWN':context.state;
    }else{el('companion-task-name').textContent='';el('companion-task-state').textContent='';}
    el('companion-share-result').disabled=!context||!returnWork?.linked||workFacts.offline||sending||
      !['RESULT_PENDING_REVIEW','ACCEPTED','REJECTED','REVISION_REQUESTED'].includes(context.state);
    const sources=[...el('chat-sources').querySelectorAll('input:checked')].map(n=>n.parentElement.textContent.trim());
    el('companion-sharing').textContent=sources.length?'本次提供：'+sources.join('、')+(preview?' · 已預覽，傳送時才分享。':' · 尚待預覽。'):
      '本次未加入工作資料。沿用目前對話歷史；不能據此確認最新成果。';
    el('companion-expand').disabled=!floating?.ready;
  }
  function closeFloating(focus=true) {
    if(!floating)return;
    endWindowGesture();++contextEpoch;saveDraft();floating=null;layoutWindow();
    for(const id of ['chat-knowledge','chat-source-dialog','work-proposal'])if(el(id).open)el(id).close();
    if(el('companion-panel').open)el('companion-panel').close();
    chatHome.insertBefore(el('chat-space'),chatAnchor);
    el('chat-space').hidden=document.body.dataset.space!=='chat';
    clearSources();updateContext();
    if(focus&&!el('companion-ask').hidden)el('companion-ask').focus({preventScroll:true});
  }
  function activateFloating(chat,linked) {
    if(!floating)return;
    switchConversation(chat,true);
    returnWork={task:floating.task,chat:selected,top:floating.top,linked};
    floating.ready=true;el('companion-unlinked').hidden=true;el('chat-space').hidden=false;
    saveDraft();updateSend();layoutWindow();refresh();el('chat-question').focus({preventScroll:true});
  }
  async function openFloating() {
    const task=workFacts.tasks.find(t=>t.task_id===workFacts.selected);
    if(!workEnabled||!task||sending||document.body.dataset.workDetail!=='true')return;
    closeFloating(false);saveDraft();clearSources();
    const mine=++contextEpoch,account=state?.auth.active;
    floating={task:task.task_id,account,top:scrollY,ready:false};returnWork=null;
    el('companion-panel-body').append(el('chat-space'));el('chat-space').hidden=true;
    el('companion-unlinked').hidden=false;el('companion-start-new').hidden=true;
    el('companion-link-notice').textContent='正在核對這項工作的原對話；尚未分享工作資料。';
    el('companion-panel').hidden=false;el('companion-panel').show();layoutWindow();updateContext();
    try{
      const origin=await api('work-origin',{task_id:task.task_id});
      if(mine!==contextEpoch||workFacts.selected!==task.task_id||state?.auth.active!==account)return;
      if(origin.task_id!==task.task_id||!visibleChat(origin.chat))throw Error('原對話不在目前帳戶可選取的紀錄中。');
      activateFloating(origin.chat,true);
    }catch(e){
      if(mine!==contextEpoch)return;
      el('companion-link-notice').textContent=e.message+' 可另開新對話普通聊天；不會自動加入這項工作的內容或成果。';
      el('companion-start-new').hidden=false;el('companion-start-new').focus();
    }
  }
  function updateSend() {
    if(el('organize-open')){el('organize-open').hidden=!organizeEnabled;el('organize-open').disabled=!workspace||!connected||sending||authChanging||authPreparing||!!state?.busy||!state?.auth.active||!!state?.auth.pending;}
    const hasSource=chosen().length>0;
    const model=state?.models.find(m=>m.slug===el('chat-model').value);
    const needsLogin=!state?.auth.active||state.auth.accounts.find(a=>a.id===state.auth.active)?.signed_in===false;
    el('chat-send').disabled=!connected||sending||authChanging||authPreparing||!!state?.busy||!state?.auth.active||state?.auth.pending||
      needsLogin||catalogLoading||!model||(hasSource&&!preview)||!!window.NexusOrganize?.active();
    el('chat-question').disabled=sending||authChanging||authPreparing||!connected||(workEnabled&&!sessionReady&&!!state?.continuity);
    el('chat-new').disabled=el('chat-history').disabled=sending||authChanging||authPreparing||(workEnabled&&!sessionReady&&!!state?.continuity);
    el('chat-source-status').textContent=hasSource?chosen().length+' 項資料'+(preview?' · 已預覽':' · 待預覽'):'';
    el('chat-knowledge-done').disabled=hasSource&&!preview;
    el('chat-preview').disabled=!hasSource;
    el('chat-signin').hidden=!!state?.auth.pending||(connected&&!needsLogin&&!!model);
    el('chat-signin-open').hidden=!connected;
    el('chat-signin-open').textContent=state?.auth.active?(needsLogin?'重新登入此帳戶':'帳戶與模型'):'登入 ChatGPT';
    el('chat-recover').hidden=connected&&needsLogin;
    el('chat-recover').disabled=catalogLoading||authChanging||!!state?.busy;
    el('chat-recover').textContent=!connected?'重新連接':catalogLoading?'正在讀取模型…':'重新讀取模型';
    el('chat-recovery-copy').textContent=!connected?'尚未連接本機 Companion，請確認視窗仍在執行。':
      needsLogin?(state?.auth.active?'此帳戶需要重新登入；既有對話仍保留。':'登入 ChatGPT 後即可開始對話。'):
      catalogLoading?'正在確認此帳戶可用的模型。':catalogError||'尚未確認可用模型，請重新讀取。';
    const ready=!connected?'連線未確認，請稍候。':state?.auth.pending?'請在官方瀏覽器完成登入。':
      needsLogin?(state?.auth.active?'登入已失效，請重新登入此帳戶。':'尚未登入 ChatGPT'):
      catalogLoading?'正在讀取可用模型…':!model?catalogError||'模型尚未就緒，請重新讀取模型。':
      state?.busy?'正在等待模型完整回答…':model.display_name+' · 可以開始聊天';
    if(el('chat-ready').textContent!==ready)el('chat-ready').textContent=ready;
    saveStatus();
    updateContext();
    renderProjectBinding();
  }
  function clearSources() {
    window.NexusConversation?.clearConsent();
    if(el('work-chat-context'))el('work-chat-context').hidden=true;
    el('work-chat-preview')?.replaceChildren();
    clearDocumentConsent();
    sourceVersion++;
    for(const input of el('chat-sources').querySelectorAll('input'))input.checked=false;
    preview=null;el('chat-source-preview').replaceChildren();el('chat-preview-notice').textContent='';updateSend();
  }
  function clearDocumentConsent() {
    const old=documentSource;documentSource=null;el('document-chat-context').hidden=true;
    for(const id of ['document-chat-name','document-chat-scope','document-chat-content'])el(id).textContent='';
    if(old)void api('resource-source-cancel',{workspace:old.workspace,key:old.source.key}).catch(()=>{});
  }
  function attachDocument(record) {
    if(record.account!==state?.auth.active||state.auth.pending||record.workspace!==workspace||record.chat!==(selected||null))throw Error('目前對話或帳戶已變更，請返回文件重新確認。');
    documentSource=record;sourceVersion++;
    const r=record.source;preview={[r.key]:r.sha256};
    el('document-chat-name').textContent='本次討論 · '+r.name;
    el('document-chat-scope').textContent=(r.scope==='name'?'僅名稱 · 未提供內文':'節錄 · 原文件 L'+r.start_line+'–L'+r.end_line)+' · 版本 '+r.version.slice(0,12);
    el('document-chat-content').textContent=r.text;el('document-chat-context').hidden=false;
    updateSend();
  }
  function sourceView(records,parent) {
    parent.replaceChildren();
    for(const r of records) {
      const section=document.createElement('section');section.className='chat-source-record';
      section.append(text('h3','['+r.id+'] '+r.name),text('p',r.captured_at+' · SHA-256 '+r.sha256));
      if(r.scope){
        section.append(text('p',(r.scope==='name'?'僅名稱，沒有文件內文':'原文件節錄 L'+r.start_line+'–L'+r.end_line)+' · 文件版本 '+r.version));
        const back=text('button','返回來源文件 · 重新核對目前版本');back.type='button';back.className='text-button';
        back.onclick=()=>{el('chat-source-dialog').close();window.nexusReturnDocument?.(r);};section.append(back);
      }
      const content=text('pre',r.text.split('\n').map((line,i)=>'L'+(i+1)+': '+line).join('\n'));
      content.className='chat-source-text';section.append(content);parent.append(section);
    }
  }
  function openAux(id,focus) {
    if(window.NexusConversation?.openExisting(id,focus))return;
    el(id).showModal();
    if(focus)el(focus).focus();
  }
  function fitInput() {
    if(window.NexusConversation?.fitInput())return;
    const input=el('chat-question');input.style.height='auto';
    input.style.height=Math.min(input.scrollHeight,Math.max(60,Math.min(150,innerHeight*.2)))+'px';
  }
  const draftKey=(id=selected)=>JSON.stringify([state?.auth.active||'',id]);
  const visibleChat=id=>!id||state?.chats.some(c=>c.id===id&&(!c.account||c.account===state.auth.active));
  function selectedChanged(replace=false){window.dispatchEvent(new CustomEvent('companion-chat-selected',{detail:{id:selected,replace}}));void readProjectLink(true);}
  function continuityValue() {
    const owner=state?.auth.active;
    return {selected:visibleChat(selected)?selected:'',drafts:[...drafts].filter(([key,value])=>{
      try{const [account,id]=JSON.parse(key);return account===owner&&visibleChat(id)&&!!value.length;}catch{return false;}
    }),positions:[...positions].filter(([id])=>visibleChat(id)).slice(-256),preferences:{
      material:window.companionMaterialPreferences?.()||{theme:'obsidian',motion:'auto',quality:'high'},
      sidebar:window.companionSidebarPreference?window.companionSidebarPreference():continuityPreferences?.sidebar??null,
      window:{mode:windowMode,window:windowRect,mini:miniRect}}};
  }
  function writeTab() {
    if(window.nexusComparisonLayout)return;
    if(!sessionKey||!sessionReady)return;
    const value=continuityValue();if(state?.continuity)delete value.drafts;
    try{sessionStorage.setItem(sessionKey,JSON.stringify({...value,returnWork,
      continuityRevision,continuityDirty:continuityPending}));sessionSaved=true;}catch{sessionSaved=false;}
  }
  function saveStatus() {
    const node=el('chat-save-status'),hasDraft=!!el('chat-question').value.length;
    if(window.nexusComparisonLayout){
      node.dataset.state='saved';node.textContent='UX-02 版面比較：草稿與版面偏好不回存，不會覆蓋新版。';
      el('chat-save-retry').hidden=true;el('chat-save-recover').hidden=true;
      return;
    }
    node.dataset.state=continuityError?'error':continuityPending||continuitySaving?'saving':'saved';
    const message=!state?.continuity?(hasDraft?'草稿僅保留於此分頁。':''):
      !state.auth.active||state.auth.pending?'':continuityLoading?'正在讀取本機接續資料…':
      continuityError||(!continuityReady?'本機保存尚未確認；草稿暫留於此分頁。':
      continuityPending||continuitySaving?'正在加密保存於本機…':!continuityRevision?'等待第一次本機保存…':
      hasDraft?'草稿已加密保存於本機。':'對話位置與偏好已保存於本機。');
    if(node.textContent!==message)node.textContent=message;
    el('chat-save-recover').hidden=!continuityError;
    el('chat-save-retry').hidden=!continuityError;
    if(continuityReady)el('preference-storage').textContent=continuityError?'本機保存尚未確認':
      continuityPending||continuitySaving?'偏好正在加密保存於本機':'偏好已加密保存於本機';
    window.dispatchEvent(new Event('companion-continuity'));
  }
  function restorePreferences(value) {
    if(!value)return;
    continuityPreferences=value;
    window.companionRestoreMaterial?.(value.material);window.companionRestoreSidebar?.(value.sidebar);
    if(value.window&&windowModes.includes(value.window.mode)){
      windowMode=value.window.mode;windowRect=value.window.window;miniRect=value.window.mini;
      saveWindow(false);layoutWindow();
    }
  }
  async function restoreContinuity() {
    if(!workEnabled||!state?.continuity||!workspace||!state.auth.active||state.auth.pending||authChanging||continuityReady||continuityError)return;
    if(continuityLoading)return continuityLoading;
    const account=state.auth.active,root=workspace,mine=continuityGeneration;
    continuityLoading=(async()=>{
      try{
        const record=await api('continuity-get',{account,workspace:root});
        if(mine!==continuityGeneration||account!==state?.auth.active||root!==workspace||state.auth.pending)return;
        if(record.account!==account||record.workspace!==root)throw Error('接續資料身分未確認。');
        const key='companion.nexus.chat.v1:'+JSON.stringify([root,account]);let tab=null;
        try{tab=JSON.parse(sessionStorage.getItem(key)||'null');}catch{}
        // Same-tab navigation metadata is separate from encrypted draft text.
        // It restores the work chip only; sharing still rechecks the origin
        // and requires the user's explicit result selection and preview.
        const ref=tab?.returnWork;
        const returnReference=ref&&typeof ref.task==='string'&&ref.task.length<=128&&typeof ref.chat==='string'&&visibleChat(ref.chat)?
          {task:ref.task,chat:ref.chat,top:Number.isFinite(ref.top)?Math.max(0,Math.min(10_000_000,ref.top)):0,linked:ref.linked===true}:null;
        // Only migrate the old tab-only format once. New draft content lives
        // in memory and DPAPI, never in browser session/local storage.
        if(!Array.isArray(tab?.drafts))tab=null;
        continuityRevision=record.revision;continuitySerial=JSON.stringify(record.value);
        if(record.value&&(!tab||(!tab.continuityDirty&&tab.continuityRevision!==record.revision)))tab={...record.value,returnWork:returnReference?.chat===record.value.selected?returnReference:null};
        if(tab?.continuityDirty&&Number.isInteger(tab.continuityRevision)&&tab.continuityRevision!==record.revision){
          continuityError='另一個視窗已保存較新的版本；本分頁草稿仍保留，請核對已保存版本。';
          continuityRevision=tab.continuityRevision;
        }
        continuityRestored=tab;restorePreferences(tab?.preferences);continuityReady=true;
      }catch(e){if(mine===continuityGeneration)continuityError=e.message;}
      finally{if(mine===continuityGeneration){continuityLoading=false;restoreSession();updateSend();
        if(inChat())void read().catch(e=>notice(e.message));}}
    })();
    return continuityLoading;
  }
  async function flushContinuity(keepalive=false) {
    if(window.nexusComparisonLayout)return true;
    clearTimeout(continuityTimer);
    if(continuitySaving){await continuitySaving;return continuityPending&&!continuityError?flushContinuity(keepalive):!continuityPending;}
    if(!continuityReady||!state?.continuity||state.auth.pending||authChanging||continuityError)return false;
    const value=continuityValue(),serial=JSON.stringify(value);
    if(serial===continuitySerial){continuityPending=false;writeTab();saveStatus();return true;}
    const account=state.auth.active,root=workspace,mine=continuityGeneration,revision=continuityRevision;
    continuityPending=true;
    continuitySaving=(async()=>{
      try{
        const record=await api('continuity-save',{account,workspace:root,revision,value},
          {keepalive:keepalive&&new TextEncoder().encode(serial).length<60000});
        if(mine!==continuityGeneration||account!==state?.auth.active||root!==workspace||state.auth.pending)return;
        if(record.account!==account||record.workspace!==root||record.revision!==revision+1)throw Error('本機保存回執未確認。');
        continuityRevision=record.revision;continuitySerial=serial;
        continuityPending=JSON.stringify(continuityValue())!==serial;
      }catch(e){if(mine===continuityGeneration)continuityError=e.message;}
      finally{if(mine===continuityGeneration){continuitySaving=null;writeTab();saveStatus();
        if(continuityPending&&!continuityError)continuityTimer=setTimeout(()=>void flushContinuity(),150);}}
    })();
    saveStatus();await continuitySaving;return !continuityPending&&!continuityError;
  }
  function persistChat() {
    if(window.nexusComparisonLayout)return;
    if(!workEnabled||!sessionReady||!sessionKey)return;
    if(inChat()&&renderedChat===selected)positions.set(selected,el('chat-messages').scrollTop);
    if(state?.continuity&&continuityReady){
      continuityPending=JSON.stringify(continuityValue())!==continuitySerial;clearTimeout(continuityTimer);
      if(continuityPending&&!continuityError&&!authChanging)continuityTimer=setTimeout(()=>void flushContinuity(),350);
    }
    writeTab();saveStatus();
  }
  function saveDraft() {drafts.set(draftKey(),el('chat-question').value);persistChat();}
  function restoreSession() {
    if(!workEnabled||sessionReady||!workspace||!state||continuityLoading)return;
    sessionKey='companion.nexus.chat.v1:'+JSON.stringify([workspace,state.auth.active||'']);
    try{
      const saved=continuityRestored||JSON.parse(sessionStorage.getItem(sessionKey)||'null');
      if(saved){
        for(const [key,value] of saved.drafts||[])if(typeof value==='string')drafts.set(key,value.slice(0,4000));
        for(const [id,value] of saved.positions||[])if(Number.isFinite(value))positions.set(id,Math.max(0,value));
        if(requestedChat===null)requestedChat=saved.selected||'';
        if(saved.returnWork&&typeof saved.returnWork.task==='string'&&typeof saved.returnWork.chat==='string')returnWork=saved.returnWork;
      }
    }catch{}
    sessionReady=true;
    const next=requestedChat??selected;requestedChat=null;
    selected=visibleChat(next)?next:'';rendered='';renderedChat=null;
    el('chat-history').value=selected;
    if(returnWork?.chat!==selected)returnWork=null;
    el('chat-question').value=drafts.get(draftKey())||'';fitInput();selectedChanged(true);
    persistChat();
  }
  function switchConversation(next,replace=false) {
    window.NexusConversation?.resetContext();
    dismissProposal();
    window.NexusOrganize?.reset();
    if(sending)return;
    ++contextEpoch;
    if(!visibleChat(next)){next='';notice('此對話不在目前帳戶可選取的紀錄中。');}
    saveDraft();if(inChat()&&renderedChat===selected)positions.set(selected,el('chat-messages').scrollTop);
    selected=next;el('chat-history').value=next;el('chat-question').value=drafts.get(draftKey(next))||'';
    if(returnWork?.chat!==selected)returnWork=null;
    rendered='';renderedChat=null;el('chat-messages').replaceChildren(text('p','正在讀取選定對話…'));
    notice('');clearSources();read().catch(e=>notice(e.message));fitInput();el('chat-question').focus();
    saveDraft();selectedChanged(replace);
  }
  function showSpace(next,focus=true) {
    if(floating)closeFloating(false);
    if(workEnabled&&next!==document.body.dataset.space)clearSources();
    if(next==='chat'&&!inChat())workScroll=scrollY;
    document.body.dataset.space=next;
    el('chat-space').hidden=next!=='chat';el('work-space').hidden=next!=='work';
    el('open-chat').setAttribute('aria-pressed',String(next==='chat'));
    el('open-workspace').setAttribute('aria-pressed',String(next==='work'));
    el('skip-main').href=next==='chat'?'#chat-question':'#task-title';
    el('skip-main').textContent=next==='chat'?'跳至訊息輸入':'跳至目前工作';
    if(next==='chat') {fitInput();if(focus)el('chat-question').focus({preventScroll:true});refresh();}
    else {scrollTo(0,workScroll);if(focus)el('task-title').focus({preventScroll:true});}
    window.dispatchEvent(new CustomEvent('companion-space',{detail:next}));
  }
  async function read() {
    const mine=++epoch,id=selected,account=state?.auth.active,scroller=el('chat-messages');
    if(!id) {
      if(renderedChat!==''||rendered!=='empty'){
        const empty=text('div','');empty.className='chat-empty';
        empty.append(text('span','A LITTLE ROOM TO THINK'),text('h2','從你想聊的開始。'),text('p','一個想法、一個問題，或只是聊聊今天。'));
        scroller.replaceChildren(empty);rendered='empty';renderedChat='';
      }
      return;
    }
    const conversation=await api('get',{chat:id});
    const proposals=workEnabled?await api('work-state',{chat:id}):[];
    if(mine!==epoch||id!==selected||authChanging||account!==state?.auth.active||state?.auth.pending)return;
    const organizations=organizeEnabled?await api('organize-state',{chat:id}):[];
    if(mine!==epoch||id!==selected||authChanging||account!==state?.auth.active||state?.auth.pending)return;
    await Promise.all(proposals.filter(p=>p.kind==='native_codex'&&p.result_id).map(p=>loadNativeResult(p)));
    if(mine!==epoch||id!==selected||authChanging||account!==state?.auth.active||state?.auth.pending)return;
    const pilots=window.NexusPilot?await window.NexusPilot.state(id):[];
    if(mine!==epoch||id!==selected||authChanging||account!==state?.auth.active)return;
    const signature=JSON.stringify([conversation,proposals,organizations,pilots,proposals.map(p=>nativeResults.get(nativeResultKey(p)))]);if(signature===rendered&&renderedChat===id)return;
    const same=renderedChat===id,top=scroller.scrollTop,nearEnd=scroller.scrollHeight-scroller.clientHeight-top<90;
    rendered=signature;renderedChat=id;
    const nodes=[];
    for(const turn of conversation.turns) {
      const box=document.createElement('article');box.className='chat-message';box.dataset.turn=turn.id;
      const question=text('div','');question.className='chat-user';
      question.append(text('strong','你'),text('p',turn.question));
      const answer=text('div','');answer.className='chat-answer';
      const stamp=text('p',new Date(turn.created).toLocaleString()+' · '+turn.model);stamp.className='chat-time';
      const body=text('div','');
      window.CompanionReading.markdown(body,turn.status==='complete'?turn.answer:turn.error||'正在等待模型完整回答。可以切換空間，稍後回來查看。');
      answer.append(text('strong',turn.status==='complete'?'Companion':turn.status==='pending'?'Companion · 等待回答':'未完成回答'),stamp,body);
      if(turn.sources.length) {
        for(const source of turn.sources.filter(r=>r.scope)){
          const locate=text('button','定位原文 · '+source.name+(source.scope==='excerpt'?' · 第 '+source.start_line+'–'+source.end_line+' 行':''));
          locate.type='button';locate.className='secondary-button chat-locate-source';
          locate.onclick=()=>window.nexusReturnDocument?.(source);answer.append(locate);
        }
        const refs=text('button','核對這一輪的來源快照');refs.type='button';refs.className='text-button chat-source-link';
        refs.onclick=()=>{sourceView(turn.sources,el('chat-source-records'));openAux('chat-source-dialog');};
        answer.append(refs);
      }
      if(workEnabled&&turn.status==='complete'&&!organizations.some(o=>o.turn===turn.id)) {
        const linked=proposals.find(p=>p.turn===turn.id&&p.kind==='native_codex'&&!p.parent&&p.task_id)
          ||proposals.find(p=>p.turn===turn.id&&p.kind==='native_codex'&&!p.parent);
        const propose=text('button',linked?.task_id?'查看這次診斷':linked?'繼續現有診斷草稿':'建立唯讀 Codex 診斷');
        propose.type='button';propose.className='text-button chat-source-link';
        propose.onclick=async()=>{if(propose.disabled)return;propose.disabled=true;
          try{await action(async()=>{const owner=state?.auth.active;const p=await api('work-create',{chat:id,turn:turn.id});
            if(selected!==id||state?.auth.active!==owner||state?.auth.pending||authChanging)return;
            if(p.task_id){rendered='';await read();
              if(selected===id&&state?.auth.active===owner&&!state?.auth.pending&&!authChanging){
                el('chat-messages').querySelector('[data-work="'+p.id+'"]')?.scrollIntoView?.({block:'nearest'});
                notice('這次討論已有診斷工作；已保留原身分，沒有重複啟動。');
              }
            }else{editProposal(p);rendered='';}
          });}finally{propose.disabled=false;}
        };
        answer.append(propose,text('small','聊天不會自動執行工程工作。請在提案中預覽來源，確認後才交給原生 Codex。'));
      }
      for(const p of proposals.filter(p=>p.turn===turn.id))answer.append(workCard(p));
      for(const o of organizations.filter(o=>o.turn===turn.id))answer.append(window.NexusOrganize.card(o,()=>{rendered='';void refresh();},()=>selected===id&&state?.auth.active===account&&!state?.auth.pending&&!authChanging));
      for(const pilot of pilots.filter(p=>p.turn===turn.id))answer.append(window.NexusPilot.card(pilot));
      box.append(question,answer);nodes.push(box);
    }
    scroller.replaceChildren(...nodes);
    const last=conversation.turns.at(-1);
    if(!same)scroller.scrollTop=positions.get(id)??(nodes.at(-1)?.offsetTop||0);
    else if(last?.status==='pending'&&nearEnd)scroller.scrollTop=scroller.scrollHeight;
    else scroller.scrollTop=top; // A long completed answer grows below the reader, never yanks them to its end.
    if(last)notice(last.status==='complete'?(last.sources.some(s=>s.scope)?'回答與當時的來源已保存。追問可沿用對話；核對文件目前內容時，請重新選取與預覽。':'回答已保存，可以繼續聊。'):last.status==='pending'?'正在等待模型完整回答…':last.error||'未取得完整回答，可重新提問。');
  }
  function invalidateAccount(account) {
    window.NexusConversation?.resetContext();
    dismissProposal();nativeResults.clear();nativeLoading.clear();
    window.NexusOrganize?.reset();
    ++authEpoch;
    ++continuityGeneration;clearTimeout(continuityTimer);continuityReady=false;continuityLoading=false;
    continuitySaving=null;continuityPending=false;continuityRevision=0;continuitySerial='';continuityError='';
    continuityRestored=null;continuityReview=null;continuityPreferences=null;
    if(el('chat-continuity').open)el('chat-continuity').close();el('chat-continuity-saved').textContent='';
    projectKey='';projectLink=null;projectLinkStatus='idle';++projectRead;cancelProjectPreview();
    closeFloating(false);returnWork=null;++contextEpoch;
    saveDraft();epoch++;selected='';rendered='';renderedChat=null;positions.clear();
    if(sessionKey)try{sessionStorage.removeItem(sessionKey);}catch{}
    drafts.clear();sessionKey='';sessionReady=false;requestedChat=state?.continuity?null:'';
    el('chat-messages').replaceChildren();accountChoice=account||'';catalogAttempt=null;catalogLoading=false;catalogError='';
    el('chat-source-records').replaceChildren();el('chat-question').value='';
    el('chat-history').replaceChildren(new Option('新對話',''));optionLists.delete(el('chat-history'));
    for(const id of ['work-proposal','chat-knowledge','chat-source-dialog'])if(el(id).open)el(id).close();
    proposal=null;approval=null;clearSources();el('work-origin').hidden=true;
    window.dispatchEvent(new Event('companion-continuity'));
  }
  async function changeAccount(path,body) {
    if(authChanging||authPreparing)return;
    window.NexusConversation?.resetContext();
    authPreparing=true;updateSend();saveDraft();
    if(state?.continuity&&continuityReady){
      await flushContinuity();
      if((continuityPending||continuityError)&&[...drafts.values()].some(v=>v.length)&&
          !confirm('草稿尚未確認保存。仍要變更登入並清除此分頁的草稿嗎？可取消後先複製或核對已保存版本。')){
        authPreparing=false;updateSend();return;
      }
    }
    authPreparing=false;
    authChanging=true;invalidateAccount(body.account);connected=false;updateSend();
    try{await api(path,body);}catch(e){notice(e.message);el('chat-auth-notice').textContent=e.message;}
    finally{authChanging=false;await refresh();}
  }
  async function loadModels(data) {
    if(catalogLoading||authChanging||!data?.auth.active||data.auth.pending||data.busy)return;
    const mine=authEpoch;
    catalogAttempt=data.auth.active;catalogLoading=true;catalogError='';updateSend();
    try{
      const models=await api('models',{});
      if(mine!==authEpoch||data!==state||authChanging)return;
      data.models=models;
    }catch(e){
      if(mine!==authEpoch||data!==state||authChanging)return;
      data.models=[];catalogError=e.message;notice(e.message);
    }finally{if(mine===authEpoch){catalogLoading=false;updateSend();}}
  }
  async function refresh() {
    if(loading||authChanging)return;loading=true;
    const origin=authEpoch;
    try {
      const data=await api('state');if(origin!==authEpoch||authChanging)return;connected=true;
      const accountChanged=state&&(data.auth.active!==state.auth.active||!!data.auth.pending!==!!state.auth.pending);
      if(accountChanged)invalidateAccount(data.auth.active);
      state=data;
      void restoreContinuity();if(origin!==authEpoch||authChanging)return;
      restoreSession();
      if(accountChanged){el('chat-question').value=drafts.get(draftKey())||'';fitInput();}
      if(accountChoice===undefined)accountChoice=data.auth.active||'';
      options(el('chat-accounts'),data.auth.accounts,accountChoice,'新增帳戶');
      el('chat-auth-notice').textContent=data.auth.notice;
      options(el('chat-history'),data.chats.filter(c=>!c.account||c.account===data.auth.active).map(c=>({id:c.id,label:c.title})),selected,'新對話');
      void readProjectLink();
      if(selected&&!visibleChat(selected)){switchConversation('',true);returnWork=null;}
      if(inChat()&&data.auth.active&&!data.auth.pending&&!data.busy&&!data.models.length&&catalogAttempt!==data.auth.active&&
          data.auth.accounts.find(a=>a.id===data.auth.active)?.signed_in!==false){
        await loadModels(data);
        if(data!==state||authChanging)return;
      }
      const current=el('chat-model').value;
      const model=(data.models.some(m=>m.slug===current)?current:'')||data.models.find(m=>m.slug==='gpt-6.1-sol')?.slug||data.models[0]?.slug||'';
      options(el('chat-model'),data.models.map(m=>({id:m.slug,label:m.display_name})),model,'選擇模型');
      if(!el('chat-sources').children.length)for(const source of data.sources){
        const label=document.createElement('label'),input=document.createElement('input');
        input.type='checkbox';input.value=source.id;input.checked=false;
        label.append(input,document.createTextNode(source.label));el('chat-sources').append(label);
      }
      updateSend();
      for(const id of ['chat-login','chat-logout','chat-accounts','chat-models-refresh'])el(id).disabled=!!data.busy||data.auth.pending||catalogLoading;
      if(inChat())await read();
    }catch(e){connected=false;updateSend();notice(e.message);}finally{loading=false;}
  }
  async function action(work){try{await work();await refresh();}catch(e){notice(e.message);el('chat-auth-notice').textContent=e.message;}}
  function workCard(p) {
    const card=text('section','');card.className='chat-work-card';card.dataset.work=p.id;card.dataset.task=p.task_id||'';card.dataset.state=p.state;
    if(p.kind==='native_codex'&&p.draft_hidden&&p.can_hide_draft&&!p.task_id){
      const folded=text('details',''),restore=text('button','展開並繼續草稿');
      folded.append(text('summary','已收起的未執行草稿 · '+p.goal));
      restore.type='button';restore.className='secondary-button';
      restore.onclick=async()=>{const owner=state?.auth.active;restore.disabled=true;
        try{const draft=await api('work-draft-visibility',{id:p.id,hidden:false});
          if(selected===p.chat&&state?.auth.active===owner&&!state?.auth.pending&&!authChanging){
            editProposal(draft);rendered='';await refresh();
          }
        }catch(e){if(selected===p.chat&&state?.auth.active===owner)notice(e.message);}
        finally{restore.disabled=false;}
      };
      folded.append(restore);card.append(folded);return card;
    }
    const names={AWAITING_AUTHORIZATION:'等待你的授權',CREATED:'準備中',RUNNING:'執行中',CANCEL_REQUESTED:'停止待確認',CANCELLED:'已取消',FAILED:'執行失敗／中斷',RESULT_PENDING_REVIEW:'執行完成 · 等待審查',ACCEPTED:'人類已接受成果',REJECTED:'人類已拒絕成果',REVISION_REQUESTED:'已記錄調整方向'};
    card.append(text('strong',names[p.state]||'狀態未確認'),text('p',p.goal));
    const details=text('details','');details.append(text('summary','技術與驗收資訊'),text('small',p.state+' · '+p.technical_acceptance));card.append(details);
    const button=text('button',p.task_id?'查看工作與證據':p.kind==='native_codex'?'設定並預覽診斷':'編輯提案與確認範圍');button.className='secondary-button';button.type='button';
    button.onclick=()=>p.task_id?action(async()=>{workOrigin=p;if(window.nexusOpenWork)await window.nexusOpenWork(p.task_id);else{showSpace('work');await window.openCompanionWork(p.task_id);}}):editProposal(p);
    if(p.kind==='native_codex'&&p.task_id)details.append(button);else card.append(button);

    if(p.kind==='native_codex'){
      details.append(text('p','原生 Codex · '+p.review_status+' · '+p.capability));
      card.append(text('p',p.result_id?'唯讀診斷已完成，尚待獨立技術審查。':p.task_id?'進度會在這裡更新，不需要切換頁面。':'先核對來源，再由你確認開始。'));
      if(!p.task_id)card.append(text('p','設定目標與來源 → 預覽 → 確認 READ_ONLY 後啟動。'));
      if(p.failure_summary){
        const failure=text('p',(p.failure_stage||'啟動檢查')+' · '+p.failure_summary
          +(p.failure_code!==null&&p.failure_code!==undefined?'（RPC '+p.failure_code+'）':''));
        failure.setAttribute('role','status');card.append(failure);
        card.append(text('small',p.start_outcome==='REJECTED'?'Codex 明確拒絕啟動；沒有自動重送。':
          p.start_outcome==='NOT_SENT'?'診斷尚未送出，前置階段已停止。':
          '請求可能已送出，不能推定未執行；請保留工作並對帳。'));
      }
      if(p.parent)card.append(text('small','本次為一次後續診斷；保留同一 thread 的先前已授權內容。'));
      const evidence=text('details','');
      evidence.append(text('summary','工作身分與實際事件'),text('p','Thread: '+(p.thread_id||'尚未取得')+' / Turn: '+(p.turn_id||'尚未取得')),
        text('p','來源指紋: '+(p.candidate_id||'尚未預覽')));
      for(const e of p.events||[])evidence.append(text('p',e.at+' · '+({connecting:'正在連接原生 Codex',session_bound:'原生 thread 已回傳',
        turn_bound:'原生 turn 已回傳',receiving_result:'收到模型內容事件',cancel_requested:'已請求停止，等待終態',
        completed:'執行完成',failed:'執行失敗',cancelled:'已確認停止',unknown:'終態未確認',reconciled:'已嘗試核對原生紀錄'}[e.kind]||'事件')));
      card.append(evidence);
      const feedback=text('p',reconcileFeedback.get(p.id)||'');
      feedback.setAttribute('role','status');feedback.setAttribute('aria-live','polite');
      feedback.hidden=!feedback.textContent;card.append(feedback);
      const showFeedback=message=>{reconcileFeedback.set(p.id,message);feedback.textContent=message;feedback.hidden=false;};
      const owner=state?.auth.active,chatId=p.chat;
      const current=()=>selected===chatId&&state?.auth.active===owner&&!state?.auth.pending&&!authChanging;
      const control=(label,operation,explain)=>{
        const b=text('button',label);b.type='button';b.className='secondary-button';
        b.onclick=async()=>{b.disabled=true;try{
          const response=await operation();if(current()){
            if(explain)showFeedback(explain(response));
            rendered='';await refresh();
          }
        }catch(e){if(current()){
          if(explain)showFeedback('對帳請求未完成：'+e.message+'。此工作沒有重新執行。');
          else notice(e.message);
        }}finally{b.disabled=false;}};
        card.append(b);return b;
      };
      if(p.can_hide_draft&&!p.task_id)control('收起未執行草稿',()=>api('work-draft-visibility',{id:p.id,hidden:true}));
      if(['RUNNING','CANCEL_REQUESTED'].includes(p.state)){
        const stop=control('停止這項診斷',()=>api('work-stop',{id:p.id}));
        stop.disabled=p.state==='CANCEL_REQUESTED';
      }
      if(p.task_id&&p.state==='UNKNOWN')control('讀取原生狀態對帳',()=>api('work-reconcile',{id:p.id}),r=>{
        if(r?.result_id)return '已找到保存成果；請使用「查看工作與證據」核對。';
        if(r?.state==='UNKNOWN')return !r.thread_id||!r.turn_id
          ? '已嘗試對帳，但缺少完整的 Codex thread／turn 身分，仍無法確認結果。沒有重新執行工作。'
          : '已嘗試讀取 Codex 紀錄，仍無可信終態。狀態保持未確認，沒有重新執行工作。';
        if(r?.state==='FAILED')return '原生紀錄顯示執行失敗；請查看工作與證據。';
        if(r?.state==='CANCELLED')return '原生紀錄確認工作已取消。';
        return '已回傳工作狀態：'+(r?.state||'未確認')+'。請查看工作與證據。';
      });
      if(p.result_id){
        const cached=nativeResults.get(nativeResultKey(p));
        if(cached?.data)renderNativeResult(card,cached.data);
        else card.append(text('p',cached?.error||'正在讀取已保存的診斷結果，不會重新執行。'));
        const reload=control('在此讀取診斷結果',async()=>{await loadNativeResult(p,true);});
        details.append(reload);
      }
      if(p.can_revise){
        const section=text('details',''),feedback=document.createElement('textarea'),revise=text('button','預覽一次後續修正');
        section.append(text('summary','接續一次診斷修正'));
        feedback.maxLength=4000;feedback.setAttribute('aria-label','後續診斷修正內容');
        revise.type='button';revise.className='secondary-button';
        revise.onclick=async()=>{if(!feedback.value.trim())return;revise.disabled=true;
          try{const child=await api('work-revise',{id:p.id,feedback:feedback.value});if(current()){editProposal(child);rendered='';await refresh();}}
          catch(e){if(current())notice(e.message);}finally{revise.disabled=false;}};
        section.append(feedback,revise);card.append(section);
      }
    }
    if(p.result_id){
      const back=text('button',p.kind==='native_codex'?'用這份診斷接著聊':'加入成果，繼續討論');back.className='text-button';back.type='button';
      back.onclick=()=>attachResult(p);card.append(back);
    }
    window.NexusConversation?.workCard(card,p);
    return card;
  }
  function nativeResultKey(p,owner=state?.auth.active){return JSON.stringify([owner,workspace,p.chat,p.id,p.result_id]);}
  async function loadNativeResult(p,retry=false){
    const owner=state?.auth.active,root=workspace,key=nativeResultKey(p,owner);
    const current=()=>selected===p.chat&&state?.auth.active===owner&&workspace===root&&!state?.auth.pending&&!authChanging;
    if(!current())return;
    if(nativeLoading.has(key))return nativeLoading.get(key);
    if(!retry&&nativeResults.has(key))return;
    const pending=(async()=>{
      try{
        const result=await api('work-result',{id:p.id});
        if(!current())return;
        if(result.task_id!==p.task_id||result.result_id!==p.result_id||typeof result.result!=='string')throw Error('保存結果身分未確認，請重新讀取。');
        nativeResults.set(key,{data:result});
      }catch(e){if(current())nativeResults.set(key,{error:'保存結果暫時無法讀取：'+e.message});}
      finally{nativeLoading.delete(key);}
    })();
    nativeLoading.set(key,pending);return pending;
  }
  function renderNativeResult(card,result){
    if(window.NexusConversation?.diagnosis(card,result))return;
    const summary=text('div','');summary.className='native-result-summary';
    const view=result.presentation||{overview:result.result.slice(0,600)};
    for(const [key,label] of [['overview','診斷結論'],['evidence','程式碼依據'],['next_steps','建議下一步']]){
      if(!view[key])continue;
      const section=text('section',''),body=text('div','');
      section.append(text('h4',label));window.CompanionReading.markdown(body,view[key]);section.append(body);summary.append(section);
    }
    card.append(summary);
    const full=text('details',''),raw=text('pre',result.result);full.className='native-full-result';raw.dataset.nativeResult='true';
    full.append(text('summary','完整診斷、限制與原始證據'),raw);card.append(full);
  }
  function dismissProposal(){
    window.NexusConversation?.proposalClosed();
    proposal=null;proposalOwner=null;approval=null;proposalVersion++;
    if(el('work-proposal'))el('work-proposal').hidden=true;
  }
  function proposalCurrent(){return !!proposal&&selected===proposal.chat&&state?.auth.active===proposalOwner&&!state?.auth.pending&&!authChanging;}
  function editProposal(p) {
    if(selected!==p.chat||state?.auth.pending||authChanging)return;
    window.NexusOrganize?.reset();
    proposal=p;proposalOwner=state?.auth.active;proposalVersion++;approval=null;el('work-goal').value=p.goal;el('work-expected').value=p.expected;
    el('work-scope').textContent=p.workspace+' · '+p.capability;
    el('work-files').replaceChildren(text('legend','允許讀取的程式檔案'));
    const choices=p.source_choices||['daily','chat','surface','core','runtime','review','work'].map(key=>({key,name:'src/companion_core/'+key+'.py'}));
    for(const {key,name} of choices){
      const label=text('label',''),input=document.createElement('input');input.type='checkbox';input.value=key;input.checked=p.selection.includes(key);
      label.append(input,document.createTextNode(name));el('work-files').append(label);
    }
    el('work-manifest').replaceChildren();el('work-notice').textContent='尚未開始。請先預覽這次選定的來源。';el('work-confirm').disabled=true;
    el('work-preview').disabled=false;el('work-proposal').hidden=false;el('work-settings').open=false;
    if(!window.NexusConversation?.proposalOpened())el('work-proposal').scrollIntoView({block:'nearest'});
  }
  function invalidateWork(){approval=null;proposalVersion++;el('work-confirm').disabled=true;el('work-manifest').replaceChildren();el('work-notice').textContent='內容已調整，請重新預覽來源。';}
  for(const id of ['work-goal','work-expected','work-files'])el(id).addEventListener('input',invalidateWork);
  el('work-close').onclick=dismissProposal;
  el('work-preview').onclick=async()=>{
    if(!proposalCurrent()||el('work-preview').disabled)return;
    el('work-preview').disabled=true;const origin=proposal.id,mine=++proposalVersion;approval=null;el('work-confirm').disabled=true;
    const body={id:origin,goal:el('work-goal').value,expected:el('work-expected').value,selection:[...el('work-files').querySelectorAll('input:checked')].map(n=>n.value)};
    try{
      const p=await api('work-preview',body);
      if(!proposalCurrent()||proposal.id!==origin||mine!==proposalVersion||el('work-goal').value!==body.goal||el('work-expected').value!==body.expected||JSON.stringify([...el('work-files').querySelectorAll('input:checked')].map(n=>n.value))!==JSON.stringify(body.selection))return;
      el('work-manifest').replaceChildren(text('p','本次只分享 '+p.manifest.length+' 份來源快照：'));
      for(const r of p.manifest){
        const source=text('details','');source.append(text('summary',r.name+' · '+r.bytes+' bytes'));
        const snapshot=p.source_snapshots?.find(s=>s.key===r.key&&s.sha256===r.sha256);
        if(snapshot){const content=text('pre',snapshot.text.split('\n').map((line,i)=>'L'+(i+1)+': '+line).join('\n'));content.className='chat-source-text';source.append(content);}
        source.append(text('small','SHA-256 '+r.sha256));el('work-manifest').append(source);
      }
      window.NexusConversation?.previewSources(p);
      approval=p.approval;el('work-confirm').disabled=false;
      el('work-notice').textContent='可展開核對程式碼。按確認才送出上述快照做唯讀診斷；來源變更會要求重新預覽。';rendered='';
    }catch(e){if(proposalCurrent()&&mine===proposalVersion)el('work-notice').textContent=e.message;}
    finally{if(proposalCurrent()&&proposal.id===origin)el('work-preview').disabled=false;}
  };
  el('work-confirm').onclick=async()=>{
    if(!proposalCurrent()||!approval||el('work-confirm').disabled)return;
    const ident=proposal.id,ticket=approval,mine=proposalVersion;approval=null;el('work-confirm').disabled=true;
    try{
      await api('work-confirm',{id:ident,approval:ticket,authority:'READ_ONLY'});
      if(!proposalCurrent()||proposal.id!==ident||mine!==proposalVersion)return;
      dismissProposal();rendered='';await refresh();
    }catch(e){if(proposalCurrent()&&proposal.id===ident)el('work-notice').textContent=e.message+' 請重新核對來源；不會自動重送。';}
  };
  async function attachResult(p){
    if(selected!==p.chat||state?.auth.pending||authChanging)return;
    const owner=state?.auth.active;
    clearSources();for(const n of el('chat-sources').querySelectorAll('[data-work-source]'))n.remove();
    const mine=sourceVersion,key='work:'+p.id;
    const label=text('label',''),input=document.createElement('input');label.dataset.workSource='true';input.type='checkbox';input.value=key;input.checked=true;
    label.append(input,document.createTextNode('已保存工作成果：'+p.goal));el('chat-sources').append(label);updateSend();
    try{
      const records=await api('preview',{sources:[key],chat:p.chat});
      if(selected!==p.chat||state?.auth.active!==owner||state?.auth.pending||authChanging||mine!==sourceVersion)return;
      if(records.length!==1||records[0].key!==key||typeof records[0].text!=='string')throw Error('成果來源身分無法確認。');
      preview={[key]:records[0].sha256};el('work-chat-name').textContent='接著討論：'+p.goal;
      el('work-chat-preview').textContent=records[0].text;el('work-chat-context').hidden=false;
      if(!el('chat-question').value.trim())el('chat-question').value='請根據這份診斷，說明最值得先處理的下一步與理由。';
      fitInput();saveDraft();updateSend();el('chat-question').focus();
    }catch(e){if(selected===p.chat&&state?.auth.active===owner&&mine===sourceVersion){clearSources();notice(e.message);}}
  }
  el('work-chat-clear').onclick=clearSources;
  el('work-origin').onclick=async()=>{
    try{
      const id=window.surfaceInspection().selected,account=state?.auth.active;
      const origin=await api('work-origin',{task_id:id});
      if(window.surfaceInspection().selected!==id||state?.auth.active!==account||document.body.dataset.space!=='work')return;
      workOrigin=origin;if(selected!==origin.chat)switchConversation(origin.chat);showSpace('chat');
    }catch(e){el('work-origin').textContent=e.message;}
  };
  el('open-chat').onclick=()=>showSpace('chat');
  el('open-workspace').onclick=()=>showSpace('work');
  el('chat-settings-open').onclick=()=>openAux('chat-settings');
  el('chat-signin-open').onclick=()=>openAux('chat-settings','chat-login');
  el('chat-source-open').onclick=()=>openAux('chat-knowledge');
  el('chat-login').onclick=()=>changeAccount('login',{account:el('chat-accounts').value||null});
  el('chat-logout').onclick=()=>changeAccount('logout',{});
  el('chat-accounts').onchange=()=>{accountChoice=el('chat-accounts').value;if(accountChoice)changeAccount('select',{account:accountChoice});};
  el('chat-models-refresh').onclick=async()=>{await loadModels(state);await refresh();};
  el('chat-recover').onclick=async()=>{if(connected)await loadModels(state);await refresh();};
  el('chat-model').onchange=updateSend;
  el('chat-history').onchange=()=>switchConversation(el('chat-history').value);
  el('chat-new').onclick=()=>switchConversation('');
  el('project-chat-link').onclick=()=>previewProjectLink('link');
  el('project-chat-unlink').onclick=()=>previewProjectLink('unlink');
  el('project-confirm').addEventListener('close',()=>{projectConfirm=null;});
  el('project-confirm-save').onclick=async()=>{
    const p=projectConfirm;if(!p||p.chat!==selected||p.account!==state?.auth.active||p.epoch!==contextEpoch)return;
    el('project-confirm-save').disabled=true;
    try {
      const value=await api('project-confirm',{chat:p.chat,action:p.action,approval:p.approval});
      if(projectConfirm!==p||selected!==p.chat||state.auth.active!==p.account)return;
      projectLink=value;projectLinkStatus='ready';cancelProjectPreview();renderProjectBinding();notice('專案關聯已保存；沒有分享資料或呼叫模型。');
    }catch(e){el('project-confirm-notice').textContent=e.message+' 請取消後重新檢查關聯。';projectKey='';}
  };
  el('chat-messages').onscroll=()=>{if(inChat()&&renderedChat===selected){positions.set(selected,el('chat-messages').scrollTop);persistChat();}};
  el('chat-question').oninput=()=>{saveDraft();fitInput();};
  el('chat-question').onkeydown=e=>{
    if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)&&!e.isComposing){
      e.preventDefault();
      if(window.NexusOrganize?.active()){if(!el('organize-start').disabled)void window.NexusOrganize.submit();}
      else if(!el('chat-send').disabled)el('chat-form').requestSubmit();
    }
  };
  el('chat-sources').onchange=()=>{
    clearDocumentConsent();
    sourceVersion++;preview=null;el('chat-source-preview').replaceChildren();updateSend();
    el('chat-preview-notice').textContent=chosen().length?'請先預覽這則訊息要加入的資料。':'這則訊息不會加入專案資料。';
  };
  el('chat-clear-sources').onclick=clearSources;
  el('chat-preview').onclick=async()=>{
    const version=sourceVersion,selection=chosen();
    el('chat-preview').disabled=true;
    try{
      const records=await api('preview',{sources:selection,...(selection.some(k=>k.startsWith('work:')||k.startsWith('document:'))?{chat:selected||null}:{})});
      if(version!==sourceVersion)return;
      sourceView(records,el('chat-source-preview'));preview=Object.fromEntries(records.map(r=>[r.key,r.sha256]));
      el('chat-preview-notice').textContent='已預覽。返回對話後，按「傳送訊息」才會分享這些資料。';
    }catch(e){el('chat-preview-notice').textContent=e.message;}finally{updateSend();}
  };
  if(el('organize-open'))el('organize-open').onclick=()=>{
    const account=state?.auth.active,origin=selected;
    window.NexusOrganize.open({account,workspace,chat:origin||null,
      valid:()=>state?.auth.active===account&&!state?.auth.pending&&!authChanging&&selected===origin,
      started:async result=>{if(state?.auth.active!==account||authChanging)return;
        drafts.delete(draftKey(origin));el('chat-question').value='';fitInput();
        selected=result.chat;rendered='';persistChat();selectedChanged(true);await refresh();}
    });
  };
  el('chat-form').onsubmit=async event=>{
    event.preventDefault();if(window.NexusOrganize?.active()){await window.NexusOrganize.submit();return;}
    if(el('chat-send').disabled)return;
    const origin=selected,question=el('chat-question').value;
    sending=true;saveDraft();updateSend();notice('正在提交訊息…');
    try{
      const result=await api('send',{chat:origin||null,question,sources:chosen(),model:el('chat-model').value,preview});
      drafts.delete(draftKey(origin));selected=result.chat;el('chat-question').value='';clearSources();fitInput();
      if(returnWork?.chat===origin)returnWork.chat=selected;
      persistChat();selectedChanged(true);
      notice('訊息已保存，正在等待模型完整回答…');
    }catch(e){if(documentSource)clearSources();notice(e.message);}finally{sending=false;updateSend();await refresh();}
  };
  window.addEventListener('resize',()=>{endWindowGesture();fitInput();layoutWindow();});
  window.addEventListener('nexus-layout',layoutWindow);
  if(workEnabled){
    windowControl(el('companion-window-header'),false,false);windowControl(el('companion-window-resize'),false,true);
    windowControl(el('companion-mini-move'),true,false);windowControl(el('companion-mini-resize'),true,true);
  }
  el('companion-window-mode').onchange=()=>setWindowMode(el('companion-window-mode').value);
  el('companion-maximize').onclick=()=>setWindowMode(windowMode==='reading'?'floating':'reading');
  el('companion-minimize').onclick=minimizeWindow;el('companion-restore').onclick=restoreWindow;
  el('companion-mini-close').onclick=()=>closeFloating();
  document.addEventListener('keydown',event=>{
    if(event.key==='Escape'&&floating&&!document.querySelector('dialog:modal')&&
      (el('companion-panel').contains(event.target)||el('companion-mini').contains(event.target))){event.preventDefault();closeFloating();}
  });
  el('companion-ask').onclick=openFloating;
  el('companion-close').onclick=()=>closeFloating();
  el('companion-panel').addEventListener('cancel',e=>{e.preventDefault();closeFloating();});
  el('companion-panel').addEventListener('close',()=>{if(!el('companion-panel').open&&!floating?.minimized)closeFloating(false);});
  el('companion-start-new').onclick=()=>activateFloating('',false);
  el('companion-expand').onclick=()=>{if(!floating?.ready)return;const record=documentSource;documentSource=null;closeFloating(false);showSpace('chat');if(record)attachDocument(record);updateContext();};
  el('companion-return').onclick=async()=>{
    if(!returnWork)return;const context={...returnWork};saveDraft();closeFloating(false);clearSources();
    await window.nexusOpenWork(context.task);
    if(window.surfaceInspection().selected===context.task&&document.body.dataset.space==='work')scrollTo(0,context.top||0);
  };
  el('companion-share-result').onclick=async()=>{
    if(el('companion-share-result').disabled)return;
    const context={...returnWork},chat=selected,account=state?.auth.active,mine=contextEpoch;
    try{
      const p=await api('work-origin',{task_id:context.task});
      if(mine!==contextEpoch||selected!==chat||state?.auth.active!==account||returnWork?.task!==context.task)return;
      if(p.task_id!==context.task||p.chat!==chat||!p.result_id)throw Error('目前沒有可核對的已保存成果；可先普通聊天。');
      attachResult(p);
    }catch(e){notice(e.message);}
  };
  let originSelection='';
  window.addEventListener('companion-state',async event=>{
    workFacts=event.detail;
    if(floating&&!floating.document&&(floating.task!==workFacts.selected||!workFacts.tasks.some(t=>t.task_id===floating.task)))closeFloating(false);
    updateContext();
    if(event.detail.workspace&&!workspace){workspace=event.detail.workspace;await restoreContinuity();restoreSession();void readProjectLink();}
    const id=event.detail.selected,identity=JSON.stringify([id,state?.auth.active,event.detail.offline]);
    if(identity===originSelection)return;originSelection=identity;el('work-origin').hidden=true;
    window.dispatchEvent(new CustomEvent('companion-work-origin',{detail:null}));
    if(!id||event.detail.offline||!workEnabled)return;
    try{const p=await api('work-origin',{task_id:id});if(originSelection===identity){el('work-origin').textContent='返回原對話';el('work-origin').hidden=false;window.dispatchEvent(new CustomEvent('companion-work-origin',{detail:p}));}}catch{}
  });
  window.companionNavigate=showSpace;
  window.closeCompanionFloating=closeFloating;
  window.companionClearSourceConsent=()=>{++contextEpoch;cancelProjectPreview();clearSources();};
  window.companionProjectStatus=projectStatus;
  window.companionResumeStatus=()=>{
    if(!sessionReady||!state?.auth.active||state.auth.pending||authChanging||continuityLoading)return null;
    const chat=state.chats.find(c=>c.id===selected&&(!c.account||c.account===state.auth.active));
    const hasDraft=!!el('chat-question').value.trim();
    if(!chat&&!hasDraft)return null;
    return {title:chat?.title||'尚未送出的新對話',hasDraft,
      saved:!!state.continuity&&continuityReady&&continuityRevision>0&&!continuityError&&!continuityPending&&!continuitySaving,
      saving:!!state.continuity&&!!(continuityPending||continuitySaving),error:!!continuityError};
  };
  window.companionProjectContext=()=>api('project-context',{});
  window.openProjectConversation=async id=>{
    const account=state?.auth.active,mine=contextEpoch;
    const value=await api('project-get',{chat:id});
    if(state?.auth.active!==account||mine!==contextEpoch||value.account!==account||value.workspace!==workspace||!visibleChat(id))throw Error('目前無法安全開啟這段專案對話。');
    switchConversation(id);showSpace('chat');
  };
  window.companionSaveChat=saveDraft;
  window.companionChatSelection=()=>selected;
  window.openDocumentCompanion=record=>{
    // Opening a read-only context is navigation. A stale busy poll must not
    // discard its grant; updateSend and the backend still serialize sends.
    if(sending)throw Error('請等待目前訊息提交完成。');
    if(record.account!==state?.auth.active||record.workspace!==workspace||record.chat!==(selected||null)||state.auth.pending)throw Error('帳戶或對話已變更，請重新確認文件。');
    closeFloating(false);clearSources();saveDraft();++contextEpoch;returnWork=null;
    floating={document:true,account:record.account,top:scrollY,ready:true};
    windowMode='split-right';el('documents-index').open=false;
    el('companion-panel-body').append(el('chat-space'));el('companion-unlinked').hidden=true;
    el('chat-space').hidden=false;el('companion-panel').hidden=false;el('companion-panel').show();
    attachDocument(record);layoutWindow();read().catch(e=>notice(e.message));el('chat-question').focus({preventScroll:true});
  };
  el('document-chat-clear').onclick=clearSources;
  el('companion-read-document').onclick=()=>{if(floating?.document){saveDraft();floating.reading=true;layoutWindow();el('document-title').focus({preventScroll:true});}};
  el('document-chat-toggle').onclick=()=>{if(floating?.document){floating.reading=false;floating.minimized=false;if(!el('companion-panel').open)el('companion-panel').show();layoutWindow();el('chat-question').focus({preventScroll:true});}};
  window.companionLocateDocument=()=>{
    if(!floating?.document)return false;
    saveDraft();floating.reading=true;layoutWindow();return true;
  };
  el('document-chat-return').onclick=()=>{if(documentSource)window.nexusReturnDocument?.(documentSource.source);};
  window.openCompanionChat=id=>{if(sessionReady)switchConversation(id,true);else requestedChat=id;};
  window.addEventListener('companion-preferences-change',persistChat);
  window.addEventListener('companion-preferences-ready',()=>{
    if(continuityPreferences)window.companionRestoreSidebar?.(continuityPreferences.sidebar);
  });
  el('chat-save-retry').onclick=async()=>{
    const account=state?.auth.active,root=workspace,mine=continuityGeneration;
    try{
      const record=await api('continuity-get',{account,workspace:root});
      if(mine!==continuityGeneration||account!==state?.auth.active||state.auth.pending)return;
      if(record.account!==account||record.workspace!==root)throw Error('接續資料身分未確認。');
      const serial=JSON.stringify(continuityValue());
      if(JSON.stringify(record.value)===serial){
        continuityRevision=record.revision;continuitySerial=serial;continuityPending=false;continuityError='';continuityReady=true;writeTab();saveStatus();
      }else if(record.revision===continuityRevision){
        continuityError='';continuityReady=true;await flushContinuity();
      }else throw Error('另一個視窗已保存較新的版本；請先核對已保存版本。');
    }catch(e){if(mine===continuityGeneration){continuityError=e.message;saveStatus();}}
  };
  el('chat-save-recover').onclick=async()=>{
    const account=state?.auth.active,root=workspace,mine=continuityGeneration;
    try{
      const record=await api('continuity-get',{account,workspace:root});
      if(mine!==continuityGeneration||account!==state?.auth.active||state.auth.pending)return;
      if(record.account!==account||record.workspace!==root)throw Error('接續資料身分未確認。');
      continuityReview=record;
      const lines=(record.value?.drafts||[]).map(([key,value])=>{
        const id=JSON.parse(key)[1],title=state.chats.find(c=>c.id===id)?.title||'新對話';return title+'\n'+value;
      });
      el('chat-continuity-saved').textContent=lines.join('\n\n')||'尚無已保存草稿。';
      openAux('chat-continuity');
    }catch(e){continuityError=e.message;saveStatus();}
  };
  el('chat-continuity-use').onclick=()=>{
    const record=continuityReview;
    if(!record||record.account!==state?.auth.active||record.workspace!==workspace||state.auth.pending)return;
    clearTimeout(continuityTimer);continuityReady=false;closeFloating(false);clearSources();
    drafts.clear();positions.clear();sessionReady=false;rendered='';renderedChat=null;++epoch;
    continuityRevision=record.revision;continuitySerial=JSON.stringify(record.value);
    continuityError='';continuityPending=false;continuityRestored=record.value||{selected:'',drafts:[],positions:[]};
    restorePreferences(record.value?.preferences);requestedChat=record.value?.selected||'';continuityReady=true;
    restoreSession();el('chat-continuity').close();read().catch(e=>notice(e.message));updateSend();
  };
  el('chat-continuity').addEventListener('close',()=>{continuityReview=null;el('chat-continuity-saved').textContent='';});
  window.addEventListener('pagehide',()=>{saveDraft();void flushContinuity(true);});
  window.addEventListener('beforeunload',e=>{saveDraft();void flushContinuity(true);
    if([...drafts.values()].some(v=>v.length)&&(state?.continuity?
        !continuityReady||continuityPending||!!continuitySaving||!!continuityError:!sessionSaved)){e.preventDefault();e.returnValue='';}});
  el('space-nav').hidden=false;showSpace('chat',false);
  async function poll(){await refresh();setTimeout(poll,1500);}poll();
})();
