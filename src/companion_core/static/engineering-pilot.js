/* Fixed isolated sample; never reuses READ_ONLY approval or ReviewStore actions. */
(() => {
  if(document.body.dataset.pilotEnabled!=='true')return;
  const real=document.body.dataset.realGitJob==='true';
  const el=id=>document.getElementById(id), node=(tag,text='')=>{const n=document.createElement(tag);n.textContent=text;return n;};
  async function api(action,body){const r=await fetch('/api/chat/pilot-'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify(body)});const v=await r.json();if(!r.ok)throw Error(v.error||'試點未能確認。');return v;}
  window.NexusPilot={state:chat=>api('state',{chat}),card(job,onEvidence){
    const card=node('section');card.className='chat-work-card';card.dataset.pilot=job.id;card.dataset.state=job.state;
    const labels={PREVIEW:real?'請核對 Git 工程範圍':'隔離工程範例 · 請核對寫入範圍',EXPIRED:'預覽已失效',RUNNING:'Codex 正在處理隔離候選',COMPLETED:'範例修改與測試已完成',PENDING_REVIEW:'待獨立技術審查',FAILED:'未開始工程執行',UNKNOWN:'執行結果尚未確認'};
    card.append(node('h3',labels[job.state]||job.state),node('p',job.summary));
    if(job.realGit){
      const version=job.verified||job.before;
      const match=job.current?.sha256===version.sha256;
      card.append(node('p',job.project+' · 工作 '+job.id),node('p',(job.verified?'驗證版本：':'預覽版本：')+version.head+' · '+version.sha256),
        node('p',!job.current?'目前候選身分無法核對':match?'目前候選與上述版本一致':'目前候選已變：'+job.current.head+' · '+job.current.sha256));
      if(job.current?.status.length)card.append(node('pre',job.current.status.join('\n')));
    }
    if(job.state==='PREVIEW'&&job.token){
      card.append(node('p','可寫候選：'+job.root),node('p',job.realGit?'只批准改動 '+job.targets.join('、')+'。驗證：'+job.verification:'預期只修改 calculator.py；test_calculator.py 與 AGENTS.md 必須保持不變。將執行 Python unittest。'));
      if(job.realGit)card.append(node('p','唯讀來源：'+job.original),node('p','來源版本：'+job.source_id.head+' · '+job.source_id.sha256),
        node('p','執行器：'+job.executor),node('p','模型寫入副本：'+job.executionScope+'。NEXUS 只將核對過的檔案寫回候選。'));
      const sources=node('details');sources.open=true;sources.append(node('summary','檔案內容'));
      for(const [name,text]of Object.entries(job.source)){sources.append(node('h4',name),node('pre',text));}card.append(sources);
      card.append(node('p','Windows 寫入邊界會先用測試檔實測。此沙盒不保證私人檔案讀取及完整網路隔離；任務不授權存取範例以外資料，額外權限要求一律拒絕。'));
      const label=node('label'),box=node('input');box.type='checkbox';box.style.width='auto';label.append(box,document.createTextNode(' 我確認僅授權上述檔案的修改與測試'));card.append(label);
      const confirm=node('button',job.realGit?'批准修改隔離候選並執行測試':'批准修改隔離範例並執行測試');confirm.type='button';confirm.className='primary-button';confirm.disabled=true;box.onchange=()=>confirm.disabled=!box.checked;
      confirm.onclick=async()=>{confirm.disabled=true;try{
        const approval={id:job.id,token:job.token,authority:job.realGit?'SELECTED_GIT_WRITE':'ISOLATED_SAMPLE_WRITE'};
        if(job.realGit){
          approval.chat=window.companionChatSelection?.();
          approval.project=job.projectId;
        }
        await api('confirm',approval);card.querySelector('p').textContent='已送出這次明確批准。';
      }catch(e){card.querySelector('p').textContent=e.message;}};card.append(confirm);
    }
    if(job.events?.length)card.append(node('p','目前進度：'+job.events.at(-1).kind));
    if(job.tests)card.append(node('h4','主機覆核測試 · Exit '+job.tests.exitCode),node('pre',(job.tests.stdout||'')+(job.tests.stderr||'')));
    if(job.diff)card.append(node('h4','實際檔案差異'),node('pre',job.diff));
    if(job.realGit&&job.state==='PENDING_REVIEW'&&onEvidence){
      const evidence=node('button','預覽並選取 Git 工作證據');
      evidence.type='button';evidence.className='secondary-button';
      evidence.onclick=onEvidence;card.append(evidence);
    }
    if(job.model_summary){const summary=node('details');summary.append(node('summary','Codex 完成說明'),node('p',job.model_summary));card.append(summary);}
    if(job.events?.length){const events=node('details');events.append(node('summary','原生工具與工作紀錄'),node('pre',JSON.stringify({thread:job.thread_id,turn:job.turn_id,events:job.events},null,2)));card.append(events);}
    return card;
  }};
  function picker(){
    const panel=node('details');
    panel.id='git-project-picker';
    panel.append(node('summary','Git 工程'));
    const status=node('p');status.setAttribute('role','status');
    const register=node('details');register.append(node('summary','登錄本機專案'));
    const name=field(register,'專案名稱'),folder=field(register,'projects 下的來源資料夾名稱');
    const consent=field(register,'我確認這是非敏感來源','checkbox');
    const project=field(panel,'專案','select'),work=field(panel,'接續工作','select');
    project.id='git-project';work.id='git-job';
    const info=node('p');panel.append(info,status);
    const goal=field(panel,'工程需求','textarea'),targets=field(panel,'允許變更的相對 Python 檔案，每行一個','textarea');
    const test=field(panel,'既有 unittest 檔案（留空只檢查語法）');
    const controls=node('div');
    let catalog={projects:[],jobs:[]};
    let catalogOwner='';
    const owner=()=>window.companionProjectStatus?.().account||'';
    function field(parent,label,kind='input'){
      const wrapper=node('label',label+' ');
      const input=node(kind==='checkbox'?'input':kind);
      if(kind==='checkbox')input.type='checkbox';
      wrapper.style.display='block';wrapper.append(input);parent.append(wrapper);
      return input;
    }
    function action(parent,title,run){
      const button=node('button',title);button.type='button';button.className='secondary-button';
      button.onclick=async()=>{button.disabled=true;try{await run();}catch(e){status.textContent=e.message;}finally{button.disabled=false;}};
      parent.append(button);
      return button;
    }
    function showSelection(){
      const picked=catalog.projects.find(p=>p.id===project.value);
      info.textContent=picked?.readonly?'這個項目只提供既有 Reverb 工程紀錄。':
        picked?'唯讀來源 '+picked.source+' · 獨立候選 '+picked.root:'請先登錄或選擇專案。';
      work.replaceChildren(new Option('選擇工作',''),...catalog.jobs.filter(j=>j.project===project.value)
        .map(j=>new Option(j.goal.slice(0,65)+' · '+j.state,j.id)));
      for(const input of [goal,targets,test,preview])input.disabled=!picked||!!picked.readonly;
    }
    async function refresh(){
      const requestedOwner=owner();
      const data=await api('catalog',{});
      if(!requestedOwner||owner()!==requestedOwner)return;
      catalog=data;
      catalogOwner=requestedOwner;
      project.replaceChildren(new Option('選擇專案',''),...catalog.projects.map(p=>new Option(p.name,p.id)));
      project.value=catalog.selected||'';
      showSelection();
    }
    async function open(actionName,body){
      const chat=window.companionChatSelection?.()||null;
      const result=await api(actionName,{...body,chat});
      if(!chat){
        for(let i=0;i<50&&!Array.from(el('chat-history').options).some(o=>o.value===result.chat);i++)
          await new Promise(resolve=>setTimeout(resolve,100));
        if(!Array.from(el('chat-history').options).some(o=>o.value===result.chat))throw Error('請在對話紀錄選取工程對話。');
        if(!window.companionChatSelection?.())window.openCompanionChat(result.chat);
      }
      status.textContent=actionName==='preview'?'已保存預覽，請在對話核對並確認。':'已接續所選工作。';
    }
    project.onchange=async()=>{
      try{if(project.value)await api('select',{project:project.value});await refresh();status.textContent='';}
      catch(e){status.textContent=e.message;}
    };
    action(register,'登錄並建立隔離候選',async()=>{
      const p=await api('register',{name:name.value,folder:folder.value,nonSensitive:consent.checked});
      await api('select',{project:p.id});await refresh();register.open=false;
      status.textContent='已登錄並選擇 '+p.name;
    });
    const preview=action(controls,'預覽工程',()=>open('preview',{project:project.value,goal:goal.value,
      targets:targets.value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean),test:test.value.trim()}));
    action(controls,'接續選定工作',()=>open('continue',{project:project.value,id:work.value}));
    action(controls,'更新專案與工作',refresh);
    panel.append(controls,register);
    window.addEventListener('companion-continuity',()=>{
      if(!catalogOwner||catalogOwner===owner())return;
      catalogOwner='';
      catalog={projects:[],jobs:[]};
      project.replaceChildren(new Option('選擇專案',''));
      for(const input of [name,folder,goal,targets,test])input.value='';
      consent.checked=false;status.textContent='';panel.open=false;
      showSelection();
    });
    panel.ontoggle=()=>{if(panel.open)refresh().catch(e=>{status.textContent=e.message;});};
    el('chat-send').before(panel);
    showSelection();
  }
  window.addEventListener('DOMContentLoaded',()=>{
    if(real){
      picker();
      return;
    }
    const button=node('button','預覽工程範例');button.type='button';button.className='secondary-button';
    button.onclick=async()=>{button.disabled=true;try{
      const chat=window.companionChatSelection?.()||null;
      const job=await api('preview',{chat,question:el('chat-question').value});
      if(!chat){
        // Let the existing chat refresh expose the locally saved conversation.
        for(let i=0;i<50&&!Array.from(el('chat-history').options).some(o=>o.value===job.chat);i++){
          if(window.companionProjectStatus?.().account!==job.account)throw Error('帳戶已變更；請重新選取對話。');
          await new Promise(resolve=>setTimeout(resolve,100));
        }
        if(!Array.from(el('chat-history').options).some(o=>o.value===job.chat))throw Error('預覽已保存；請從對話紀錄選取工程範例。');
        window.openCompanionChat(job.chat);
      }
      el('chat-notice').textContent='工程範例預覽已保存；請在本對話核對來源與寫入範圍。';
    }catch(e){el('chat-notice').textContent=e.message;}finally{button.disabled=false;}};
    el('chat-send').before(button);
  });
})();
