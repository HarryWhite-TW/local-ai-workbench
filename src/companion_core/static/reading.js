/* Small, inert Markdown reader. No HTML interpretation, embedded media, or dependencies. */
(() => {
  const node = (tag, value) => { const n=document.createElement(tag); if(value!==undefined)n.textContent=value; return n; };
  function inline(parent, value, depth=0) {
    if(depth>5){parent.append(document.createTextNode(value));return;}
    const tokens=/(`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\n]+\*|\[[^\]\n]+\]\([^\s)]+\))/g;
    let at=0;
    for(const m of value.matchAll(tokens)) {
      parent.append(document.createTextNode(value.slice(at,m.index)));const s=m[0];let n;
      if(s.startsWith('`'))n=node('code',s.slice(1,-1));
      else if(s.startsWith('**')){n=node('strong');inline(n,s.slice(2,-2),depth+1);}
      else if(s.startsWith('*')){n=node('em');inline(n,s.slice(1,-1),depth+1);}
      else {
        const parts=/^\[([^\]]+)\]\((.+)\)$/.exec(s);
        if(/^https?:\/\//i.test(parts[2])) {
          n=node('a',parts[1]);n.href=parts[2];n.target='_blank';n.rel='noopener noreferrer';
        } else n=node('span',s);
      }
      parent.append(n);at=m.index+s.length;
    }
    parent.append(document.createTextNode(value.slice(at)));
  }
  function markdown(parent, value) {
    parent.replaceChildren();parent.classList.add('markdown');
    const lines=String(value).replace(/\r\n?/g,'\n').split('\n');let i=0;
    const boundary=s=>/^(#{1,6}\s|\s*```|\s*~~~|\s*[-*+]\s|\s*\d+\.\s|>\s?|\s*---+\s*$)/.test(s);
    const cells=s=>s.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(c=>c.trim());
    while(i<lines.length) {
      const s=lines[i];if(!s.trim()){i++;continue;}
      const fence=/^\s*(`{3,}|~{3,})(.*)$/.exec(s);
      if(fence) {
        const content=[];i++;
        while(i<lines.length&&!lines[i].trim().startsWith(fence[1]))content.push(lines[i++]);
        if(i<lines.length)i++;
        const pre=node('pre');pre.tabIndex=0;pre.setAttribute('aria-label','程式碼');pre.append(node('code',content.join('\n')));parent.append(pre);continue;
      }
      if(i+1<lines.length&&s.includes('|')&&/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[i+1])) {
        const wrap=node('div'),table=node('table'),head=node('thead'),row=node('tr'),body=node('tbody');
        wrap.className='markdown-table';wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label','表格，可水平捲動');
        for(const c of cells(s)){const th=node('th');th.scope='col';inline(th,c);row.append(th);}head.append(row);i+=2;
        while(i<lines.length&&lines[i].includes('|')&&lines[i].trim()){
          const tr=node('tr');for(const c of cells(lines[i++])){const td=node('td');inline(td,c);tr.append(td);}body.append(tr);
        }
        table.append(head,body);wrap.append(table);parent.append(wrap);continue;
      }
      const heading=/^(#{1,6})\s+(.+)$/.exec(s);
      if(heading){const h=node('h'+Math.min(6,heading[1].length+1));inline(h,heading[2]);parent.append(h);i++;continue;}
      if(/^\s*---+\s*$/.test(s)){parent.append(node('hr'));i++;continue;}
      if(/^>/.test(s)){
        const q=node('blockquote'),parts=[];while(i<lines.length&&/^>/.test(lines[i]))parts.push(lines[i++].replace(/^>\s?/,''));
        inline(q,parts.join('\n'));parent.append(q);continue;
      }
      const list=/^\s*([-*+]|\d+\.)\s+/.exec(s);
      if(list){
        const ordered=/\d/.test(list[1]),ul=node(ordered?'ol':'ul');if(ordered)ul.start=parseInt(list[1],10);
        while(i<lines.length&&(ordered?/^\s*\d+\.\s+/:/^\s*[-*+]\s+/).test(lines[i])){
          const li=node('li');inline(li,lines[i++].replace(/^\s*([-*+]|\d+\.)\s+/,''));ul.append(li);
        }parent.append(ul);continue;
      }
      const parts=[s];i++;
      while(i<lines.length&&lines[i].trim()&&!boundary(lines[i])&&!(lines[i].includes('|')&&i+1<lines.length&&/---/.test(lines[i+1])))parts.push(lines[i++]);
      const p=node('p');inline(p,parts.join('\n'));parent.append(p);
    }
  }
  const rendered=new WeakMap();
  function result(parent, value, bounded=false) {
    const key=JSON.stringify([value,bounded]);if(rendered.get(parent)===key)return;
    rendered.set(parent,key);parent.replaceChildren();parent.classList.add('result-reading');
    // Only a host-declared bounded audit gets this mechanical reading guide.
    // Original evidence remains byte-for-byte text; no model summary is generated.
    if(bounded&&value.startsWith('可信本機唯讀查核紀錄（非模型摘要）\n')){
      const files=value.split('\n').filter(s=>s.startsWith('來源：')).map(s=>s.slice(3));
      const summary=node('section');summary.className='result-summary';
      summary.append(node('span','查核結論'),node('h3','選定檔案已完成程式結構查核。'),
        node('p','已讀取 '+files.length+' 份檔案，記錄其中的程式定義與入口呼叫位置。這份結果只能證明查核時的程式結構，不能判定整個功能可用。'),node('h4','確認範圍'));
      const ul=node('ul');for(const file of files)ul.append(node('li',file));summary.append(ul,
        node('h4','仍未確認'),node('p','未執行功能測試、登入驗證或 Git／遠端查核；未修改專案。人類接受成果與 ChatGPT 技術驗收是不同決定。'),
        node('h4','這能回答原問題嗎？'),node('p','如果問題是「功能是否已接通或可正常使用」，目前證據不足。找到定義或呼叫位置，不代表使用流程已成功執行。'),
        node('h4','合理的下一步'),node('p','返回原對話，指出尚未確認的使用流程與預期行為，討論所需的功能測試或操作證據。這個查核器無法執行那些驗證；此頁也不會自動開始新工作。'),
        node('small','依本機查核紀錄整理的閱讀提示；完整內容以下方原始證據為準。'));
      const details=node('details');details.className='raw-evidence';details.append(node('summary','展開完整原始技術證據'));
      details.append(node('pre',value));parent.append(summary,details);
    } else {
      const note=node('p','以下是保存的原始成果。未提供結構化查核結論；內容中的推論不會自動成為已驗證事實。');note.className='reading-note';
      const content=node('div');markdown(content,value);parent.append(note,content);
    }
  }
  const states=Object.freeze({UNKNOWN:'執行狀態未確認',CREATED:'正在準備',RUNNING:'執行中',CANCEL_REQUESTED:'停止待確認',CANCELLED:'已確認取消',FAILED:'執行失敗',RESULT_PENDING_REVIEW:'成果等待審查',ACCEPTED:'人類已接受',REJECTED:'人類已拒絕',REVISION_REQUESTED:'已記錄調整方向'});
  window.CompanionReading={markdown,result,states};
})();
