'use strict';

let clientProject,clientResearch,scopeEpoch=0,selectionGeneration=0,scopeChanging=false;
let projectFilter='active';
function scopeHeaders(){return clientProject===undefined?{}:{'X-RP-Project':clientProject||'-','X-RP-Research':clientResearch||'-'};}
function viewTitle(){return ({projects:'项目',overview:'研究流程'})[view]||views.find(item=>item[0]===view)?.[1]||'研究任务';}
function ensureProjectView(){
  if(['settings','projects','reader'].includes(view))return;
  view=S.project?'overview':'projects';
}

function projectSidebar(){
  return `<button class="workspace-picker" data-action="nav" data-view="projects"><span class="workspace-icon">${icon('folder')}</span><span class="workspace-name">我的项目<small>${S.project?e(S.project.name):(S.archived_projects?.length?'选择或恢复一个项目':'先绑定一个本机文件夹')}</small></span>${icon('chevron')}</button>
    <button class="new-research" data-action="create-project">${icon('plus')}<span>添加项目</span></button>
    <section class="project-tree" aria-label="项目"><div class="nav-section">项目</div>${(S.projects||[]).map(project=>`<div class="project-tree-group"><button class="project-tree-project ${S.project?.id===project.id?'active':''}" data-action="select-project" data-project="${project.id}" title="${e(project.path||'历史记录，待绑定文件夹')}">${icon('folder')}<span>${e(project.name)}</span></button></div>`).join('')||'<p class="sidebar-placeholder">你的项目会保存在这里</p>'}</section>`;
}
function projectsView(){
  const archived=projectFilter==='archived',projects=archived?(S.archived_projects||[]):(S.projects||[]);
  return head('PROJECTS','我的项目','每个项目对应一个文件夹，从想法出发建立研究资料。',`<button class="btn primary" data-action="create-project">${icon('plus')} 添加项目</button>`)+
    `<div class="project-filter" role="group" aria-label="项目状态">${[['active','进行中',(S.projects||[]).length],['archived','已归档',(S.archived_projects||[]).length]].map(([id,label,count])=>`<button class="btn ${projectFilter===id?'primary':''}" data-action="project-filter" data-filter="${id}" aria-pressed="${projectFilter===id}">${label} <span>${count}</span></button>`).join('')}</div>
    <div class="project-cards">${projects.map(project=>`<article class="panel project-card"><${archived?'div':'button'} class="project-card-main" ${archived?'':`type="button" data-action="select-project" data-project="${project.id}"`}><span class="project-card-icon">${icon('folder')}</span><h2>${e(project.name)}</h2><p class="project-path">${e(project.path||'待绑定文件夹')}</p><div class="button-row"><span class="tag ${archived||project.bound?'gray':'warm'}">${archived?'已归档':project.bound?'已绑定文件夹':'待确认归属'}</span><span class="tiny muted">${archived?'研究资料保留':'进入研究流程'}</span></div></${archived?'div':'button'}><div class="project-card-actions">${archived?`<span class="tiny muted">归档于 ${date(project.archived_at)}</span><button class="btn small" data-action="restore-project" data-project="${project.id}" aria-label="恢复项目 ${e(project.name)}">恢复项目</button>`:`<button class="btn text" data-action="archive-project" data-project="${project.id}" aria-label="归档项目 ${e(project.name)}">归档项目</button>`}</div></article>`).join('')|| (archived?`<section class="panel project-first"><h2>还没有归档项目</h2><p>归档后的项目会保留研究任务和记录，可随时恢复。</p></section>`:(S.archived_projects||[]).length?`<section class="panel project-first"><h2>暂无进行中的项目</h2><p>你可以创建新项目，或恢复已归档的项目。</p><button class="btn" data-action="project-filter" data-filter="archived">查看归档项目</button></section>`:`<section class="panel project-first"><span class="project-card-icon">${icon('folder')}</span><h2>先绑定你的研究文件夹</h2><p>选择用于保存论文与研究说明的文件夹，从一个想法开始探索。</p><button class="btn primary" data-action="create-project">${icon('plus')} 创建第一个项目</button><p class="tiny muted">模型连接在账号设置中统一管理，可在绑定项目后配置。</p></section>`)}</div>`;
}
function projectOverview(){
  if(flowRunVisible())return flowRunView();
  if(!S.project)return projectsView();
  return head('RESEARCH',e(S.project.name),'从一个想法开始，在你的项目文件夹中建立研究。',`<button class="btn text" data-action="archive-project" data-project="${S.project.id}">归档项目</button>`)+`<p class="project-path">${e(S.project.local_path||'请先绑定项目文件夹')}</p>`+(S.project.bound?flowView():`<section class="panel"><button class="btn primary" data-action="bind-project">选择项目文件夹</button></section>`);
}

