/* Fixed isolated sample; never reuses READ_ONLY approval or ReviewStore actions. */
(() => {
  if(document.body.dataset.pilotEnabled!=='true')return;
  const el=id=>document.getElementById(id), node=(tag,text='')=>{const n=document.createElement(tag);n.textContent=text;return n;};
  async function api(action,body){const r=await fetch('/api/chat/pilot-'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify(body)});const v=await r.json();if(!r.ok)throw Error(v.error||'試點未能確認。');return v;}
  window.NexusPilot={state:chat=>api('state',{chat}),card(job){
    const card=node('section');card.className='chat-work-card';card.dataset.pilot=job.id;card.dataset.state=job.state;
    const labels={PREVIEW:'隔離工程範例 · 請核對寫入範圍',RUNNING:'Codex 正在處理隔離範例',COMPLETED:'範例修改與測試已完成',FAILED:'未開始工程執行',UNKNOWN:'執行結果尚未確認'};
    card.append(node('h3',labels[job.state]||job.state),node('p',job.summary));
    if(job.state==='PREVIEW'){
      card.append(node('p','可寫範圍僅限：'+job.root),node('p','預期只修改 calculator.py；test_calculator.py 與 AGENTS.md 必須保持不變。將執行 Python unittest。這是工程寫入授權，與唯讀診斷及結果審查分開。'));
      const sources=node('details');sources.open=true;sources.append(node('summary','本次範例來源'));
      for(const [name,text]of Object.entries(job.source)){sources.append(node('h4',name),node('pre',text));}card.append(sources);
      card.append(node('p','Windows 寫入邊界會先用測試檔實測。此沙盒不保證私人檔案讀取及完整網路隔離；任務不授權存取範例以外資料，額外權限要求一律拒絕。'));
      const label=node('label'),box=node('input');box.type='checkbox';box.style.width='auto';label.append(box,document.createTextNode(' 我確認僅授權這份隔離範例的修改與測試'));card.append(label);
      const confirm=node('button','批准修改隔離範例並執行測試');confirm.type='button';confirm.className='primary-button';confirm.disabled=true;box.onchange=()=>confirm.disabled=!box.checked;
      confirm.onclick=async()=>{confirm.disabled=true;try{await api('confirm',{id:job.id,token:job.token,authority:'ISOLATED_SAMPLE_WRITE'});card.querySelector('p').textContent='已送出這次明確批准；正在啟動原生 Codex。';}catch(e){card.querySelector('p').textContent=e.message;}};card.append(confirm);
    }
    if(job.events?.length)card.append(node('p','目前進度：'+job.events.at(-1).kind));
    if(job.tests)card.append(node('h4','主機覆核測試 · Exit '+job.tests.exitCode),node('pre',(job.tests.stdout||'')+(job.tests.stderr||'')));
    if(job.diff)card.append(node('h4','實際檔案差異'),node('pre',job.diff));
    if(job.model_summary){const summary=node('details');summary.append(node('summary','Codex 完成說明'),node('p',job.model_summary));card.append(summary);}
    if(job.events?.length){const events=node('details');events.append(node('summary','原生工具與工作紀錄'),node('pre',JSON.stringify({thread:job.thread_id,turn:job.turn_id,events:job.events},null,2)));card.append(events);}
    return card;
  }};
  window.addEventListener('DOMContentLoaded',()=>{
    const button=node('button','預覽工程範例');button.type='button';button.className='secondary-button';
    button.onclick=async()=>{button.disabled=true;try{
      const chat=window.companionChatSelection?.();if(!chat)throw Error('請先選取一段已保存的對話，再預覽隔離工程範例。');
      await api('preview',{chat,question:el('chat-question').value});el('chat-notice').textContent='工程範例預覽已保存；請在本對話核對來源與寫入範圍。';
    }catch(e){el('chat-notice').textContent=e.message;}finally{button.disabled=false;}};
    el('chat-send').before(button);
  });
})();
