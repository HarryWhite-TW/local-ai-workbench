/* Conversation layout only. Existing controllers own all data and authority. */
(() => {
  if(document.body.dataset.workEnabled!=='true')return;
  const el=id=>document.getElementById(id),body=document.body;
  const node=(tag,value='',className='')=>{const n=document.createElement(tag);n.textContent=value;if(className)n.className=className;return n;};
  const button=(label,run,className='secondary-button')=>{const b=node('button',label,className);b.type='button';b.onclick=run;return b;};
  if(window.nexusComparisonLayout){
    const mark=()=>{if(!location.hash.startsWith('#chat'))return;const [route,query]=location.hash.split('?'),p=new URLSearchParams(query);p.set('layout','ux02');history.replaceState(history.state,'',route+'?'+p);};
    window.addEventListener('companion-chat-selected',()=>queueMicrotask(mark));mark();return;
  }
  body.dataset.conversationLayout='true';
  const preferenceKey='nexus.conversation.reading.v1';let prefs={font:'18',width:'comfortable'};
  try{const saved=JSON.parse(localStorage.getItem(preferenceKey)||'null');if(['18','20','22'].includes(saved?.font))prefs.font=saved.font;if(['comfortable','wide'].includes(saved?.width))prefs.width=saved.width;}catch{}
  function applyPreferences(){body.style.setProperty('--conversation-font',prefs.font+'px');body.dataset.readingWidth=prefs.width;try{localStorage.setItem(preferenceKey,JSON.stringify(prefs));}catch{}}
  applyPreferences();
  const heading=el('chat-space').querySelector('.chat-heading');el('chat-title').textContent='Companion';
  heading.append(el('chat-history').parentElement);el('chat-history').setAttribute('aria-label','切換保存的對話');
  const tools=node('div','','conversation-tools');
  const options=node('div','','conversation-options');options.id='conversation-options';options.hidden=true;
  const settings=button('閱讀設定',()=>{options.hidden=!options.hidden;settings.setAttribute('aria-expanded',String(!options.hidden));});
  settings.setAttribute('aria-expanded','false');settings.setAttribute('aria-controls',options.id);
  function choice(label,values,selected,change){const wrap=node('label',label),select=node('select');select.setAttribute('aria-label',label);for(const [value,name]of values){const o=node('option',name);o.value=value;select.append(o);}select.value=selected;select.onchange=()=>change(select.value);wrap.append(select);return wrap;}
  options.append(choice('閱讀字級',[['18','舒適 · 18'],['20','大字 · 20'],['22','特大 · 22']],prefs.font,value=>{prefs.font=value;applyPreferences();fitInput();}),
    choice('閱讀寬度',[['comfortable','自然行長'],['wide','寬敞閱讀']],prefs.width,value=>{prefs.width=value;applyPreferences();}),
    button('收合／展開側欄',()=>el('nexus-sidebar-toggle').click()));
  const compare=node('a','比較 UX-02 版面');compare.target='_blank';compare.rel='noopener';
  function comparisonLink(){const id=window.companionChatSelection?.()||'';compare.href='/#chat?'+new URLSearchParams({...(id?{chat:id}:{}),layout:'ux02'});}
  comparisonLink();window.addEventListener('companion-chat-selected',comparisonLink);options.append(compare);
  const parking=node('div');parking.hidden=true;parking.id='conversation-parking';parking.append(el('project-chat-strip'));
  const layout=node('div','','conversation-body');layout.id='conversation-body';
  el('chat-messages').before(layout);
  const column=node('div','','conversation-column');
  column.append(el('chat-messages'),el('document-chat-context'),el('work-chat-context'),el('chat-form'));layout.append(column);
  const pane=node('aside','','conversation-reader');pane.id='conversation-reader';pane.hidden=true;pane.setAttribute('aria-label','情境閱讀區');
  const readerHeader=node('header'),readerTitle=node('h2'),readerSelect=node('select');readerSelect.setAttribute('aria-label','閱讀內容');
  const focus=button('專注閱讀',()=>{body.dataset.readerFocus=body.dataset.readerFocus==='true'?'false':'true';focus.setAttribute('aria-pressed',body.dataset.readerFocus);});focus.setAttribute('aria-pressed','false');
  const close=button('關閉閱讀',()=>closeReader(true),'text-button');close.setAttribute('aria-label','關閉情境閱讀區');
  readerHeader.append(readerTitle,focus,close);
  const readerBody=node('div','','conversation-reader-body'),readerFooter=node('footer');readerBody.tabIndex=0;
  pane.append(readerHeader,readerSelect,readerBody,readerFooter);layout.append(pane);
  tools.append(button('專案情境',()=>openReader('專案情境',[{label:'目前對話的專案',mount:[el('project-chat-strip')]}],'project')),settings);
  heading.append(tools);heading.after(options);el('chat-space').append(parking);
  let current=null,mounted=[],lastFocus=null;
  function restoreMounted(){for(const {element,placeholder}of mounted){if(placeholder.parentNode)placeholder.replaceWith(element);}mounted=[];}
  function mount(element,parent){const placeholder=document.createComment('conversation reading position');element.before(placeholder);mounted.push({element,placeholder});parent.append(element);}
  function closeReader(cancel=false){
    const mode=current?.mode;restoreMounted();current=null;pane.hidden=true;body.dataset.readerOpen='false';body.dataset.readerFocus='false';focus.setAttribute('aria-pressed','false');
    readerBody.replaceChildren();readerFooter.replaceChildren();
    if(cancel&&mode==='proposal')el('work-close').click();
    if(cancel&&mode==='organize')el('organize-close').click();
    if(lastFocus?.isConnected)lastFocus.focus({preventScroll:true});
  }
  function showSection(index){
    restoreMounted();readerBody.replaceChildren();readerFooter.replaceChildren();
    const section=current.sections[index];readerSelect.value=String(index);
    for(const element of section.mount||[])mount(element,readerBody);
    for(const element of section.footer||[])mount(element,readerFooter);
    if(section.text!==undefined){
      const content=node(section.kind==='code'?'pre':'div','','conversation-reading-content');
      if(section.kind==='code')content.textContent=section.text;else window.CompanionReading.markdown(content,section.text);
      readerBody.append(content);
    }
    readerBody.scrollTop=0;
  }
  function openReader(title,sections,mode='read'){
    if(current)closeReader(current.mode==='proposal'||current.mode==='organize');lastFocus=document.activeElement;current={title,sections,mode};
    readerTitle.textContent=title;readerSelect.replaceChildren(...sections.map((s,i)=>{const o=node('option',s.label);o.value=String(i);return o;}));readerSelect.hidden=sections.length===1;
    pane.hidden=false;body.dataset.readerOpen='true';showSection(0);
    if(innerWidth<1100){body.dataset.readerFocus='true';focus.setAttribute('aria-pressed','true');}
    readerBody.focus({preventScroll:true});
  }
  readerSelect.onchange=()=>showSection(Number(readerSelect.value));
  pane.addEventListener('click',event=>{if(event.target.closest('[data-close]')){event.preventDefault();event.stopImmediatePropagation();closeReader(false);}},true);
  pane.addEventListener('keydown',event=>{if(event.key==='Escape'){event.stopPropagation();closeReader(true);}});
  // Secondary spaces stay available without making engineering navigation dominant.
  const nav=el('nexus-navigation'),more=node('details','','conversation-more');more.append(node('summary','更多空間'));
  for(const b of [...nav.querySelectorAll('button')])if(!['chat','project','documents','work'].includes(b.dataset.route))more.append(b);
  nav.prepend(el('open-chat'));nav.append(more);
  const composeToggle=button('展開輸入',()=>{body.dataset.composeExpanded=body.dataset.composeExpanded==='true'?'false':'true';composeToggle.textContent=body.dataset.composeExpanded==='true'?'縮小輸入':'展開輸入';fitInput();el('chat-question').focus();},'text-button');
  el('chat-send').before(composeToggle);el('chat-question').placeholder='寫下想法，或一起處理一件事…';
  function fitInput(){const input=el('chat-question');input.style.height='auto';const expanded=body.dataset.composeExpanded==='true';input.style.height=Math.min(Math.max(input.scrollHeight,expanded?220:58),innerHeight*(expanded ? .46 : .26))+'px';return true;}
  function attachment(id,contentId,label){const b=button(label,()=>openReader(label,[{label:'下則訊息將分享的內容',text:el(contentId).textContent,kind:'code'}],'consent'),'text-button');el(id).append(b);}
  attachment('work-chat-context','work-chat-preview','閱讀待分享的診斷');attachment('document-chat-context','document-chat-content','閱讀本次文件節錄');
  function resetForSelection(){const id=window.companionChatSelection?.()||'';if(resetForSelection.id!==undefined&&resetForSelection.id!==id)closeReader(false);resetForSelection.id=id;}
  window.addEventListener('companion-chat-selected',resetForSelection);
  window.addEventListener('resize',()=>{
    if(current?.mode==='organize'){
      const needsInput=innerWidth<1100,hasInput=current.sections[0].mount.includes(el('chat-question'));
      if(needsInput!==hasInput){current.sections[0].mount=[...(needsInput?[el('chat-question')]:[]),el('organize-panel')];showSection(0);}
    }
    fitInput();
  });
  window.NexusConversation={
    fitInput,
    resetContext(){if(current)closeReader(true);},
    clearConsent(){if(current?.mode==='consent')closeReader(false);},
    openExisting(id){
      if(!['chat-knowledge','chat-source-dialog'].includes(id))return false;
      const dialog=el(id);openReader(id==='chat-knowledge'?'加入這則訊息的資料':'這一輪的來源快照',[{label:'核對分享範圍',mount:[dialog.querySelector('.chat-aux-body')],footer:[dialog.querySelector('.chat-aux-footer')]}],'consent');return true;
    },
    proposalOpened(){openReader('這次唯讀診斷',[{label:'來源與授權確認',mount:[el('work-proposal')],footer:[el('work-confirm')]}],'proposal');return true;},
    proposalClosed(){if(current?.mode==='proposal')closeReader(false);},
    organizeOpened(){openReader('整理選定文件',[{label:'選檔與分享確認',mount:[...(innerWidth<1100?[el('chat-question')]:[]),el('organize-panel')],footer:[el('organize-start')]}],'organize');},
    organizeClosed(){if(current?.mode==='organize')closeReader(false);},
    previewSources(p){
      const manifest=el('work-manifest'),select=node('select'),code=node('pre','','chat-source-text');select.setAttribute('aria-label','選擇要核對的程式快照');
      manifest.replaceChildren(node('p','本次只分享以下 '+p.manifest.length+' 份來源。確認前可逐份閱讀：'));
      for(const r of p.manifest){const option=node('option',r.name);option.value=r.key;select.append(option);}
      const identity=node('small');
      const update=()=>{const s=p.source_snapshots?.find(r=>r.key===select.value);code.textContent=s?s.text.split('\n').map((line,i)=>'L'+(i+1)+': '+line).join('\n'):'沒有可核對的來源文字。';identity.textContent=s?'SHA-256 '+s.sha256:'';};
      select.onchange=update;update();manifest.append(select,identity,code);
    },
    diagnosis(card,result){
      const summary=node('div','','native-result-summary conversation-diagnosis');
      for(const [key,label]of [['overview','診斷結論'],['next_steps','接下來可以做什麼']]){
        const value=result.presentation?.[key]||(key==='overview'?result.result.slice(0,600):'');if(!value)continue;
        const section=node('section'),content=node('div');section.append(node('h4',label));window.CompanionReading.markdown(content,value);section.append(content);summary.append(section);
      }
      card.append(summary);
      const full=result.result.startsWith('Codex 唯讀工程診斷（模型輸出，未經獨立技術審查）\n')?result.result.split('\n\n').slice(1).join('\n\n'):result.result;
      const sections=[{label:'完整診斷',text:full},{label:'程式碼依據',text:result.presentation?.evidence||'請在完整診斷內核對來源引用。'},{label:'原始保存紀錄',text:result.result,kind:'code'}];
      card.append(button('閱讀依據與完整診斷',()=>openReader('診斷閱讀',sections)));
      return true;
    },
    workCard(card,p){
      if(p.kind!=='native_codex')return;
      const details=[...card.children].filter(n=>n.tagName==='DETAILS'&&['技術與驗收資訊','工作身分與實際事件'].includes(n.querySelector('summary')?.textContent));
      for(const d of details)d.classList.add('conversation-technical');
      if(details.length)card.append(button('工作紀錄',()=>{for(const d of details)d.open=true;openReader('執行與審查紀錄',[{label:'工作身分與事件',mount:details}]);},'text-button'));
      for(const b of card.querySelectorAll('button'))if(b.textContent==='用這份診斷接著聊')b.className='primary-button conversation-followup';
    },
    organizationCard(card,job){
      if(!job.plan)return;
      const sections=job.plan.map(p=>({label:p.name+' · '+p.category,text:'分類：'+p.category+'\n\n'+p.reason+'\n\n> '+p.evidence.replace(/\n/g,'\n> ')+'\n\n副本位置：'+p.destination}));
      card.append(button('閱讀分類依據',()=>openReader('文件分類與原文',sections),'text-button'));
    }
  };
  fitInput();if(!location.hash)el('open-chat').click();
})();
