'use strict';
function flowView(){
  if(flowRunVisible())return flowRunView();
  const f=S.research_flow||{stage:'clarifying',turns:[],ideas:[]},last=f.turns?.at(-1),count=f.turns?.length||0;
  const steps=['梳理想法','确认方向','比较 Idea','建立研究资料'];
  const current=f.stage==='selected'?3:['ideas','researching','needs_input'].includes(f.stage)?2:f.stage==='confirmed'?1:0;
  let body=`<ol class="flow-steps">${steps.map((label,i)=>`<li class="${i<=current?'active':''}"><span>${i+1}</span>${label}</li>`).join('')}</ol>`;
  if(f.stage==='selected'){
    const idea=f.ideas.find(i=>i.id===f.selected);
    return body+`<section class="panel"><span class="tag">已选定研究方向</span><h2>${e(idea?.title)}</h2><p class="flow-copy">${e(idea?.hypothesis)}</p><h3>已保存到项目文件夹</h3><ul class="flow-files">${(f.files||[]).map(p=>`<li>${e(p)}</li>`).join('')}</ul><button class="btn" data-action="nav" data-view="reader">打开论文阅读器</button></section>`;
  }
  if(f.stage==='needs_input'||f.stage==='researching'){
    const c=f.coordination||{},canContinue=!(c.next_step==='search'&&!c.pending_queries?.length);
    return body+`<section class="panel"><h2>${f.stage==='needs_input'?'研究需要你的决定':'继续上次的研究'}</h2><p class="flow-copy">${e(c.message||'已完成的分析和文献会保留，从尚未完成的步骤继续。')}</p>${f.review?.summary?`<h3>当前审查意见</h3><p class="flow-copy">${e(f.review.summary)}</p>`:''}${(f.review?.issues||[]).map(i=>`<p class="flow-copy">${e(i.problem)}<br>下一步：${e(i.requested_change)}</p>`).join('')}${f.curation?.gaps?.length?`<p class="flow-copy">${e(f.curation.gaps.join('；'))}</p>`:''}<div class="button-row">${f.stage==='needs_input'?(canContinue?'<button class="btn primary" data-action="flow-continue" data-busy>再推进一轮</button>':''):'<button class="btn primary" data-action="flow-analyze" data-busy>继续研究</button>'}<button class="btn" data-action="flow-refine">调整研究方向</button></div>${f.stage==='needs_input'&&canContinue?'<p class="tiny muted">继续后最多增加一轮修订、三次检索和四次分析；仍有问题时再次交由你决定。</p>':''}</section>`;
  }
  if(f.stage==='ideas')return body+`<div class="button-row"><p class="flow-copy">比较候选方向及推荐阅读，选择你希望继续研究的 Idea。</p><button class="btn text" data-action="flow-refine">调整研究方向</button></div><div class="flow-ideas">${f.ideas.map((idea,index)=>`<section class="panel"><span class="tag">方向 ${index+1}</span><h2>${e(idea.title)}</h2><p class="flow-copy">${e(idea.hypothesis)}</p><h3>如何开始验证</h3><p class="flow-copy">${e(idea.experiment)}</p><p class="muted small-copy">${e(idea.risk)}</p><h3>推荐阅读 · ${idea.refs.length} 篇</h3><div class="flow-readings">${idea.refs.map(id=>{const p=f.papers.find(x=>x.id===id);return `<article><span class="tag gray">${p.reading_type==='classic'?'基础阅读':'前沿研究'}</span> <span class="tiny muted">${e(p.published)}</span><a href="${e(p.url)}" target="_blank" rel="noopener noreferrer">${e(p.title)}</a><p>${e(idea.reading_reasons[id])}</p>${idea.reading_plan?.find(x=>x.paper_id===id)?.reading_goal?`<p>阅读目标：${e(idea.reading_plan.find(x=>x.paper_id===id).reading_goal)}</p>`:''}</article>`;}).join('')}</div><button class="btn primary" data-action="flow-choose" data-idea="${e(idea.id)}">选择这个 Idea</button></section>`).join('')}</div><details class="panel"><summary>研究建议与待核验事项</summary><p class="flow-copy">${e(f.review?.summary||'')}</p>${f.curation?.gaps?.length?`<p class="flow-copy">${e(f.curation.gaps.join('；'))}</p>`:''}</details>`;
  body+=`<section class="panel flow-composer"><h2>${last?'继续梳理你的想法':'你想探索什么？'}</h2><p class="flow-copy">${last?e(last.summary):'从一个兴趣、观察或尚不确定的问题开始。我们会先了解你的意图，再逐步缩小研究范围。'}</p>${last?`<h3>${e(last.question)}</h3><div class="flow-options">${last.options.map((option,index)=>`<button class="btn" data-action="flow-option" data-index="${index}" data-busy>${e(option)}</button>`).join('')}</div>`:''}<form id="flow-prompt-form"><label class="form-label" for="flow-prompt">${last?'也可以补充自己的想法':'描述你的想法'}</label><textarea class="field full" id="flow-prompt" maxlength="4000" rows="5" placeholder="例如：我对机器人如何在新环境中学习很感兴趣，但还没有具体的研究问题…" required></textarea><div class="button-row"><button class="btn primary" type="submit" data-busy ${S.model.ready?'':'disabled'}>${last?'继续梳理':'开始探索'}</button>${!S.model.ready?'<button class="btn" type="button" data-action="nav" data-view="settings">连接科研模型</button>':''}</div></form></section>`;
  if(f.can_confirm||(f.can_confirm===undefined&&count>=3)||f.stage==='confirmed')body+=`<section class="panel"><h3>当前研究方向</h3><p class="flow-copy">${e(f.direction)}</p>${f.stage==='confirmed'?'<button class="btn primary" data-action="flow-analyze" data-busy>生成候选 Idea 与阅读清单</button>':'<button class="btn primary" data-action="flow-confirm" data-busy>确认方向</button>'}</section>`;
  return body;
}
const flowPromptDrafts=new Map();
function bindFlowForms(){const form=$('#flow-prompt-form'),input=$('#flow-prompt');if(form){input.value=flowPromptDrafts.get(clientProject)||'';input.oninput=()=>flowPromptDrafts.set(clientProject,input.value);form.onsubmit=event=>{event.preventDefault();flowTurn(input.value);};}}
async function flowTurn(message){const project=clientProject;if(!S.model.ready)return toast('请先连接科研模型');await work('正在梳理你的想法…',async()=>{await job('/api/flow/turn',{message});flowPromptDrafts.delete(project);await state();render();});}
async function flowAction(action,button){
  if(action==='flow-run-dismiss'){flowRun=null;clearInterval(flowRunTimer);render();return true;}
  if(action==='flow-run-retry'){const {path,data}=flowRun;await work('正在重新连接研究…',async()=>{await job(path,data);await state();render();});return true;}
  if(action==='flow-option'){const f=S.research_flow;await flowTurn(f.turns.at(-1).options[Number(button.dataset.index)]);return true;}
  if(action==='flow-refine'){
    modal(`<h2>调整研究方向</h2><p class="flow-copy">补充你想改变的问题或条件，已完成的协作记录会保留。</p><form id="flow-refine-form"><label class="form-label" for="flow-refine-text">补充想法</label><textarea class="field full" id="flow-refine-text" rows="5" maxlength="4000" required></textarea><button class="btn primary" type="submit">重新梳理</button></form>`);
    $('#flow-refine-form').onsubmit=event=>{event.preventDefault();const message=$('#flow-refine-text').value;flowPromptDrafts.set(clientProject,message);closeModal();flowTurn(message);};return true;
  }
  if(action==='flow-continue'){await work('继续推进研究…',async()=>{await job('/api/flow/continue',{});await state();render();});return true;}
  if(action==='flow-confirm'){await work('确认研究方向…',async()=>{await api('/api/flow/confirm',{});await state();render();});return true;}
  if(action==='flow-analyze'){await work('正在整理候选方向和推荐阅读…',async()=>{await job('/api/flow/analyze',{});await state();render();});return true;}
  if(action==='flow-choose'){
    const idea=S.research_flow.ideas.find(i=>i.id===button.dataset.idea);
    modal(`<h2>采用这个研究方向</h2><h3>${e(idea.title)}</h3><p class="flow-copy">将在当前项目的 reference/ 中保存 ${idea.refs.length} 篇论文PDF及阅读清单，并生成研究 README。已有 README 会保留，研究说明另存为 README.researchpilot.md。</p><p class="project-path">${e(S.project.local_path)}</p><button class="btn primary" data-action="flow-save" data-idea="${e(idea.id)}" data-busy>保存到项目文件夹</button>`);return true;
  }
  if(action==='flow-save'){await work('正在保存研究资料…',async()=>{await job('/api/flow/select',{idea_id:button.dataset.idea});await state();closeModal();render();toast('研究资料已保存到项目文件夹');});return true;}
  if(action==='reading-notes'){
    modal(`<h2>我的阅读笔记</h2>${(S.reading_notes||[]).map(n=>`<section class="panel"><h3>${e(n.title)}</h3><p class="flow-copy">${e(n.body.source_text)}</p><p class="flow-copy">${e(n.body.translation)}</p></section>`).join('')||'<p class="flow-copy">保存双语阅读后，可以在这里随时查看。</p>'}`);return true;
  }
  return false;
}

