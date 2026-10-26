"""流水线门面：把工作区与各阶段组合起来，供 CLI / HTTP 接口 / 测试统一调用。"""
from .models import Stage
from .stages import AnalysisStage, ReadingStage, ScopingStage, SelectionStage
from .workspace import ResearchWorkspace


class ResearchPipeline:
    def __init__(self, workspace, llm, searcher, translation_llm=None, git_factory=None):
        self.ws = workspace
        self.scoping = ScopingStage(workspace, llm, searcher)
        self.analysis = AnalysisStage(workspace, llm)
        kwargs = dict(git_factory=git_factory) if git_factory else {}
        self.selection = SelectionStage(workspace, llm, **kwargs)
        self.reading = ReadingStage(workspace, llm, translation_llm or llm)

    @classmethod
    def new(cls, folder, title, llm, searcher, repo_url='', use_git=True, **kwargs):
        return cls(ResearchWorkspace.create(folder, title, repo_url, use_git), llm, searcher, **kwargs)

    @classmethod
    def open(cls, folder, llm, searcher, **kwargs):
        return cls(ResearchWorkspace.open(folder), llm, searcher, **kwargs)

    @property
    def research(self):
        return self.ws.research

    # 阶段 1
    def start(self, prompt):
        return self.scoping.start(prompt)

    def chat(self, message):
        return self.scoping.turn(message)

    def confirm_direction(self, direction=None):
        return self.scoping.confirm(direction)

    # 阶段 2
    def analyze(self, **kwargs):
        return self.analysis.run(**kwargs)

    # 阶段 3
    def select(self, idea_id, **kwargs):
        return self.selection.run(idea_id, **kwargs)

    # 阶段 4（任意阶段可用）
    def translate(self, paper_id, text=None, target='中文'):
        return self.reading.translate(paper_id, text, target)

    def close_read(self, paper_id, fulltext=''):
        return self.reading.close_read(paper_id, fulltext)

    def status(self):
        r = self.research
        nxt = {Stage.CREATED: 'start <prompt>', Stage.SCOPING: 'chat <message> 或 confirm',
               Stage.SCOPED: 'analyze', Stage.ANALYZED: 'select <idea-id>',
               Stage.SELECTED: '在项目文件夹中用 Codex 按 AGENTS.md 实现', Stage.HANDED_OFF: '—'}
        return dict(title=r.title, folder=r.folder, repo=r.repo_url, stage=r.stage.value, direction=r.direction,
                    papers=len(r.papers), ideas=[(i.id, i.title) for i in r.ideas],
                    project=r.project_folder, next=nxt[r.stage])
