'use strict';

function agentInitial(role){return ({scout:'S',analyst:'A',ideator:'I',skeptic:'R',planner:'P'})[role]||'·';}
function agentTraceInitial(label){return agentInitial(['scout','analyst','ideator','skeptic','planner'].find(role=>label.toLowerCase().includes(role)));}
function teamList(items){return items?.length?`<ul>${items.map(item=>`<li>${e(item)}</li>`).join('')}</ul>`:'';}
function teamReportBody(role,output){
  if(role==='scout')return `<p>${e(output.summary)}</p>${output.papers.map(p=>`<div class="team-report-item"><strong>${e(p.id)}${output.selected_ids.includes(p.id)?' · 带入假设生成':''}</strong><p>${e(p.relevance)}</p><p>摘要依据：${e(p.evidence)}</p><p class="muted">证据范围：${e(p.limitations)}</p></div>`).join('')}<strong>待补充证据</strong>${teamList(output.gaps)}`;
  if(role==='analyst')return `<p>${e(output.summary)}</p><p class="tiny muted">${({shared_summary:'已获准共享的项目摘要',unshared:'未共享项目，仅评估领域与资源约束',no_project:'未导入项目，仅评估领域与资源约束'})[output.scope]||''}</p>${output.findings.map(f=>`<div class="team-report-item"><code>${e(f.file)}:${e(f.line)}</code><p>${e(f.observation)}</p></div>`).join('')}<strong>研究落点</strong>${teamList(output.opportunities)}<strong>风险</strong>${teamList(output.risks)}<strong>分析范围</strong>${teamList(output.limitations)}`;
  if(role==='ideator')return output.ideas.map(c=>`<div class="team-report-item"><strong>${e(c.id)} · ${e(c.title)}</strong><p>${e(c.hypothesis)}</p><p>${e(c.experiment)}</p><p>指标：${e(c.metrics)}</p><p>风险：${e(c.risk)}</p><small>引用：${e(c.refs.join(', '))}</small></div>`).join('');
  if(role==='skeptic')return `<p>${e(output.summary)}</p><p>${output.verdict==='revise'?'需要修订':'可以继续规划实验；假设仍待验证'}</p>${output.issues.map(issue=>`<div class="team-report-item"><strong>${e(issue.idea_id)} · ${e(issue.severity)}</strong><p>${e(issue.problem)}</p><p>修改要求：${e(issue.requested_change)}</p></div>`).join('')}`;
  if(role==='planner')return `<p>${e(output.summary)}</p>${output.unresolved_issues?.length?'<div class="callout warm">仍有审查问题未解决；以下计划需先处理这些问题。</div>':''}${output.experiments.map(plan=>`<div class="team-report-item"><strong>${e(plan.idea_id)} · 实验计划</strong><p>基线：${e(plan.baseline)}</p><strong>消融</strong>${teamList(plan.ablations)}<strong>指标</strong>${teamList(plan.metrics)}<p>失败判据：${e(plan.failure_criteria)}</p><strong>执行步骤</strong>${teamList(plan.steps)}</div>`).join('')}<strong>限制</strong>${teamList(output.limitations)}`;
  return '';
}
function teamReports(run){
  if(!run.agent_runs?.length)return '';
  return `<section class="agent-reports"><div class="section-title"><h3>Agent 协作产出</h3><span class="tiny muted">${run.agent_runs.length} 次模型调用 · ${run.revision_count||0} 轮修订</span></div><p class="small-copy muted">文献分析与项目判断会传递给假设生成、审查和实验规划。展开查看各次产出与输入来源。</p>${run.review_status==='needs_revision'?'<div class="callout warm">复审仍提出修改要求。请处理未解决的问题，再开展实验。</div>':''}${run.agent_runs.map(message=>`<details class="panel agent-report"><summary><span class="agent-avatar">${agentInitial(message.role)}</span><strong>${e(message.name)}</strong><small>第 ${message.iteration} 次调用</small>${icon('chevron')}</summary><div class="agent-report-body"><p class="tiny muted">输入产物：${e(message.inputs.join(' → ')||'研究主题、约束与论文')}</p>${teamReportBody(message.role,message.output)}</div></details>`).join('')}</section>`;
}

function plannedExperiment(card){
  const plan=S.last_run?.agent_reports?.planner?.experiments.find(item=>item.idea_id===card?.id);
  if(!plan)return '';
  return `\n\nPlanner 实验计划：\n基线：${plan.baseline}\n消融：${plan.ablations.join('；')}\n指标：${plan.metrics.join('；')}\n失败判据：${plan.failure_criteria}\n步骤：\n${plan.steps.map((step,index)=>`${index+1}. ${step}`).join('\n')}${S.last_run.review_status==='needs_revision'?'\n注意：复审仍有未解决问题，需先处理。':''}`;
}