// The running view only advances on progress reported by the server.
let flowRun=null,flowRunTimer=null;
function flowRunPlan(path){
  if(['/api/flow/analyze','/api/flow/continue'].includes(path))return {title:'让线索，彼此相遇。',subtitle:'从文献中寻找联系，让研究方向有据可循。',label:'研究协作',steps:[['检索文献','寻找近期研究与基础阅读'],['分析证据','梳理文献价值与尚待回答的问题'],['构思方向','形成可验证的候选 Idea'],['独立审查','检查可行性与证据边界'],['阅读策划','独立编排阅读顺序、理由与目标']]};
  if(path==='/api/flow/select')return {title:'把下一步，留在这里。',subtitle:'将选定的方向，整理成可以继续研究的资料。',label:'资料整理',steps:[['保存研究资料','下载论文，整理阅读清单与研究说明']]};
  return {title:'让想法，逐渐清晰。',subtitle:'从你的表达出发，找到值得继续追问的方向。',label:'意图澄清',steps:[['梳理研究意图','理解你的兴趣、问题与研究条件']]};
}
function flowRunIndex(path,progress){
  if(!['/api/flow/analyze','/api/flow/continue'].includes(path))return 0;
  if(progress.includes('阅读策划'))return 4;
  if(progress.includes('审查Agent'))return 3;
  if(progress.includes('文献研究Agent')||progress.includes('文献Agent'))return 1;
  if(progress.includes('选题生成Agent')||progress.includes('研究Agent'))return 2;
  return 0;
}
function flowRunVisible(){return flowRun&&flowRun.project===clientProject&&view==='overview';}
function flowRunStart(path,data){
  if(!path.startsWith('/api/flow/'))return;
  if(path==='/api/flow/select')closeModal();
  clearInterval(flowRunTimer);
  const f=S.research_flow;
  flowRun={path,data:JSON.parse(JSON.stringify(data||{})),project:clientProject,started:Date.now(),index:0,status:'queued',progress:'正在准备研究上下文',error:'',seed:data?.message||f?.direction||S.project?.name||'',round:(f?.turns?.length||0)+1};
  if(view==='overview'){render();if($('.page-scroll'))$('.page-scroll').scrollTop=0;$('#research-run-heading')?.focus({preventScroll:true});}
  flowRunTimer=setInterval(flowRunTick,1000);
  return flowRun;
}
function flowRunProgress(path,progress,status,owner=flowRun){
  if(!flowRun||flowRun!==owner||flowRun.path!==path)return;
  flowRun.status=status;flowRun.progress=progress||'研究正在进行';
  const index=flowRunIndex(path,flowRun.progress);
  if(index!==flowRun.index){flowRun.index=index;if(flowRunVisible())render();}
  flowRunTick();
}
function flowRunEnd(path,error,owner=flowRun){
  if(!flowRun||flowRun!==owner||flowRun.path!==path)return;
  clearInterval(flowRunTimer);flowRunTimer=null;
  if(error){flowRun.status='error';flowRun.ended=Date.now();flowRun.error=error.message||String(error);if(flowRunVisible())render();}
  else flowRun=null;
}
function flowRunTick(){
  if(!flowRunVisible())return;
  const clock=$('#research-run-clock'),status=$('#research-run-status'),pill=$('#research-run-pill');
  const seconds=Math.floor(((flowRun.ended||Date.now())-flowRun.started)/1000);
  if(clock)clock.textContent=String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0');
  if(status)status.textContent=flowRun.status==='error'?flowRun.error:flowRun.progress;
  if(pill)pill.textContent=flowRun.status==='error'?'需要重试':flowRun.status==='queued'?'准备中':'进行中';
}
function flowRunView(){
  const r=flowRun,plan=flowRunPlan(r.path),failed=r.status==='error';
  return `<section class="research-run ${failed?'has-error':''}" aria-label="研究运行状态">
    <div class="research-run-header"><span class="research-run-label"><i></i>${e(plan.label)}</span><span class="research-run-meta">${r.path==='/api/flow/turn'?'第 '+r.round+' 轮探索':'研究进行时'}</span></div>
    <div class="research-run-grid"><div class="research-run-scene">
      <div class="research-run-illustration" aria-hidden="true"><div class="run-halo"></div><svg class="run-orbits" viewBox="0 0 520 340" fill="none"><defs><linearGradient id="run-ink" x1="70" y1="50" x2="450" y2="300" gradientUnits="userSpaceOnUse"><stop stop-color="#b5a881"/><stop offset=".5" stop-color="#508e88"/><stop offset="1" stop-color="#b8cfc4"/></linearGradient></defs><g class="run-orbit-outer"><ellipse cx="260" cy="170" rx="204" ry="78" transform="rotate(-24 260 170)"/><ellipse cx="260" cy="170" rx="184" ry="113" transform="rotate(36 260 170)"/><ellipse cx="260" cy="170" rx="156" ry="128" transform="rotate(-52 260 170)"/></g><g class="run-orbit-inner"><ellipse cx="260" cy="170" rx="112" ry="48" transform="rotate(-24 260 170)"/><ellipse cx="260" cy="170" rx="104" ry="73" transform="rotate(42 260 170)"/></g><path class="run-path" d="M83 264C144 238 142 104 260 170S381 194 445 80"/><circle class="run-node node-a" cx="111" cy="232" r="5"/><circle class="run-node node-b" cx="402" cy="102" r="4"/><circle class="run-node node-c" cx="341" cy="267" r="3"/><circle cx="260" cy="170" r="27" class="run-core-ring"/><circle cx="260" cy="170" r="7" class="run-core"/></svg><span class="run-coordinate coordinate-a">01 / ${r.path==='/api/flow/select'?'整理':'探索'}</span><span class="run-coordinate coordinate-b">${String(r.index+1).padStart(2,'0')} / ${plan.steps.length===1?'思考':'连接'}</span></div>
      <h2 id="research-run-heading" tabindex="-1">${failed?'线索暂时停在这里。':e(plan.title)}</h2><p class="research-run-subtitle">${failed?'你的研究方向会保留，可以重试这一步。':e(plan.subtitle)}</p>
      <div class="research-run-seed"><span>始于你的想法</span><p>${e(r.seed.slice(0,160))}${r.seed.length>160?'…':''}</p></div>
    </div><aside class="research-run-progress" aria-label="研究进度"><div class="run-progress-heading"><span>正在推进</span><span id="research-run-pill" class="run-status-pill">${failed?'需要重试':r.status==='queued'?'准备中':'进行中'}</span></div>
      <ol class="run-stage-list">${plan.steps.map(([title,detail],i)=>`<li class="${i<r.index?'is-done':i===r.index?'is-current':''}" ${i===r.index?'aria-current="step"':''}><span class="run-stage-marker">${i<r.index?icon('check'):String(i+1).padStart(2,'0')}</span><div><strong>${e(title)}</strong><p>${e(detail)}</p>${i===r.index?'<span class="run-stage-wave" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></span>':''}</div></li>`).join('')}</ol>
      <div class="run-live-update"><span class="run-live-label">${failed?'本次状态':'当前动态'}</span><p id="research-run-status" role="status" aria-live="polite">${e(failed?r.error:r.progress)}</p></div>
      ${failed?'<div class="button-row"><button class="btn primary" data-action="flow-run-retry">重试此步骤</button><button class="btn text" data-action="flow-run-dismiss">返回研究</button></div>':'<p class="run-patience">你可以切换页面，研究会在后台继续。</p>'}
      <footer class="run-progress-footer"><span>${failed?'本次用时':'已用时'} <time id="research-run-clock" aria-hidden="true">00:00</time></span><span>${e(S.project?.name||'当前项目')}</span></footer>
    </aside></div>
  </section>`;
}