function projectModal(bind=false){
  const record=S.project_record;
  modal(`<div class="eyebrow">${bind?'BIND FOLDER':'NEW PROJECT'}</div><h2>${bind?'为历史记录确认文件夹':'创建项目并绑定文件夹'}</h2><p>绑定文件夹后，描述你的想法并逐步确认研究方向。可以使用代码项目，也可以选择空文件夹。</p><form id="bind-project-form"><label class="form-label" for="bound-project-name">项目名称</label><input class="field full" id="bound-project-name" maxlength="80" value="${bind?e(record.name):''}" ${bind?'disabled':''} placeholder="例如：我的论文项目"><label class="form-label" for="bound-project-path">项目文件夹</label><div class="folder-picker-row"><input class="field full" id="bound-project-path" value="${bind?e(record.suggested_path||''):''}" placeholder="选择文件夹，或粘贴文件夹路径" required><button class="btn" id="choose-project-folder" type="button">${icon('folder')} 选择文件夹</button></div><p id="folder-picker-status" class="tiny muted" role="status" aria-live="polite">选择一个已有文件夹作为项目上下文。</p><label class="check-label"><input id="bound-project-consent" type="checkbox" required>允许研途只读扫描这个文件夹中的代码、README 和配置</label><p class="tiny muted">不修改文件夹中的源文件。模型是否接收项目摘要，在研究任务中另行选择。</p><button class="btn primary" type="submit">${icon('folder')} ${bind?'确认绑定':'创建项目'}</button></form>`);
  const form=$('#bind-project-form'),picker=$('#choose-project-folder'),status=$('#folder-picker-status');
  const pathInput=form.querySelector('#bound-project-path'),nameInput=form.querySelector('#bound-project-name');
  const browser=document.createElement('section');browser.className='folder-browser';browser.hidden=true;browser.setAttribute('aria-label','浏览项目文件夹');
  status.after(browser);
  let generation=0;
  async function loadFolder(path){
    const request=++generation;
    browser.hidden=false;browser.innerHTML='<p class="tiny muted" role="status">正在读取文件夹…</p>';
    try{
      const result=await api('/api/projects/folders',path?{path}:{});
      if(!form.isConnected||request!==generation)return;
      browser.innerHTML=`<div class="folder-browser-toolbar">${result.shortcuts.map(item=>`<button class="btn small" type="button" data-folder-path="${e(item.path)}">${e(item.name)}</button>`).join('')}${result.parent?`<button class="btn small" type="button" data-folder-path="${e(result.parent)}">上一级</button>`:''}</div><p class="project-path">${e(result.path)}</p><div class="folder-browser-list">${result.folders.map(item=>`<button class="folder-browser-item" type="button" data-folder-path="${e(item.path)}" aria-label="打开文件夹 ${e(item.name)}">${icon('folder')}<span>${e(item.name)}</span>${icon('chevron')}</button>`).join('')||'<p class="tiny muted">此文件夹没有子文件夹，可以直接选用。</p>'}</div><div class="folder-browser-actions"><button class="btn" type="button" data-folder-cancel>取消</button><button class="btn primary" type="button" data-folder-select>选用当前文件夹</button></div>`;
      browser.querySelectorAll('[data-folder-path]').forEach(button=>button.onclick=()=>loadFolder(button.dataset.folderPath));
      browser.querySelector('[data-folder-cancel]').onclick=()=>{generation++;browser.hidden=true;status.textContent='已取消选择，原有填写内容保持不变。';picker.focus();};
      browser.querySelector('[data-folder-select]').onclick=()=>{
        pathInput.value=result.path;
        if(!bind&&!nameInput.value.trim())nameInput.value=result.name;
        generation++;browser.hidden=true;status.textContent='已选择文件夹；创建项目时将进行只读扫描。';
        pathInput.dispatchEvent(new Event('input',{bubbles:true}));picker.focus();
      };
    }catch(error){
      if(!form.isConnected||request!==generation)return;
      browser.innerHTML='<p class="tiny muted" role="alert"></p><button class="btn small" type="button">返回个人文件夹</button>';
      browser.querySelector('p').textContent=error.message;browser.querySelector('button').onclick=()=>loadFolder();
    }
  }
  picker.onclick=()=>{
    if(browser.hidden){status.textContent='打开子文件夹后，点击“选用当前文件夹”。';loadFolder(pathInput.value.trim()||undefined);}
    else{generation++;browser.hidden=true;status.textContent='选择一个已有文件夹作为项目上下文。';}
  };
  $('#bind-project-form').onsubmit=async event=>{
    event.preventDefault();const data={name:$('#bound-project-name').value,path:$('#bound-project-path').value,consent:$('#bound-project-consent').checked};
    if(bind)data.id=record.id;
    const button=event.target.querySelector('button[type=submit]');button.disabled=true;
    try{await changeResearchScope(bind?'/api/projects/bind':'/api/projects/create',data,'overview');closeModal();}
    catch(error){toast(error.message,true);if(button.isConnected)button.disabled=false;}
  };
}
function researchModal(){
  if(!S.project)return projectModal();
  if(!S.project.bound)return projectModal(true);
  modal(`<div class="eyebrow">NEW RESEARCH</div><h2>在 ${e(S.project.name)} 中新建研究</h2><p class="project-path">${e(S.project.local_path)}</p><form id="new-research-form"><label class="form-label" for="research-title">研究任务名称</label><input class="field full" id="research-title" maxlength="120" placeholder="写下这次要研究的问题" required><p class="tiny muted">这次调研的论文、Agent 产出、对话、笔记和环境记录会保存在这个任务中。</p><button class="btn primary" type="submit">${icon('plus')} 创建研究任务</button></form>`);
  $('#new-research-form').onsubmit=async event=>{
    event.preventDefault();const title=$('#research-title').value,button=event.target.querySelector('button[type=submit]');button.disabled=true;
    try{await changeResearchScope('/api/research/create',{title},'home');closeModal();}
    catch(error){toast(error.message,true);if(button.isConnected)button.disabled=false;}
  };
}
function resetResearchView(){
  setWatch(false);clearTimeout(readerResizeTimer);
  selected=new Set();chat=[];plan=null;envResult=null;busy='';shareProject=false;
  clearTimeout(toastTimer);$('#toast').className='';$('#toast').textContent='';
  taskDraft=topicDraft=constraintDraft=searchDraft=chatDraft='';taskMode='research';notesFilter='all';renderedView=null;
}
async function changeResearchScope(path,data,target){
  const generation=++selectionGeneration,previous={project:clientProject,research:clientResearch,state:S,view};
  scopeChanging=true;
  try{
    const selection=await api(path,data);
    if(generation!==selectionGeneration)return;
    scopeEpoch++;clientProject=selection.project_id;clientResearch=selection.research_id;
    resetResearchView();
    if($('#view'))$('#view').innerHTML='<div class="empty" role="status">正在打开项目与研究任务…</div>';
    await state();
    topicDraft=S.last_run?.topic||S.research?.title||'';
    taskDraft=S.research?.title||'';constraintDraft=S.last_run?.constraints||'';searchDraft=S.search?.query||'';
    restoreSelection();view=target;ensureProjectView();render();
  }catch(error){
    if(!accountLocked){
      clientProject=previous.project;clientResearch=previous.research;S=previous.state;view=previous.view;
      ensureProjectView();render();
    }
    throw error;
  }finally{if(generation===selectionGeneration)scopeChanging=false;}
}
async function projectManagerAction(action,button){
  if(await flowAction(action,button))return true;
  if(action==='project-filter'){projectFilter=button.dataset.filter;render();return true;}
  if(action==='archive-project'){
    await changeResearchScope('/api/projects/archive',{id:button.dataset.project},'projects');
    toast('项目已归档，可在“已归档”中恢复');return true;
  }
  if(action==='restore-project'){
    await changeResearchScope('/api/projects/restore',{id:button.dataset.project},'overview');
    projectFilter='active';toast('项目已恢复');return true;
  }

  if(action==='create-project'){projectModal();return true;}
  if(action==='bind-project'){projectModal(true);return true;}
  if(action==='select-project'){await changeResearchScope('/api/projects/select',{id:button.dataset.project},'overview');return true;}
  if(action==='select-research'){await changeResearchScope('/api/research/select',{id:button.dataset.research},'home');return true;}
  if(action==='new-research'){researchModal();return true;}
  return false;
}
