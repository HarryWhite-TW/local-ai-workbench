/* Trusted host UI. Generated source executes only in an opaque sandbox frame. */
(() => {
  if(document.body.dataset.controlledCode!=='true')return;
  const el=id=>document.getElementById(id),node=(tag,text='')=>{const n=document.createElement(tag);n.textContent=text;return n;};
  async function api(action,body){const r=await fetch('/api/chat/code-'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify(body)});const v=await r.json();if(!r.ok)throw Error(v.error||'受控工程未確認。');return v;}
  function reviewSummary(job){
    const tests=job.tests;
    return ['NEXUS · 宿主審查摘要','工作：'+job.id,'狀態：'+job.state,'需求：'+job.goal,
      (job.state==='COMPLETED'?'實際修改目標：':'預定目標（尚未確認套用）：')+job.source.root+'/'+job.source.target,
      '實際驗證命令：'+(tests?.command||'尚無主機驗證紀錄'),
      'Exit code：'+(tests?.exitCode??'未確認'),
      'stdout：\n'+(tests?.stdout||'（無輸出）'),'stderr：\n'+(tests?.stderr||'（無輸出）'),
      '限制：主機靜態語法檢查不代表功能測試通過；生成範例的複製功能尚未驗證通過。',
      '審查狀態：尚待獨立技術審查。'].join('\n');
  }
  function reviewControls(job){
    const section=node('section');section.className='controlled-review';
    const copy=node('button','複製宿主審查摘要');copy.type='button';
    const feedback=node('p');feedback.className='controlled-copy-status';feedback.setAttribute('role','status');feedback.setAttribute('aria-live','polite');
    const details=node('details'),content=node('textarea');content.readOnly=true;content.value=reviewSummary(job);content.setAttribute('aria-label','宿主審查摘要全文');
    details.append(node('summary','查看／手動選取宿主審查摘要'),content);
    copy.onclick=async event=>{
      copy.disabled=true;feedback.textContent='正在寫入剪貼簿…';feedback.dataset.state='pending';
      try{
        if(!event.isTrusted||!navigator.userActivation?.isActive)throw Error('請直接按此按鈕複製。');
        if(!window.isSecureContext||!navigator.clipboard?.writeText)throw Error('目前環境不提供安全剪貼簿；可展開摘要手動選取。');
        await navigator.clipboard.writeText(content.value);
        feedback.textContent='已複製宿主審查摘要；尚待獨立技術審查。';feedback.dataset.state='success';
      }catch(error){
        feedback.textContent='未複製：'+(error.name==='NotAllowedError'?'剪貼簿權限遭拒或環境限制，請檢查瀏覽器權限或手動選取摘要。':error.message);feedback.dataset.state='error';
      }finally{copy.disabled=false;}
    };
    section.append(copy,feedback,details);return section;
  }
  function evidence(card,title,content){
    const details=node('details');details.className='controlled-evidence';details.append(node('summary',title),node('pre',content));card.append(details);
  }
  async function demo(job,card){
    const data=await api('demo',{id:job.id});
    const dialog=node('dialog'),close=node('button','關閉隔離體驗'),status=node('p','此框架無同來源權限、網路、表單、彈出視窗或主機工具。生成範例內的複製控制尚未驗證通過；請使用外層「複製宿主審查摘要」。');
    dialog.className='controlled-demo';dialog.setAttribute('aria-label','隔離工程結果體驗');close.type='button';
    status.setAttribute('role','status');close.onclick=()=>dialog.close();
    const frame=node('iframe');frame.title='隔離工程結果卡';frame.setAttribute('sandbox','allow-scripts');frame.referrerPolicy='no-referrer';
    const received=node('textarea');received.readOnly=true;received.setAttribute('aria-label','實際複製的生成範例摘要');received.hidden=true;
    const nonce=document.body.dataset.demoNonce;
    if(!/^[a-f0-9]{48}$/.test(nonce||''))throw Error('隔離框架政策未確認；未執行生成程式。');
    const safeJob=JSON.stringify({...data.job,source:undefined,events:undefined,replacement:undefined}).replaceAll('<','\\u003c');
    // This harness, its CSP and the clipboard bridge are independent of the candidate.
    frame.srcdoc=`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'nonce-${nonce}'; style-src 'unsafe-inline'; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-src 'none'; worker-src 'none'"><style>html{color-scheme:light}body{margin:0;padding:16px;font:16px/1.6 system-ui;color:#18252b;background:white;overflow-wrap:anywhere}*{box-sizing:border-box;min-width:0}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:18rem;overflow:auto}button,textarea{max-width:100%;font:inherit}button{white-space:normal;margin:6px 0;padding:8px}details{margin:12px 0}summary{cursor:pointer}</style><body data-pilot-enabled="true"><div hidden><button id="chat-send"></button><textarea id="chat-question"></textarea><p id="chat-notice"></p></div><main id="result"></main><script nonce="${nonce}">
      const pending=new Map();let sequence=0;
      Object.defineProperty(navigator,'clipboard',{value:{writeText(text){return new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});parent.postMessage({kind:'eng01-copy',id,text},'*');});}}});
      addEventListener('message',e=>{if(e.source!==parent||e.data?.kind!=='eng01-copy-result')return;const p=pending.get(e.data.id);if(!p)return;pending.delete(e.data.id);e.data.ok?p.resolve():p.reject(Error('剪貼簿寫入失敗'));});
      const script=document.createElement('script');script.nonce=${JSON.stringify(nonce)};script.textContent=new TextDecoder().decode(Uint8Array.from(atob(${JSON.stringify(data.source_base64)}),c=>c.charCodeAt(0)));document.body.append(script);
      document.getElementById('result').append(window.NexusPilot.card(${safeJob}));
    <\/script>`;
    const listener=async event=>{
      if(event.source!==frame.contentWindow||event.data?.kind!=='eng01-copy')return;
      const {text,id}=event.data;
      let ok=false;
      if(typeof text==='string'&&text.length<=6000&&navigator.userActivation.isActive
          &&text.includes(job.goal)&&text.includes(job.source.target)&&text.includes('尚待獨立技術審查')
          &&text.includes('node --check')&&text.includes(String(job.tests.exitCode))){
        try{await navigator.clipboard.writeText(text);received.value=text;received.hidden=false;status.textContent='本次生成範例摘要已寫入剪貼簿；其內容與功能仍尚待獨立技術審查。';ok=true;}
        catch{status.textContent='剪貼簿寫入失敗；沒有宣稱已複製。';}
      }else status.textContent='摘要缺少真實工作／驗證內容，或不是使用者操作；沒有寫入剪貼簿。';
      frame.contentWindow.postMessage({kind:'eng01-copy-result',id,ok},'*');
    };
    addEventListener('message',listener);
    dialog.onclose=()=>{removeEventListener('message',listener);dialog.remove();};
    dialog.append(close,status,reviewControls(data.job),frame,received);document.body.append(dialog);dialog.showModal();
  }
  window.NexusControlled={state:chat=>api('state',{chat}),savedTurn(turn,chat,jobs,changed,current){
    if(turn.status!=='complete'||turn.model.startsWith('NEXUS ·'))return null;
    const existing=jobs.find(job=>job.source_turn===turn.id);
    const button=node('button',existing?'查看受控修改 · '+existing.state:'從這則需求預覽固定範例修改');
    button.type='button';button.className='text-button chat-source-link';
    button.onclick=async()=>{
      if(button.disabled||!current())return;
      button.disabled=true;
      try{const job=await api('preview',{chat,turn:turn.id});if(current())await changed(job);}
      catch(e){if(current())el('chat-notice').textContent=e.message;}
      finally{button.disabled=false;}
    };
    return button;
  },card(job){
    const card=node('section');card.className='chat-work-card controlled-card';card.dataset.controlledJob=job.id;card.dataset.state=job.state;
    card.append(node('h3','受控程式修改 · '+job.state),node('p',job.summary),node('p','需求：'+job.goal));
    card.append(node('p',(job.state==='COMPLETED'?'實際修改目標：':'預定目標：')+job.source.root+'/'+job.source.target));
    card.append(node('p',job.tests?'主機靜態語法檢查 · Exit '+(job.tests.exitCode??'未確認')+' · '+(job.tests.command||'命令未確認'):'主機驗證：尚未執行。預定命令：'+job.validation));
    card.append(node('p','尚待獨立技術審查。靜態語法檢查不代表功能測試通過；生成範例的複製功能尚未驗證通過。'));
    if(job.state!=='PREVIEW')card.append(reviewControls(job));
    if(job.state==='PREVIEW'){
      card.append(node('p','只分享下列來源快照及需求；模型無 Shell／檔案／瀏覽器工具。主機只替換此檔案。靜態檢查不執行生成程式；功能體驗另以無網路、無同來源權限的框架隔離。批准限本帳戶、本對話、本來源及 30 分鐘內使用一次。'));
      evidence(card,'核對本次完整來源',job.source.text);
      const label=node('label'),box=node('input');box.type='checkbox';box.style.width='auto';label.append(box,document.createTextNode(' 我已核對具體來源，只批准此單一檔案修改與固定靜態驗證'));card.append(label);
      const confirm=node('button','批准受控程式修改');confirm.type='button';confirm.disabled=true;box.onchange=()=>confirm.disabled=!box.checked;
      confirm.onclick=async()=>{confirm.disabled=true;try{await api('confirm',{id:job.id,token:job.token,authority:'CONTROLLED_CODE_REPLACEMENT'});card.querySelector('p').textContent='已消耗本次批准；不會自動重送。';}catch(e){card.querySelector('p').textContent=e.message;}};card.append(confirm);
    }
    if(job.state!=='PREVIEW')evidence(card,'原始來源快照',job.source.text);
    if(job.tests)evidence(card,'完整主機驗證紀錄',JSON.stringify(job.tests,null,2));
    if(job.diff)evidence(card,'完整實際差異',job.diff);
    evidence(card,'來源身分與原生事件',JSON.stringify({source:{...job.source,text:undefined},final_sha256:job.final_sha256,thread:job.thread_id,turn:job.turn_id,tools_enabled:job.tools_enabled,events:job.events||[]},null,2));
    if(job.state==='COMPLETED'){
      card.append(node('p','尚待獨立技術審查。正常聊天頁保留已提交的原始前端；生成檔案只能在隔離框架體驗。'));
      const button=node('button','開啟隔離範例（功能待驗證）');button.type='button';button.onclick=async()=>{button.disabled=true;try{await demo(job,card);}catch(e){card.append(node('p',e.message));}finally{button.disabled=false;}};card.append(button);
    }
    return card;
  }};
  addEventListener('DOMContentLoaded',()=>{
    const button=node('button','預覽受控程式修改');button.type='button';button.className='secondary-button';
    button.onclick=async()=>{button.disabled=true;try{const chat=window.companionChatSelection?.();if(!chat)throw Error('請先選取原對話。');await api('preview',{chat,question:el('chat-question').value});el('chat-notice').textContent='受控工程預覽已保存；請核對來源與影響並親自批准。';}catch(e){el('chat-notice').textContent=e.message;}finally{button.disabled=false;}};
    el('chat-send').before(button);
  });
})();
