"""Five bounded research roles. Agents judge; the coordinator owns tools and routing."""
import re


def text(value):
    return isinstance(value, str) and bool(value.strip())


def queries(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 3:
        raise ValueError('请提供1–3条明确的补充检索主题。')
    result = []
    for item in value:
        if not text(item) or len(item) > 180:
            raise ValueError('检索主题格式无效。')
        words = re.findall(r'[A-Za-z0-9-]+', item)
        if not 1 <= len(words) <= 5:
            raise ValueError('英文检索主题应简短明确，每条不超过5个词。')
        result.append(' '.join(words))
    return list(dict.fromkeys(result))


class ResearchAgent:
    role = ''
    name = ''
    instruction = ''
    required = ()

    def __init__(self, call):
        self.call = call

    def run(self, payload):
        output = self.call(self.role, self.instruction, payload, self.required)
        if not isinstance(output, dict) or any(key not in output for key in self.required):
            raise ValueError(self.name + '返回内容不完整，请重试。')
        self.validate(output, payload)
        return output


class ClarifierAgent(ResearchAgent):
    role, name = 'clarifier', '意图澄清'
    required = ('summary', 'question', 'options', 'direction', 'queries', 'brief', 'ready')
    instruction = (
        '你是意图澄清Agent。从领域/兴趣、任务/对象到问题/条件逐步细化，允许模糊表达和未知条件。'
        '根据已有信息判断是否足以让用户确认，不按对话轮数判断。返回summary,question,options(3–6个字符串),'
        'direction,queries(1–3条英文短主题，每条不超过5词),brief(对象，含goal,subject,constraints字符串和'
        'open_questions字符串数组),ready(布尔)。仅在目标、对象与条件可表述时ready=true；条件未知须明确'
        '写进open_questions。具体Prompt可一轮就绪，模糊Prompt继续追问。ready不代表替用户确认。'
    )

    def validate(self, out, payload):
        if any(not text(out[k]) for k in ('summary', 'question', 'direction')):
            raise ValueError('方向说明不完整，请重试。')
        if not isinstance(out['options'], list) or not 3 <= len(out['options']) <= 6 or any(not text(x) or len(x)>500 for x in out['options']):
            raise ValueError('可选方向格式不完整，请重试。')
        out['queries'] = queries(out['queries'])
        brief = out['brief']
        if not isinstance(brief, dict) or not isinstance(out['ready'], bool):
            raise ValueError('研究意图结构不完整，请重试。')
        if any(not isinstance(brief.get(k), str) for k in ('goal','subject','constraints')) or not isinstance(brief.get('open_questions'), list) or any(not text(x) for x in brief['open_questions']):
            raise ValueError('研究条件结构不完整，请重试。')
        if out['ready'] and any(not text(brief[k]) for k in ('goal','subject','constraints')):
            raise ValueError('请先明确目标、研究对象与条件，再确认方向。')


class EvidenceAgent(ResearchAgent):
    role, name = 'scout', '文献研究'
    required = ('status','summary','evidence','evidence_gaps')
    instruction = (
        '你是文献研究Agent。基于真实题录摘要建立证据表，不只给总结。返回status(sufficient或needs_search),'
        'summary,evidence(数组，每项paper_id,relevance,contribution,limitations字符串),evidence_gaps(字符串数组)。'
        '充分时至少分析5篇且覆盖frontier与classic；较早发表不自动等于经典。证据不足时另给queries'
        '(1–3个英文短主题，每条不超过5词)，说明要补什么。不得编造来源。只据题录摘要判断，保留证据边界。'
    )

    def validate(self, out, payload):
        known = {p['id']:p for p in payload['papers']}
        if out['status'] not in ('sufficient','needs_search') or not text(out['summary']):
            raise ValueError('文献研究决定无效。')
        if not isinstance(out['evidence_gaps'],list) or any(not text(g) for g in out['evidence_gaps']):
            raise ValueError('证据缺口格式无效。')
        if not isinstance(out['evidence'],list):raise ValueError('文献证据表格式无效。')
        ids=[]
        for entry in out['evidence']:
            if not isinstance(entry,dict) or not text(entry.get('paper_id')) or entry['paper_id'] not in known or any(not text(entry.get(k)) for k in ('relevance','contribution','limitations')):
                raise ValueError('证据表引用了未知文献或缺少分析。')
            ids.append(entry['paper_id'])
        if len(set(ids)) != len(ids):raise ValueError('证据表包含重复来源。')
        if out['status']=='sufficient':
            if len(ids)<5 or {known[i]['reading_type'] for i in ids}!={'classic','frontier'}:
                raise ValueError('证据表需覆盖至少5篇文献及前沿、基础阅读。')
        else:out['queries']=queries(out.get('queries'))


class IdeationAgent(ResearchAgent):
    role, name = 'ideator', '选题生成'
    required = ('ideas',)
    instruction = (
        '你是选题生成Agent。根据已确认意图、证据表和审查反馈提出或修订2–4个候选idea。返回ideas数组，'
        '每项id,title,hypothesis,experiment,risk(非空字符串),source_ids(1–10个真实文献id)。'
        '说明可证伪假设、已有工作区别与最小验证；不要预设有效性或新颖性。收到反馈须逐项落实。'
        '此阶段仅给核心依据，不负责最终5–10篇阅读编排，后者由独立阅读策划Agent决定。'
    )

    def validate(self, out, payload):
        known={p['id'] for p in payload['papers']}
        if not isinstance(out['ideas'],list) or not 2<=len(out['ideas'])<=4:
            raise ValueError('请给出2–4个候选研究方向。')
        ids=set()
        for idea in out['ideas']:
            if not isinstance(idea,dict) or any(not text(idea.get(k)) for k in ('id','title','hypothesis','experiment','risk')) or idea['id'] in ids:
                raise ValueError('候选研究方向格式无效或编号重复。')
            sources=idea.get('source_ids')
            if not isinstance(sources,list) or not 1<=len(sources)<=10 or any(not isinstance(i,str) or i not in known for i in sources) or len(set(sources))!=len(sources):
                raise ValueError('研究假设的核心依据必须来自已核验文献池。')
            ids.add(idea['id'])


class ReviewAgent(ResearchAgent):
    role, name = 'reviewer', '独立审查'
    required = ('decision','summary','issues')
    instruction = (
        '你是独立反方审查Agent。直接核对用户研究意图、文献证据与候选假设，不接受其他Agent的自我评价。'
        '返回decision(accept/revise/search),summary,issues(数组，每项idea_id,severity(major/minor),'
        'problem,requested_change)。accept仅表示可交给用户比较，不证明创新性。重大问题必须revise或search。'
        '假设不可证伪或表述不清选revise；证据不足选search并给queries(1–3条英文短主题，每条不超过5词)。'
        '复审核对上一轮修改要求是否落实，不新增无依据的结论。'
    )

    def validate(self, out, payload):
        if out['decision'] not in ('accept','revise','search') or not text(out['summary']) or not isinstance(out['issues'],list):
            raise ValueError('审查决定格式无效。')
        ids={i['id'] for i in payload['ideas']}
        for issue in out['issues']:
            if not isinstance(issue,dict) or issue.get('idea_id') not in ids or issue.get('severity') not in ('major','minor') or any(not text(issue.get(k)) for k in ('problem','requested_change')):
                raise ValueError('审查意见缺少明确对象与修改要求。')
        if out['decision']=='revise' and not out['issues']:raise ValueError('修订决定必须说明修改要求。')
        if out['decision']=='accept' and any(i['severity']=='major' for i in out['issues']):raise ValueError('仍有重大问题，不能通过审查。')
        if out['decision']=='search':out['queries']=queries(out.get('queries'))


class ReadingPlannerAgent(ResearchAgent):
    role, name = 'curator', '阅读策划'
    required = ('decision','summary','lists','gaps')
    instruction = (
        '你是独立阅读策划Agent，不负责为idea背书。为每个idea编排5–10篇真实论文，覆盖基础与前沿工作，'
        '优先纳入相近工作和能挑战该假设的证据，未找到反证时明确写入gaps，不编造。返回decision'
        '(complete/search),summary,gaps(字符串数组),lists(每项idea_id,readings数组；每篇paper_id,reason,'
        'reading_goal,purpose字符串)。readings按阅读顺序排列，purpose为foundation/frontier/method/challenge。'
        'reason说明与idea的具体关联，reading_goal说明读完应回答什么。文献不匹配选search，并给queries'
        '(1–3条英文短主题，每条不超过5词)。不要为了凑数重复或填充无关文献。'
    )

    def validate(self, out, payload):
        if out['decision'] not in ('complete','search') or not text(out['summary']) or not isinstance(out['gaps'],list) or any(not text(g) for g in out['gaps']):
            raise ValueError('阅读策划结果格式无效。')
        if not isinstance(out['lists'],list):raise ValueError('阅读清单格式无效。')
        known={p['id']:p for p in payload['papers']};expected={i['id'] for i in payload['ideas']};seen=set()
        for entry in out['lists']:
            if not isinstance(entry,dict) or entry.get('idea_id') not in expected or entry['idea_id'] in seen or not isinstance(entry.get('readings'),list):raise ValueError('阅读清单的研究方向无效或重复。')
            seen.add(entry['idea_id']);ids=[]
            for reading in entry['readings']:
                if not isinstance(reading,dict) or not text(reading.get('paper_id')) or reading['paper_id'] not in known or any(not text(reading.get(k)) for k in ('reason','reading_goal')) or reading.get('purpose') not in ('foundation','frontier','method','challenge'):
                    raise ValueError('阅读清单包含未知来源或缺少阅读目标。')
                ids.append(reading['paper_id'])
            if len(set(ids))!=len(ids):raise ValueError('阅读清单包含重复论文。')
            if out['decision']=='complete' and (not 5<=len(ids)<=10 or {known[i]['reading_type'] for i in ids}!={'classic','frontier'}):raise ValueError('每个Idea需要5–10篇覆盖基础与前沿的推荐阅读。')
        if out['decision']=='complete' and seen!=expected:raise ValueError('阅读清单未覆盖全部候选Idea。')
        if out['decision']=='search':out['queries']=queries(out.get('queries'))


AGENT_TYPES=(ClarifierAgent,EvidenceAgent,IdeationAgent,ReviewAgent,ReadingPlannerAgent)
