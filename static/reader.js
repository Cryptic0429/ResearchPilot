'use strict';
// PDF bytes and unsaved translation history stay in this browser session.
const readerState={paper:null,pdf:null,pdfTask:null,documentEpoch:0,fileName:'',page:1,zoom:1,text:'',target:'zh-CN',glossary:'',
  append:false,result:null,history:[],source:{kind:'paste',title:'手动输入'},
  pending:false,error:'',pdfError:'',generation:0,loading:false,renderTask:null,textLayer:null,queuedKey:null,activeKey:null,scheduledKey:null};
let pdfLibraryPromise,readerAutoTimer,readerResizeObserver,readerResizeTimer;

function readerView(){
  const r=readerState,p=r.paper;
  return head('READ & TRANSLATE','论文阅读','左侧读原文，右侧看译文。划选一段，让阅读继续。',
    `<div class="button-row"><button class="btn" data-action="reading-notes">我的阅读笔记</button><label class="btn" for="reader-file">${icon('upload')} 打开本地 PDF</label></div>`)+`
    <input id="reader-file" class="hidden" type="file" accept="application/pdf,.pdf">
    <div class="reader-layout">
      <section class="reader-document" aria-label="论文原文">
        <div class="reader-document-head"><span class="tag">${r.pdf?'本地 PDF':p?'文献摘要':'阅读与翻译'}</span><h2>${e(r.fileName||p?.title||'打开一篇论文，从原文开始')}</h2>
          ${p?`<p class="muted tiny">${e(p.authors)} · ${e(p.published)}</p><a class="text-link" href="https://arxiv.org/pdf/${encodeURIComponent(p.id)}" target="_blank" rel="noopener noreferrer">打开论文 PDF ${icon('external')}</a>`:''}</div>
        ${r.pdf?`<div class="reader-toolbar"><button class="btn small" data-action="reader-prev" ${r.page<=1?'disabled':''} aria-label="上一页">←</button>
          <label class="reader-page-label"><input class="field" id="reader-page" type="number" min="1" max="${r.pdf.numPages}" value="${r.page}" aria-label="PDF 页码"> / ${r.pdf.numPages}</label>
          <button class="btn small" data-action="reader-next" ${r.page>=r.pdf.numPages?'disabled':''} aria-label="下一页">→</button>
          <select class="field" id="reader-zoom" aria-label="PDF 缩放">${[.75,1,1.25,1.5,2].map(z=>`<option value="${z}" ${z===r.zoom?'selected':''}>${Math.round(z*100)}%</option>`).join('')}</select>
          <button class="btn text" data-action="reader-page-text">翻译本页文字</button></div>
          <div id="reader-pdf-status" role="status" class="reader-pdf-status">正在呈现第 ${r.page} 页…</div><div id="reader-pdf-scroll"><div id="reader-pdf-page"></div></div>`:
          p?`<div id="reader-original" class="reader-original" tabindex="0" aria-label="可划选的论文摘要"><h3>Abstract / 摘要</h3><p>${e(p.abstract)}</p></div><div class="reader-source-foot">当前内容为论文摘要；阅读全文请下载 PDF 后打开。</div>`:
          `<div class="reader-welcome">${icon('book')}<h3>把英文文献放在手边</h3><p>打开本地 PDF 后划选文字，或在右侧粘贴英文段落。</p><label class="btn primary" for="reader-file">选择 PDF 文件</label><small>PDF 在浏览器内读取，最大 50 MB。</small></div>`}
        ${r.pdfError?`<p class="reader-error" role="alert">${e(r.pdfError)}</p>`:''}
      </section>
      <aside class="reader-side" aria-label="论文翻译面板">
        <section class="panel reader-translation-panel"><div class="panel-head"><h3>${icon('spark')} 阅读翻译</h3><select class="field" id="reader-target" aria-label="翻译目标语言"><option value="zh-CN" ${r.target==='zh-CN'?'selected':''}>英文 → 中文</option><option value="en" ${r.target==='en'?'selected':''}>中文 → 英文</option></select></div>
          <p class="reader-engine">当前引擎：${e(modelConnection('translation').provider||'翻译服务')} · ${e(modelConnection('translation').model||'')}${!modelConnection('translation').ready?' · 未连接':''}</p>
          ${!modelConnection('translation').ready?'<div class="callout warm">翻译需要单独配置文献翻译连接。<button class="btn text" data-action="nav" data-view="settings">前往设置翻译连接 →</button></div>':''}
          <div class="reader-selection-options"><span class="tag">划选即译</span><label class="check-label"><input id="reader-append" type="checkbox" ${r.append?'checked':''}>追加选区（可跨页）</label></div>
          <label class="form-label" for="reader-text">待译原文 <span id="reader-text-count">${r.text.length} / 5000</span></label>
          <textarea class="field full" id="reader-text" maxlength="5000" placeholder="在左侧划选文字，或在这里粘贴、修改原文…">${e(r.text)}</textarea>
          <details class="reader-glossary" ${r.glossary?'open':''}><summary>术语约定</summary><textarea id="reader-glossary" class="field full" maxlength="1000" aria-label="术语约定" placeholder="填写需要统一的术语及对应译法">${e(r.glossary)}</textarea></details>
          <p class="reader-footnote">划选或编辑原文后自动翻译，待译文字与术语约定发送至 ${e(modelConnection('translation').provider||'已配置的模型服务')}。</p>
          <div class="button-row reader-translate-actions"><button class="btn text" data-action="reader-clear">清空</button></div>
          <div id="reader-translation-output" aria-live="polite"></div>
          <p class="reader-footnote">译文由模型生成，请对照原文核验公式与术语。扫描件需先做 OCR；当前不含整篇自动翻译或译文 PDF 导出。</p>
        </section>
        <section class="panel reader-history-panel"><div class="panel-head"><h3>本次阅读记录</h3><span id="reader-history-count" class="count">${r.history.length}</span></div><div id="reader-history"></div><p class="tiny muted">最近 20 条暂存于本页面，刷新后清空。重要段落请保存到阅读笔记。</p></section>
      </aside>
    </div>`;
}

