"""Deterministic, checkpointed routing between research agents and bounded tools."""
import copy
import hashlib
import json
import urllib.error
import uuid
from .research_agents import EvidenceAgent, IdeationAgent, ReviewAgent, ReadingPlannerAgent, queries
from .store import now


DEFAULT_BUDGET=dict(model_calls=12,search_calls=9,revisions=2)


class BudgetStop(Exception):
    pass


class ResearchCoordinator:
    def __init__(self,flow,search,progress):
        self.flow,self.search,self.progress=flow,search,progress
        self.agents={a.role:a(flow.ask) for a in (EvidenceAgent,IdeationAgent,ReviewAgent,ReadingPlannerAgent)}

    def checkpoint(self):
        return self.flow.save(self.s)

    def output(self,role):
        artifact_id=self.c['latest'].get(role)
        return next((a['output'] for a in self.s['artifacts'] if a['id']==artifact_id),None)

    def invoke(self,role,payload,inputs):
        if role in self.c['cache']:
            artifact_id=self.c['cache'][role]
            return next(a['output'] for a in self.s['artifacts'] if a['id']==artifact_id)
        if self.c['model_calls']>=self.c['budget']['model_calls']:
            raise BudgetStop('本轮研究已达到调用预算，请决定继续推进或调整方向。')
        self.c['model_calls']+=1
        self.progress(self.agents[role].name+'Agent正在分析')
        result,artifact_id=self.flow.trace_agent(self.s,self.agents[role],payload,inputs,self.c['run_id'])
        self.c['cache'][role]=self.c['latest'][role]=artifact_id
        self.checkpoint()
        return result

    def papers(self):
        # Preserve space for both recent and foundational literature in every input.
        items=self.s.get('papers',[])
        return [p for kind in ('frontier','classic') for p in [x for x in items if x['reading_type']==kind][:36]]

    def payload(self):
        return dict(direction=self.s['direction'],brief=self.s['brief'],papers=[
            {k:(p.get(k,'')[:1800] if k=='abstract' else p.get(k,'')) for k in ('id','title','abstract','published','reading_type')}
            for p in self.papers()])

    def stop(self,message):
        self.s['stage']='needs_input';self.c.update(status='needs_input',message=message)
        self.progress('等待你决定研究的下一步')
        return self.checkpoint()

    def route_back(self,target,feedback,requested_queries=None):
        self.c['next_step']=target
        self.c['feedback']=copy.deepcopy(feedback)
        invalidate={'search':('scout','ideator','reviewer','curator'),'ideation':('ideator','reviewer','curator')}[target]
        for role in invalidate:self.c['cache'].pop(role,None)
        if target=='search':
            requested=queries(requested_queries)
            self.c['pending_queries']=[q for q in requested if q.lower() not in self.c['searched_queries']]
            if not self.c['pending_queries']:
                return self.stop('现有检索主题已经检查过，请补充新的研究线索或调整方向。')
        self.c['revisions']+=1
        if self.c['revisions']>self.c['budget']['revisions']:
            return self.stop('本轮仍有未解决问题，已暂停自动修订。你可以再推进一轮，或调整研究方向。')
        self.checkpoint()
        return None

    def search_step(self):
        for query in list(self.c['pending_queries']):
            if self.c['search_calls']>=self.c['budget']['search_calls']:
                raise BudgetStop('本轮已达到检索预算，请决定是否继续补充证据。')
            self.c['search_calls']+=1
            record=dict(id=uuid.uuid4().hex,run_id=self.c['run_id'],tool='literature_search',query=query,
                        status='running',started_at=now(),input_ids=[self.c['brief_id']])
            self.s.setdefault('tool_runs',[]).append(record);self.checkpoint()
            self.progress('检索文献：'+query)
            try:
                found=self.search(query,self.flow.store)
                for p in found:
                    if not isinstance(p,dict) or not all(isinstance(p.get(k),str) and p[k] for k in ('id','title','published','reading_type')) or p['reading_type'] not in ('frontier','classic'):
                        raise ValueError('文献来源返回了不完整的题录，请重试。')
                merged={p['id']:p for p in self.s.get('papers',[])}
                merged.update({p['id']:p for p in found});self.s['papers']=list(merged.values())
                artifact_id=self.flow.add_artifact(self.s,'search',dict(query=query,papers=found),[self.c['brief_id']],self.c['run_id'])
                record.update(status='completed',finished_at=now(),artifact_id=artifact_id)
                self.c['search_artifacts'].append(artifact_id)
                self.c['searched_queries'].append(query.lower());self.c['pending_queries'].remove(query)
                self.checkpoint()
            except Exception as error:
                record.update(status='failed',finished_at=now(),error_type=type(error).__name__)
                self.checkpoint()
                if isinstance(error,(TimeoutError,urllib.error.URLError)):
                    raise ValueError('文献来源暂时无法连接，请稍后重试。已完成的步骤会保留。') from None
                raise
        self.c['next_step']='evidence';self.checkpoint()

    def run(self):
        self.s=self.flow.state()
        if self.s.get('selected'):raise ValueError('项目已经选定研究方向。')
        if self.s['stage'] not in ('confirmed','ideas','researching','needs_input'):
            raise ValueError('请先确认研究方向。')
        if self.s['stage']=='needs_input':return self.s
        self.s.setdefault('artifacts',[]);self.s.setdefault('agent_runs',[])
        self.s.setdefault('brief',dict(goal=self.s['direction'],subject=self.s['direction'],constraints='尚未明确',open_questions=['补充资源条件']))
        self.c=self.s.get('coordination')
        if self.c and self.c['status']=='completed':return self.s
        if not self.c:
            run_id=uuid.uuid4().hex
            brief_id=self.flow.add_artifact(self.s,'confirmed_brief',dict(direction=self.s['direction'],brief=self.s['brief']),[],run_id)
            self.c=dict(run_id=run_id,project_id=self.flow.project_id,status='running',next_step='search',
                        budget=dict(DEFAULT_BUDGET),model_calls=0,search_calls=0,revisions=0,cache={},latest={},
                        searched_queries=[],pending_queries=queries(self.s['queries']),search_artifacts=[],brief_id=brief_id,feedback=None,
                        direction_hash=hashlib.sha256(json.dumps(self.s['brief'],sort_keys=True,ensure_ascii=False).encode()).hexdigest())
            self.s.update(coordination=self.c,papers=[],ideas=[],review=None,curation=None)
        for record in self.s['agent_runs']+self.s.get('tool_runs',[]):
            if record.get('run_id')==self.c['run_id'] and record.get('status')=='running':
                record.update(status='interrupted',finished_at=now())
        self.s['stage']='researching';self.c.update(status='running',message='')
        self.checkpoint()
        try:
            while True:
                step=self.c['next_step']
                if step=='search':self.search_step()
                elif step=='evidence':
                    evidence=self.invoke('scout',dict(**self.payload(),requested_gaps=self.c['feedback']),[self.c['brief_id']]+self.c['search_artifacts'])
                    if evidence['status']=='needs_search':
                        stopped=self.route_back('search',evidence,evidence['queries'])
                        if stopped:return stopped
                    else:self.c['next_step']='ideation';self.checkpoint()
                elif step=='ideation':
                    previous=self.output('ideator')
                    out=self.invoke('ideator',dict(**self.payload(),evidence=self.output('scout'),feedback=self.c['feedback'],previous_ideas=previous['ideas'] if previous else []),[self.c['brief_id'],self.c['latest']['scout']]+([self.c['latest']['reviewer']] if self.c['latest'].get('reviewer') else []))
                    self.s['draft_ideas']=copy.deepcopy(out['ideas']);self.c['next_step']='review';self.checkpoint()
                elif step=='review':
                    out=self.invoke('reviewer',dict(**self.payload(),evidence=self.output('scout')['evidence'],ideas=self.s['draft_ideas'],previous_requirements=self.c['feedback']),[self.c['brief_id'],self.c['latest']['scout'],self.c['latest']['ideator']])
                    self.s['review']=copy.deepcopy(out)
                    if out['decision']=='accept':self.c['next_step']='curation';self.checkpoint()
                    else:
                        stopped=self.route_back('search' if out['decision']=='search' else 'ideation',out,out.get('queries'))
                        if stopped:return stopped
                elif step=='curation':
                    out=self.invoke('curator',dict(**self.payload(),ideas=self.s['draft_ideas'],review=self.s['review']),[self.c['brief_id'],self.c['latest']['ideator'],self.c['latest']['reviewer']]+self.c['search_artifacts'])
                    self.s['curation']=copy.deepcopy(out)
                    if out['decision']=='search':
                        stopped=self.route_back('search',out,out['queries'])
                        if stopped:return stopped
                    else:
                        lists={item['idea_id']:item['readings'] for item in out['lists']}
                        ideas=copy.deepcopy(self.s['draft_ideas'])
                        for idea in ideas:
                            idea['reading_plan']=lists[idea['id']]
                            idea['refs']=[p['paper_id'] for p in idea['reading_plan']]
                            idea['reading_reasons']={p['paper_id']:p['reason'] for p in idea['reading_plan']}
                        self.s.update(stage='ideas',ideas=ideas)
                        self.c.update(status='completed',next_step='user_selection',message='')
                        return self.checkpoint()
                else:raise ValueError('研究阶段状态无效，请调整方向后重试。')
        except BudgetStop as error:return self.stop(str(error))
        except Exception:
            self.c['status']='paused';self.checkpoint();raise

    @staticmethod
    def extend(flow):
        state=flow.state();c=state.get('coordination')
        if state['stage']!='needs_input' or not c:raise ValueError('当前研究无需追加推进。')
        if c['next_step']=='search' and not c['pending_queries']:
            raise ValueError('请先调整研究方向，提供新的检索线索。')
        for key,amount in dict(model_calls=4,search_calls=3,revisions=1).items():c['budget'][key]+=amount
        c.update(status='running',message='');state['stage']='researching'
        flow.save(state)
        return state
