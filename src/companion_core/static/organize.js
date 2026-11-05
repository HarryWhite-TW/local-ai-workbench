/* Selected uploads and preview-bound copies stay in the current conversation. */
(() => {
  const el=id=>document.getElementById(id), make=(tag,value)=>{const n=document.createElement(tag);n.textContent=value;return n;};
  let context=null, generation=0, uploading=false, requestId=null;
  const working=new Set(), feedback=new Map();
  const titles={ANALYZING:'正在讀文件，幫你找合適的分類',PREVIEW:'先看看，這樣分類好嗎？',
    COMPLETED:'整理副本已備妥',FAILED:'這次沒能完成分類',UNKNOWN:'還需要確認分析結果',
    CANCEL_REQUESTED:'正在確認是否已停止',CANCELLED:'已停止，沒有產生副本'};
  async function api(action,body){
    const response=await fetch('/api/chat/organize-'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Companion-UI':'1'},body:JSON.stringify(body)});
    const data=await response.json();if(!response.ok)throw Error(data.error||'文件整理目前不可用。');return data;
  }
  function active(){return context!==null;}
  function reset(){
    window.NexusConversation?.organizeClosed();
    generation++;context=null;requestId=null;
    if(el('organize-panel'))el('organize-panel').hidden=true;
    if(el('chat-form'))el('chat-form').dataset.organizing='false';
    el('organize-open')?.setAttribute('aria-expanded','false');
    if(el('organize-files'))el('organize-files').value='';
    el('organize-selection')?.replaceChildren();
    if(el('organize-notice'))el('organize-notice').textContent='';
    if(el('chat-question'))el('chat-question').readOnly=false;
  }
  function open(value){
    if(uploading)return;
    reset();context=value;el('organize-panel').hidden=false;
    el('chat-form').dataset.organizing='true';
    el('organize-open').setAttribute('aria-expanded','true');
    el('organize-start').disabled=true;el('organize-choose').disabled=false;
    window.NexusConversation?.organizeOpened();
    el('organize-files').click();
  }
  function button(label,action){
    const b=make('button',label);b.type='button';b.className='secondary-button';b.onclick=action;return b;
  }
  function card(job,refresh,valid){
    const box=make('section','');box.className='organize-card';box.dataset.organization=job.id;box.dataset.state=job.state;
    box.append(make('h3',titles[job.state]||job.label));
    const status=make('p',feedback.get(job.id)||job.error||'');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
    if(job.plan){
      const groups=new Map();
      for(const p of job.plan){if(!groups.has(p.category))groups.set(p.category,[]);groups.get(p.category).push(p);}
      box.append(make('p',job.documents.length+' 份文件 · '+groups.size+' 個分類'));
      for(const [category,items] of groups){
        const group=make('div','');group.className='organize-group';
        group.append(make('h4',category+' · '+items.length+' 份'),make('p',items.map(p=>p.name).join('、')));
        const details=make('details',''),list=make('ul','');details.append(make('summary','查看分類依據'));
        for(const p of items){
          const item=make('li','');item.append(make('strong',p.name),make('p',p.reason),make('blockquote',p.evidence),make('small','副本位置：'+p.destination));list.append(item);
        }
        details.append(list);group.append(details);box.append(group);
      }
    }else box.append(make('p',job.documents.length+' 份文件 · '+job.documents.map(d=>d.name).join('、')));
    box.append(status);
    const controls=[];
    function control(label,action){const b=button(label,action);controls.push(b);b.disabled=working.has(job.id);box.append(b);return b;}
    async function download(expectedHash){
      if(!valid())return;
      const result=await api('download',{id:job.id});if(!valid())return;
      const raw=Uint8Array.from(atob(result.content),c=>c.charCodeAt(0));
      const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw)),b=>b.toString(16).padStart(2,'0')).join('');
      if(hash!==result.sha256||hash!==expectedHash)throw Error('下載內容身分不符，未提供檔案。');
      if(!valid())return;
      const url=URL.createObjectURL(new Blob([raw],{type:'application/zip'})),a=make('a','');
      a.href=url;a.download=result.name;box.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
      feedback.set(job.id,'已送出 ZIP 下載。副本已保存，之後也能回到這裡重新下載。');
    }
    async function act(action,body){
      if(!valid()||working.has(job.id))return;
      working.add(job.id);controls.forEach(b=>b.disabled=true);
      let saved=job.state==='COMPLETED',changed=false;
      status.textContent=action==='confirm'?'正在建立副本並準備下載…':action==='download'?'正在準備下載…':'正在處理…';
      try{
        if(action==='download')await download(job.output_sha256);
        else{
          const result=await api(action,body);if(!valid())return;
          if(action==='confirm'){
            if(result.id!==job.id||result.state!=='COMPLETED'||!result.output_sha256)throw Error('尚未確認副本已建立，請重新讀取結果。');
            saved=true;changed=true;await download(result.output_sha256);
          }else changed=true;
        }
        if(valid())status.textContent=feedback.get(job.id)||(action==='reconcile'?'正在核對原工作，不會重送分析。':'已更新。');
      }catch(e){
        if(valid()){
          const message=saved?'副本已保存，但下載未完成：'+e.message+' 請按「下載 ZIP」重試。':e.message;
          status.textContent=message;if(saved)feedback.set(job.id,message);
        }
      }finally{
        working.delete(job.id);controls.forEach(b=>b.disabled=false);
        if(valid()&&(changed||saved))refresh();
      }
    }
    if(job.state==='PREVIEW'){
      box.append(make('p','可展開核對理由與原文。確認後只建立 ZIP 副本，不搬動或修改原始文件。'));
      const confirm=control('確認並下載 ZIP',()=>act('confirm',{id:job.id,approval:job.approval}));confirm.className='primary-button';
    }
    if(job.state==='COMPLETED'){
      box.append(make('p','原始文件保持不變；整理副本已保存於這段對話。'));
      control('下載 ZIP',()=>act('download',{id:job.id}));
      const details=make('details','');details.className='organize-identity';details.append(make('summary','檢查副本身分'),make('code',job.output_sha256));box.append(details);
    }
    if(['ANALYZING','CANCEL_REQUESTED'].includes(job.state)){
      box.append(make('p','分類完成後會在這裡顯示預覽，確認前不會建立副本。'));
      const stop=control(job.state==='CANCEL_REQUESTED'?'等待停止確認':'停止分析',()=>act('stop',{id:job.id}));
      stop.disabled=job.state==='CANCEL_REQUESTED'||working.has(job.id);
    }
    if(job.state==='UNKNOWN'){
      box.append(make('p','還沒有可確認的分類，也沒有建立副本。可核對原工作；不會自動重送。'));
      if(job.thread_id&&job.turn_id)control('核對分析結果',()=>act('reconcile',{id:job.id}));
    }
    if(job.state==='FAILED')box.append(make('p','沒有建立副本。可檢查所選文件後，從輸入區重新開始。'));
    window.NexusConversation?.organizationCard(box,job);
    return box;
  }
  async function submit(){
    if(uploading||!context?.valid())return;
    const ctx=context,mine=generation,files=[...el('organize-files').files];
    const question=el('chat-question').value.trim()||'請依文件實際內容分類，提供分類理由與逐字原文依據；不確定的歸為待確認。';
    if(!files.length){el('organize-notice').textContent='先選擇想整理的文件。';return;}
    if(files.length>12||files.some(f=>f.size>131072)||files.reduce((n,f)=>n+f.size,0)>524288){
      el('organize-notice').textContent='文件超過數量或容量限制，請減少選取文件。';return;
    }
    uploading=true;el('organize-start').disabled=true;el('organize-choose').disabled=true;
    el('chat-question').readOnly=true;el('organize-notice').textContent='正在讀取你選定的文件…';
    try{
      const snapshots=[];
      for(const f of files){
        const bytes=new Uint8Array(await f.arrayBuffer());
        let binary='';for(const b of bytes)binary+=String.fromCharCode(b);
        snapshots.push({name:f.name,content:btoa(binary)});
      }
      if(mine!==generation||!ctx.valid())return;
      requestId=requestId||crypto.randomUUID();
      const result=await api('start',{id:requestId,chat:ctx.chat,account:ctx.account,workspace:ctx.workspace,question,files:snapshots});
      if(mine!==generation||!ctx.valid())return;
      reset();await ctx.started(result);
    }catch(e){if(mine===generation)el('organize-notice').textContent=e.message;}
    finally{uploading=false;el('organize-start').disabled=el('organize-files').files.length===0;el('organize-choose').disabled=false;el('chat-question').readOnly=false;}
  }
  document.addEventListener('DOMContentLoaded',()=>{
    if(!el('organize-panel'))return;
    el('organize-close').onclick=()=>{reset();el('chat-question').focus();};
    el('organize-choose').onclick=()=>{if(!uploading)el('organize-files').click();};
    el('organize-files').onchange=()=>{
      requestId=null;el('organize-selection').replaceChildren();
      for(const f of el('organize-files').files){const chip=make('span',f.name+' · '+Math.ceil(f.size/1024)+' KB');chip.className='organize-file';el('organize-selection').append(chip);}
      el('organize-start').disabled=el('organize-files').files.length===0;
      el('organize-choose').textContent=el('organize-files').files.length?'重新選擇文件':'選擇文件';el('organize-notice').textContent='';
    };
    el('chat-question').addEventListener('input',()=>{requestId=null;});
    el('organize-start').onclick=submit;
  });
  window.NexusOrganize={open,reset,card,active,submit};
})();