function readerKey(){const r=readerState;return JSON.stringify([r.text.trim(),r.target,r.glossary.trim(),modelConnection('translation').base,modelConnection('translation').model,modelConnection('translation').style,modelConnection('translation').provider,r.source]);}
function readerCapture(){const r=readerState;if($('#reader-text'))r.text=$('#reader-text').value;if($('#reader-glossary'))r.glossary=$('#reader-glossary').value;}
function readerOutput(){
  const r=readerState,box=$('#reader-translation-output');if(!box)return;
  const current=r.result?.key===readerKey();
  box.innerHTML=r.pending?'<div class="reader-status" role="status"><span class="spinner"></span> 正在翻译，可继续阅读原文…</div>':
    r.error?`<p class="reader-error" role="alert">${e(r.error)}</p><button class="btn text" data-action="reader-retry">重试</button>`:
    current?`<div class="reader-result"><div class="reader-result-head"><strong>${r.target==='en'?'英文译文':'中文译文'}</strong><span>${e(r.result.provider)} · ${e(r.result.model)}</span></div><p>${e(r.result.translation)}</p><div class="button-row"><button class="btn small" data-action="reader-save">${icon('plus')} 保存双语笔记</button><button class="btn text" data-action="reader-copy">复制译文</button></div></div>`:
    '<div class="reader-result-empty">译文会显示在这里，与左侧原文对照阅读。</div>';
  if($('#reader-text-count'))$('#reader-text-count').textContent=r.text.length+' / 5000';
  if($('#reader-history-count'))$('#reader-history-count').textContent=r.history.length;
  const history=$('#reader-history');if(history)history.innerHTML=r.history.length?r.history.map((h,i)=>`<button class="reader-history-item" data-action="reader-history" data-index="${i}"><span>${e(h.source.title)}${h.source.pages?.length?' · 第 '+h.source.pages.join('、')+' 页':''}</span><strong>${e(h.source_text.slice(0,95))}</strong><small>${e(h.translation.slice(0,95))}</small></button>`).join(''):'<p class="context-empty">翻译过的段落会出现在这里。</p>';
}
function readerSchedule(wait=450){
  const r=readerState;clearTimeout(readerAutoTimer);r.scheduledKey=null;r.queuedKey=null;
  if(view!=='reader'||!modelConnection('translation').ready||!r.text.trim()||r.text.length>5000)return;
  const key=readerKey();if(r.result?.key===key||r.activeKey===key)return;
  if(r.pending){r.queuedKey=key;return;}
  r.scheduledKey=key;
  readerAutoTimer=setTimeout(()=>{r.scheduledKey=null;readerTranslate();},wait);
}
function readerChanged(){readerState.error='';readerOutput();readerSchedule(650);}
function readerSetText(text,source){
  const r=readerState;clearTimeout(readerAutoTimer);
  const sameSource=source.kind===r.source.kind&&source.title===r.source.title;
  const value=r.append&&sameSource&&r.text.trim()?r.text.trim()+'\n\n'+text:text;
  if(value.length>5000){toast('单次最多 5000 字符，请缩小选区或分段翻译。',true);return false;}
  if(r.append&&r.text.trim()&&source.kind===r.source.kind&&source.title===r.source.title){source={...source,pages:[...new Set([...(r.source.pages||[]),...(source.pages||[])])]};}
  r.text=value;r.source=source;r.error='';if($('#reader-text'))$('#reader-text').value=value;readerOutput();
  readerSchedule();
  return true;
}
function readerSelection(){
  const selection=window.getSelection(),root=$('#reader-pdf-page')||$('#reader-original');
  if(!selection||selection.isCollapsed||!root?.contains(selection.anchorNode)||!root.contains(selection.focusNode))return;
  const text=selection.toString().trim();if(!text)return;
  const r=readerState;readerSetText(text,r.pdf?{kind:'pdf',title:r.fileName,pages:[r.page],paper_id:r.paper?.id||null}:{kind:'abstract',title:r.paper.title,paper_id:r.paper.id});
}
function bindReader(){
  const r=readerState,scheduledKey=r.scheduledKey;clearTimeout(readerAutoTimer);
  readerResizeObserver?.disconnect();clearTimeout(readerResizeTimer);
  // A new app render replaces the canvas, so cancel work tied to the old DOM.
  r.generation++;r.renderTask?.cancel();r.textLayer?.cancel();
  if(view!=='reader'){r.scheduledKey=null;r.queuedKey=null;return;}
  $('#reader-file').onchange=event=>{const file=event.target.files[0];if(file)readerOpenPDF(file);};
  $('#reader-text').oninput=event=>{r.text=event.target.value;readerChanged();};
  $('#reader-glossary').oninput=event=>{r.glossary=event.target.value;readerChanged();};
  $('#reader-target').onchange=event=>{r.target=event.target.value;readerChanged();};
  $('#reader-append').onchange=event=>r.append=event.target.checked;
  const original=$('#reader-original');if(original){original.onpointerup=()=>setTimeout(readerSelection,0);original.onkeyup=readerSelection;}
  if(r.pdf){
    $('#reader-page').onchange=event=>readerPage(Number(event.target.value));$('#reader-zoom').onchange=event=>{r.zoom=Number(event.target.value);readerDrawPDF();};readerDrawPDF();
    const scroll=$('#reader-pdf-scroll');let width=scroll.clientWidth;
    readerResizeObserver=new ResizeObserver(()=>{if(Math.abs(scroll.clientWidth-width)<2)return;width=scroll.clientWidth;clearTimeout(readerResizeTimer);readerResizeTimer=setTimeout(()=>readerDrawPDF(),160);});
    readerResizeObserver.observe(scroll);
  }
  readerOutput();
  if(scheduledKey===readerKey())readerSchedule();
}
async function readerOpenPaper(paper){
  capture();const r=readerState;r.documentEpoch++;r.generation++;r.renderTask?.cancel();r.textLayer?.cancel();await r.pdfTask?.destroy();r.pdfTask=null;
  r.pdf=null;r.fileName='';r.paper=paper;r.page=1;r.text=paper.abstract||'';r.result=null;r.error='';r.pdfError='';r.queuedKey=null;r.source={kind:'abstract',title:paper.title,paper_id:paper.id};
  view='reader';render();readerSchedule();
}
async function readerPDFLibrary(){
  if(!pdfLibraryPromise)pdfLibraryPromise=import('/vendor/pdfjs/pdf.min.mjs').then(lib=>{lib.GlobalWorkerOptions.workerSrc='/vendor/pdfjs/pdf.worker.min.mjs';return lib;}).catch(err=>{pdfLibraryPromise=null;throw err;});
  return pdfLibraryPromise;
}
async function readerOpenPDF(file){
  const r=readerState;if(r.loading)return;
  if(file.size>50*1024*1024){toast('PDF 最大 50 MB，请选择较小的文件。',true);return;}
  r.loading=true;const epoch=++r.documentEpoch;let task;
  try{
    toast('正在本地打开 PDF…');
    const lib=await readerPDFLibrary(),bytes=new Uint8Array(await file.arrayBuffer());
    task=lib.getDocument({data:bytes,cMapUrl:'/vendor/pdfjs/cmaps/',cMapPacked:true,standardFontDataUrl:'/vendor/pdfjs/standard_fonts/',wasmUrl:'/vendor/pdfjs/wasm/',isEvalSupported:false});
    // Password prompts are explicit; unsupported encrypted files fail without uploading.
    const doc=await task.promise;
    if(epoch!==r.documentEpoch){await task.destroy();return;}
    r.generation++;r.renderTask?.cancel();r.textLayer?.cancel();await r.pdfTask?.destroy();r.pdf=doc;r.pdfTask=task;
    r.fileName=file.name;r.page=1;r.zoom=1;r.paper=null;r.pdfError='';r.text='';r.result=null;r.error='';r.queuedKey=null;r.source={kind:'pdf',title:file.name,pages:[1]};
    if(view==='reader'){render();toast('PDF 已在本地打开，划选文字即可准备翻译。');}
  }catch(err){await task?.destroy();toast(err.name==='PasswordException'?'此 PDF 已加密，请先解锁后再打开。':'PDF 打开失败，请检查文件是否完整。'+err.message,true);}
  finally{r.loading=false;}
}
async function readerPage(page){const r=readerState;if(!Number.isInteger(page)||page<1||page>r.pdf.numPages){$('#reader-page').value=r.page;return;}readerCapture();r.page=page;render();}
async function readerDrawPDF(){
  const r=readerState,container=$('#reader-pdf-page'),scroll=$('#reader-pdf-scroll');if(!container||!r.pdf)return;
  const generation=++r.generation,doc=r.pdf,pageNumber=r.page;r.renderTask?.cancel();r.textLayer?.cancel();
  try{
    const lib=await readerPDFLibrary(),page=await doc.getPage(pageNumber);if(generation!==r.generation||!container.isConnected)return;
    const base=page.getViewport({scale:1}),scale=Math.min(1.6,Math.max(.35,(scroll.clientWidth-36)/base.width))*r.zoom,viewport=page.getViewport({scale});
    container.replaceChildren();container.style.width=viewport.width+'px';container.style.height=viewport.height+'px';container.style.setProperty('--total-scale-factor',viewport.scale);
    const canvas=document.createElement('canvas'),ratio=Math.min(window.devicePixelRatio||1,2);canvas.width=Math.ceil(viewport.width*ratio);canvas.height=Math.ceil(viewport.height*ratio);canvas.style.width=viewport.width+'px';canvas.style.height=viewport.height+'px';canvas.setAttribute('aria-label','PDF 第 '+pageNumber+' 页');container.append(canvas);
    const task=page.render({canvasContext:canvas.getContext('2d'),viewport,transform:ratio===1?null:[ratio,0,0,ratio,0,0]});r.renderTask=task;await task.promise;
    if(generation!==r.generation||!container.isConnected)return;
    const content=await page.getTextContent();if(generation!==r.generation||!container.isConnected)return;
    const layer=document.createElement('div');layer.className='textLayer';container.append(layer);const textLayer=new lib.TextLayer({textContentSource:content,container:layer,viewport});r.textLayer=textLayer;await textLayer.render();
    if(generation!==r.generation||!container.isConnected)return;
    container.onpointerup=()=>setTimeout(readerSelection,0);container.onkeyup=readerSelection;container.tabIndex=0;
    $('#reader-pdf-status').textContent=content.items.some(item=>item.str?.trim())?'划选原文即可自动翻译，译文显示在阅读翻译面板。':'本页没有可提取文字，可能是扫描页；请先进行 OCR，或在右侧手动输入。';
  }catch(err){if(generation!==r.generation||err.name==='RenderingCancelledException'||err.name==='AbortException')return;const status=$('#reader-pdf-status');if(status)status.textContent='本页呈现失败：'+err.message;}
}
async function readerTranslate(){
  readerCapture();const r=readerState;clearTimeout(readerAutoTimer);
  r.scheduledKey=null;
  if(r.pending){readerSchedule();return;}
  if(!modelConnection('translation').ready||!r.text.trim()){readerOutput();return;}
  if(r.text.length>5000){toast('单次最多 5000 字符，请分段翻译。',true);return;}
  const epoch=clientWorkspace,key=readerKey(),source=JSON.parse(JSON.stringify(r.source)),data={text:r.text,target:r.target,glossary:r.glossary,consent:true};
  if(r.result?.key===key){readerOutput();return;}
  r.queuedKey=null;r.activeKey=key;r.pending=true;r.error='';readerOutput();
  try{
    const start=await api('/api/reader/translate',data);let result;
    for(let i=0;i<750;i++){if(epoch!==clientWorkspace)return;const state=await api('/api/jobs/'+start.job_id);if(state.status==='error')throw Error(state.error);if(state.status==='done'){result=state.result;break;}await delay(800);}
    if(epoch!==clientWorkspace)return;
    if(!result)throw Error('翻译仍在后台运行，请稍后重试。');
    const entry={...result,key,source,input_text:data.text};r.history.unshift(entry);r.history=r.history.slice(0,20);
    if(key===readerKey())r.result=entry;
  }catch(err){if(epoch===clientWorkspace){if(key===readerKey())r.error=err.message;else toast('上一段翻译失败：'+err.message,true);}}
  finally{if(epoch===clientWorkspace){r.pending=false;r.activeKey=null;readerOutput();if(r.queuedKey===readerKey())readerSchedule(100);else r.queuedKey=null;}}
}
async function readerAction(action,button){
  if(!action.startsWith('reader-')&&action!=='read-paper'&&action!=='read-saved-paper')return false;
  const r=readerState;
  if(action==='read-paper'){await readerOpenPaper(S.search.papers[Number(button.dataset.index)]);return true;}
  if(action==='read-saved-paper'){const p=S.notes.find(n=>n.id===button.dataset.id)?.body;if(p)await readerOpenPaper(p);return true;}
  if(action==='reader-retry')await readerTranslate();
  if(action==='reader-clear'){r.text='';r.result=null;r.error='';r.queuedKey=null;r.scheduledKey=null;clearTimeout(readerAutoTimer);$('#reader-text').value='';readerOutput();}
  if(action==='reader-prev')await readerPage(r.page-1);
  if(action==='reader-next')await readerPage(r.page+1);
  if(action==='reader-page-text'){
    const doc=r.pdf,pageNumber=r.page,content=await(await doc.getPage(pageNumber)).getTextContent();
    if(doc!==r.pdf)return true;
    const text=content.items.map(item=>(item.str||'')+(item.hasEOL?'\n':' ')).join('').trim();
    if(!text)toast('本页没有文字，扫描页需先做 OCR。',true);
    else readerSetText(text,{kind:'pdf',title:r.fileName,pages:[pageNumber]});
  }
  if(action==='reader-save'&&r.result?.key===readerKey()){
    const {key,input_text,...note}=r.result;await api('/api/reader/notes',{title:'双语阅读：'+note.source.title,body:note});S.reading_notes=(await api('/api/state')).reading_notes;toast('已保存到阅读笔记');
  }
  if(action==='reader-copy'&&r.result?.key===readerKey()){try{await navigator.clipboard.writeText(r.result.translation);toast('译文已复制');}catch{toast('复制失败，请选中译文手动复制。',true);}}
  if(action==='reader-history'){
    const h=r.history[Number(button.dataset.index)];if(h){r.text=h.input_text;r.target=h.target;r.glossary=h.glossary;r.source=h.source;r.error='';r.result={...h,key:readerKey()};render();}
  }
  return true;
}
