/* Trusted host UI. Generated source executes only in an opaque sandbox frame. */
(() => {
  if(document.body.dataset.controlledCode!=='true')return;
  const el=id=>document.getElementById(id),node=(tag,text='')=>{const n=document.createElement(tag);n.textContent=text;return n;};
  async function api(action,body){const r=await fetch('/api/chat/code-'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify(body)});const v=await r.json();if(!r.ok)throw Error(v.error||'受控工程未確認。');return v;}
  async function demo(job,card){
    const data=await api('demo',{id:job.id});
    const dialog=node('dialog'),close=node('button','關閉隔離體驗'),status=node('p','此框架無同來源權限、網路、表單、彈出視窗或主機工具。剪貼簿由外層受控轉接。');
    status.setAttribute('role','status');close.onclick=()=>dialog.close();
    const frame=node('iframe');frame.title='隔離工程結果卡';frame.setAttribute('sandbox','allow-scripts');frame.referrerPolicy='no-referrer';frame.style.cssText='width:80vw;height:65vh;background:white;color:black';
    const received=node('textarea');received.readOnly=true;received.setAttribute('aria-label','實際複製的審查摘要');received.style.cssText='width:100%;height:8em';
    const nonce=document.body.dataset.demoNonce;
    if(!/^[a-f0-9]{48}$/.test(nonce||''))throw Error('隔離框架政策未確認；未執行生成程式。');
    const safeJob=JSON.stringify({...data.job,source:undefined,events:undefined,replacement:undefined}).replaceAll('<','\\u003c');
    // This harness, its CSP and the clipboard bridge are independent of the candidate.
    frame.srcdoc=`<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'nonce-${nonce}'; style-src 'unsafe-inline'; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-src 'none'; worker-src 'none'"><body data-pilot-enabled="true"><div hidden><button id="chat-send"></button><textarea id="chat-question"></textarea><p id="chat-notice"></p></div><main id="result"></main><script nonce="${nonce}">
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
        try{await navigator.clipboard.writeText(text);received.value=text;status.textContent='已將隔離卡片產生的摘要寫入剪貼簿。尚待獨立技術審查。';ok=true;}
        catch{status.textContent='剪貼簿寫入失敗；沒有宣稱已複製。';}
      }else status.textContent='摘要缺少真實工作／驗證內容，或不是使用者操作；沒有寫入剪貼簿。';
      frame.contentWindow.postMessage({kind:'eng01-copy-result',id,ok},'*');
    };
    addEventListener('message',listener);
    dialog.onclose=()=>{removeEventListener('message',listener);dialog.remove();};
    dialog.append(close,status,frame,received);document.body.append(dialog);dialog.showModal();
  }
  window.NexusControlled={state:chat=>api('state',{chat}),card(job){
    const card=node('section');card.className='chat-work-card';card.dataset.controlledJob=job.id;card.dataset.state=job.state;
    card.append(node('h3','受控程式修改 · '+job.state),node('p',job.summary),node('p',job.goal));
    card.append(node('p','固定目標：'+job.source.root+'/'+job.source.target),node('p','來源 HEAD：'+job.source.head+' · SHA-256：'+job.source.sha256),node('p','固定驗證：'+job.validation));
    if(job.source.runtime)card.append(node('p','NEXUS 執行來源：'+job.source.runtime.root+' · HEAD：'+job.source.runtime.head));
    if(job.state==='PREVIEW'){
      card.append(node('p','只分享下列來源快照及需求；模型無 Shell／檔案／瀏覽器工具。主機只替換此檔案。靜態檢查不執行生成程式；功能體驗另以無網路、無同來源權限的框架隔離。批准限本帳戶、本對話、本來源及 30 分鐘內使用一次。'));
      const source=node('details');source.open=true;source.append(node('summary','核對本次完整來源'),node('pre',job.source.text));card.append(source);
      const label=node('label'),box=node('input');box.type='checkbox';box.style.width='auto';label.append(box,document.createTextNode(' 我已核對具體來源，只批准此單一檔案修改與固定靜態驗證'));card.append(label);
      const confirm=node('button','批准受控程式修改');confirm.type='button';confirm.disabled=true;box.onchange=()=>confirm.disabled=!box.checked;
      confirm.onclick=async()=>{confirm.disabled=true;try{await api('confirm',{id:job.id,token:job.token,authority:'CONTROLLED_CODE_REPLACEMENT'});card.querySelector('p').textContent='已消耗本次批准；不會自動重送。';}catch(e){card.querySelector('p').textContent=e.message;}};card.append(confirm);
    }
    if(job.tests)card.append(node('h4','實際主機靜態驗證 · Exit '+job.tests.exitCode),node('pre',JSON.stringify(job.tests,null,2)));
    if(job.diff)card.append(node('h4','實際差異'),node('pre',job.diff));
    if(job.thread_id)card.append(node('p','原生 Thread：'+job.thread_id+' · Turn：'+(job.turn_id||'未確認')+' · 模型工具：關閉'));
    if(job.state==='COMPLETED'){
      card.append(node('p','尚待獨立技術審查。正常聊天頁保留已提交的原始前端；生成檔案只能在隔離框架體驗。'));
      const button=node('button','隔離體驗複製功能');button.onclick=async()=>{button.disabled=true;try{await demo(job,card);}catch(e){card.append(node('p',e.message));}finally{button.disabled=false;}};card.append(button);
    }
    return card;
  }};
  addEventListener('DOMContentLoaded',()=>{
    const button=node('button','預覽受控程式修改');button.type='button';button.className='secondary-button';
    button.onclick=async()=>{button.disabled=true;try{const chat=window.companionChatSelection?.();if(!chat)throw Error('請先選取原對話。');await api('preview',{chat,question:el('chat-question').value});el('chat-notice').textContent='受控工程預覽已保存；請核對來源與影響並親自批准。';}catch(e){el('chat-notice').textContent=e.message;}finally{button.disabled=false;}};
    el('chat-send').before(button);
  });
})();
