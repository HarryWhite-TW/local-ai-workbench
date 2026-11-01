/* On-screen, read-only native history. No model source selection or saved transcript. */
(() => {
  if(document.body.dataset.nativeCodex!=='true')return;
  const el=id=>document.getElementById(id),node=(tag,value)=>{const n=document.createElement(tag);n.textContent=value;return n;};
  const section=node('section','');section.className='nexus-panel native-codex';section.id='native-codex';
  // Constant markup only. All source data below is inserted as plain text.
  section.innerHTML='<p class="nexus-kicker">NATIVE CODEX / LOCAL HISTORY</p><h2>原生 Codex 工作</h2><p class="native-alert">已保存的歷史紀錄 · 即時執行狀態未確認</p><div class="native-toolbar"><button id="native-preview" class="primary-button">預覽連接範圍</button><button id="native-refresh" class="secondary-button" hidden>重新整理</button><button id="native-disconnect" class="text-button" hidden>中斷連接並清除畫面</button><label id="native-archive-label" hidden>工作範圍 <select id="native-archive"><option value="false">最近工作</option><option value="true">已封存工作</option></select></label><label id="native-auto-label" hidden><input id="native-auto" type="checkbox" checked>本頁可見時每 30 秒更新</label></div><p id="native-notice" role="status">尚未讀取原生 Codex 工作；請先確認範圍。</p><div id="native-scope" hidden><p id="native-scope-path"></p><p id="native-scope-description"></p><button id="native-confirm" class="primary-button">確認本機唯讀範圍並連接</button></div><div class="native-grid"><div id="native-list" aria-label="原生 Codex 工作列表"></div><article id="native-detail" aria-label="原生工作進度與回覆"></article></div>';
  el('nexus-execution-list').before(section);
  el('nexus-execute-title').textContent='接回上次的工作。';
  el('nexus-execute-title').nextElementSibling.textContent='先看交辦與回覆，再決定下一步。';
  const localWork=node('details','');localWork.className='native-local-work';
  localWork.append(node('summary','NEXUS 本機工作與審查'));el('nexus-execution-list').before(localWork);localWork.append(el('nexus-execution-list'));
  const settings=node('details','');settings.className='native-settings';settings.append(node('summary','連接設定'));
  section.querySelector('.native-toolbar').append(settings);
  for(const id of ['native-disconnect','native-archive-label','native-auto-label'])settings.append(el(id));
  const shortcut=node('button','查看原生 Codex 最近進度 ↗');shortcut.className='secondary-button';shortcut.id='native-shortcut';
  shortcut.onclick=()=>{el('nexus-navigation').querySelector('[data-route="execute"]').click();section.scrollIntoView({block:'start'});el('native-preview').focus({preventScroll:true});};
  el('nexus-overview').querySelector('.nexus-home-actions').append(shortcut);
  let token='',connected=false,owner='',epoch=0,busy=false,selected='',threads=[];
  const account=()=>window.companionProjectStatus?.().account||'';
  const stamp=value=>{if(!value)return '時間未提供';const d=new Date(typeof value==='number'?value*1000:value);return Number.isNaN(d.valueOf())?'時間未提供':d.toLocaleString('zh-TW');};
  const states={completed:'已完成一輪回覆',interrupted:'已中斷',failed:'失敗',inProgress:'進行中'};
  async function api(action,body){
    const r=await fetch('/api/chat/codex-'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify(body)});
    const data=await r.json();if(!r.ok)throw Error(data.error||'Codex 記錄無法確認。');return data;
  }
  function controls(){
    for(const id of ['native-refresh','native-disconnect','native-archive-label','native-auto-label'])el(id).hidden=!connected;
    el('native-preview').hidden=connected;el('native-refresh').disabled=busy;el('native-confirm').disabled=busy;
  }
  function clear(message){
    ++epoch;token='';connected=false;owner='';selected='';threads=[];busy=false;
    el('native-list').replaceChildren();el('native-detail').replaceChildren();el('native-scope').hidden=true;
    el('native-notice').textContent=message;controls();
  }
  const valid=mine=>mine===epoch&&owner===account();
  function fail(error){el('native-list').replaceChildren();el('native-detail').replaceChildren();threads=[];el('native-notice').textContent=(error.message||'讀取失敗。')+' 上次資料已移除，請重試或返回原生 Codex。';}
  el('native-preview').onclick=async()=>{
    clear('正在確認可讀取範圍…');owner=account();const mine=epoch;
    try{const p=await api('preview',{});if(!valid(mine))return;token=p.token;
      el('native-scope-path').textContent='允許的工作區：'+p.workspace;
      el('native-scope-description').textContent=p.scope;
      el('native-scope').hidden=false;el('native-confirm').disabled=!p.available;
      el('native-notice').textContent=p.available?'確認後才讀取工作標題與內容。':'找不到本機 Codex App Server，請先開啟原生工具。';
    }catch(e){if(valid(mine))fail(e);}
  };
  el('native-confirm').onclick=async()=>{
    const mine=epoch;busy=true;controls();
    try{await api('connect',{token});if(!valid(mine))return;connected=true;el('native-scope').hidden=true;busy=false;controls();await refresh();}
    catch(e){if(valid(mine))fail(e);}finally{if(valid(mine)){busy=false;controls();}}
  };
  el('native-disconnect').onclick=()=>{const previous=token;clear('已中斷本分頁連接並清除畫面。原生工作繼續保留。');void api('disconnect',{token:previous}).catch(()=>{});};
  function renderList(){
    el('native-list').replaceChildren();
    if(!threads.length){el('native-list').append(node('p','這個工作區目前沒有此範圍的可讀取紀錄。'));return;}
    for(const t of threads){const b=node('button','');b.className='native-row';b.dataset.thread=t.id;b.setAttribute('aria-pressed',String(t.id===selected));
      b.append(node('strong',t.title),node('small','最後記錄 · '+stamp(t.updated_at)));b.onclick=()=>{if(!busy)void detail(t.id);};el('native-list').append(b);}
  }
  function message(parent,title,entry,limit=520){
    const block=node('section','');block.className='native-copy';block.append(node('h3',title));
    const value=entry.text||'這則訊息沒有可顯示的文字。';
    const text=node('pre',value.length>limit?value.slice(0,limit)+'…':value);text.className='native-message';block.append(text);
    if(value.length>limit){const full=node('details','');full.className='native-full';full.append(node('summary','展開這則原文'));const original=node('pre',value);original.className='native-message';full.append(original);block.append(full);full.addEventListener('toggle',()=>text.hidden=full.open);}
    if(entry.truncated)block.append(node('small','來源文字較長，僅讀取前段；完整內容請回原生 Codex。'));
    if(entry.attachments_omitted)block.append(node('small','此指令另有非文字附件，未讀取附件內容。'));
    parent.append(block);
  }
  function renderDetail(data){
    const previousTurn=el('native-pair')?.dataset.turn;
    const expanded=[...el('native-detail').querySelectorAll('details')].map(d=>d.open);
    const parent=el('native-detail');parent.replaceChildren();parent.append(node('h2',data.thread.title));
    const actions=node('div','');actions.className='native-detail-actions';const a=node('a','回原生 Codex 繼續 ↗');a.href=data.thread.url;actions.append(a);parent.append(actions);
    if(!data.turns.length){parent.append(node('p','尚無可讀取回合；請回原生工具確認。'));return;}
    const paired=data.turns.findIndex(t=>t.instructions?.length),initial=paired<0?0:paired;
    const selector=node('select','');selector.id='native-turn';selector.setAttribute('aria-label','選擇交辦回合');
    data.turns.forEach((t,i)=>{const option=node('option',(i===0?'最新 · ':'')+stamp(t.completed_at||t.started_at)+(t.instructions?.length?' · 有交辦指令':' · 未附指令'));option.value=String(i);selector.append(option);});
    const previousIndex=data.turns.findIndex(t=>t.id===previousTurn);
    selector.value=String(previousIndex<0?initial:previousIndex);const picker=node('label','回合 ');picker.className='native-turn-picker';picker.append(selector);parent.append(picker);
    const reading=node('div','');reading.id='native-pair';parent.append(reading);
    function show(){
      const at=Number(selector.value),t=data.turns[at];reading.replaceChildren();reading.dataset.turn=t.id;
      if(at>0)reading.append(node('p','目前顯示較早的交辦回合；另有 '+at+' 個較新回合，可從上方切換查看。'));
      const instructions=t.instructions||[];
      if(instructions.length)for(const instruction of instructions)message(reading,'我上次交辦什麼',instruction,240);
      else {const absent=node('section','');absent.className='native-copy';absent.append(node('h3','我上次交辦什麼'),node('p','這個回合沒有已保存的使用者文字指令，無法確認交辦內容。'));reading.append(absent);}
      if(t.omitted_instructions)reading.append(node('p','另有 '+t.omitted_instructions+' 則指令未讀取，請回原生工具核對。'));
      const reply=[...t.messages].reverse().find(m=>m.phase==='final_answer')||t.messages.at(-1);
      if(reply)message(reading,reply.phase==='final_answer'?'Codex 回覆':'Codex 最近進度',reply);
      else reading.append(node('p','此回合尚無已保存的 Codex 回覆。'));
      const next=node('div','');next.className='native-next-step';next.append(node('h3','下一步'),node('p','核對這輪回覆中的待辦或待確認事項，再回原生 Codex 繼續。'));reading.append(next);
      const more=node('details','');more.className='native-record';more.append(node('summary','這一輪的進度與來源'));
      more.append(node('p','歷史狀態：'+(states[t.recorded_status]||'未提供')+' · 回合完成不代表目標完成或技術驗收。'));
      for(const m of t.messages)if(m!==reply)message(more,'進度原文',m);
      if(t.omitted_messages)more.append(node('p','另有 '+t.omitted_messages+' 則較早回覆未顯示。'));
      more.append(node('p','來源：官方 Codex App Server · thread/read、thread/turns/list'),node('p','工作：'+data.thread.id),node('p','回合：'+t.id),node('p','讀取時間：'+stamp(data.captured_at)),node('p','已讀取命令事件 '+t.commands.length+' 筆、檔案變更 '+t.changes.length+' 筆；未顯示工具輸出與推理。'));
      const failed=t.commands.filter(c=>c.exit_code!==null&&c.exit_code!==0).length;
      if(failed)more.append(node('p','本回合記錄 '+failed+' 次非零結束碼；後續是否修正需核對原文。'));
      if(data.has_older)more.append(node('p','僅讀取最近 5 回合，更早歷史請回原生 Codex。'));
      reading.append(more);
    }
    selector.onchange=show;show();
    if(previousIndex>=0)[...parent.querySelectorAll('details')].forEach((d,i)=>d.open=!!expanded[i]);
  }
  async function detail(id,insideRefresh=false){
    if(busy&&!insideRefresh)return;selected=id;renderList();const mine=epoch;busy=true;controls();
    if(!insideRefresh)el('native-detail').replaceChildren(node('p','正在讀取這項工作的最近回覆…'));
    try{const data=await api('detail',{token,id});if(valid(mine)&&selected===id)renderDetail(data);}
    catch(e){if(valid(mine))fail(e);}finally{if(valid(mine)){busy=false;controls();}}
  }
  async function refresh(){
    if(!connected||busy)return;const mine=epoch;busy=true;controls();el('native-notice').textContent='正在核對最新已保存紀錄…';
    try{const data=await api('list',{token,archived:el('native-archive').value==='true'});if(!valid(mine))return;
      threads=data.threads;renderList();el('native-notice').textContent='已讀取 '+threads.length+' 項工作 · '+stamp(data.captured_at)+(data.has_more?' · 僅顯示最近 100 項，其餘請回原生工具。':'')+' · 僅本分頁顯示。';
      if(selected&&threads.some(t=>t.id===selected))await detail(selected,true);
      else{selected='';el('native-detail').replaceChildren(node('p','選取一項工作，閱讀進度、最後回覆與下一步。'));}
    }catch(e){if(valid(mine))fail(e);}finally{if(valid(mine)){busy=false;controls();}}
  }
  el('native-refresh').onclick=()=>void refresh();el('native-archive').onchange=()=>{selected='';void refresh();};
  window.addEventListener('companion-project',()=>{if(token&&owner!==account())clear('帳戶或登入狀態已變更，請重新確認本機讀取範圍。');});
  window.addEventListener('companion-state',e=>{if(e.detail.offline&&token)clear('NEXUS 連線未確認，已清除原生資料；連線恢復後請重新連接。');});
  setInterval(()=>{if(!document.hidden&&document.body.dataset.route==='execute'&&el('native-auto').checked)void refresh();},30000);
  controls();
})();
