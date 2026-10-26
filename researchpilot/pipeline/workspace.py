"""阶段 0：一次研究 = 一个本地文件夹（绑定 GitHub 仓库）。

研究文件夹布局::

    <folder>/
      .researchpilot/research.json   研究状态（唯一事实来源）
      README.md                      研究概览（自动生成）
      direction.md                   阶段 1：方向收敛记录
      ideas/ideas.md                 阶段 2：带来源的 idea 列表
      references/
        references.bib               阶段 2：BibTeX
        <paper-id>.md                每篇文献的摘要 / 精读笔记
      translations/<paper-id>.md     阶段 4：精读翻译
"""
import json
import uuid
from pathlib import Path

from ..store import now
from .git_ops import GitRepo
from .models import Research, Stage

STATE = Path('.researchpilot') / 'research.json'
GITIGNORE = '.researchpilot/cache/\n__pycache__/\n.DS_Store\n'


class ResearchWorkspace:
    def __init__(self, research, git=None):
        self.research = research
        self.root = Path(research.folder)
        self.git = git or GitRepo(self.root)

    # ---------- 创建 / 打开 ----------
    @classmethod
    def create(cls, folder, title, repo_url='', use_git=True, git=None):
        root = Path(folder).expanduser().resolve()
        if (root / STATE).exists():
            raise FileExistsError('该文件夹已是一个研究：' + str(root))
        root.mkdir(parents=True, exist_ok=True)
        for sub in ('references', 'ideas', 'translations', '.researchpilot'):
            (root / sub).mkdir(exist_ok=True)
        gitignore = root / '.gitignore'
        if not gitignore.exists():
            gitignore.write_text(GITIGNORE, encoding='utf-8')
        research = Research(id=uuid.uuid4().hex[:12], title=title.strip() or root.name, folder=str(root))
        ws = cls(research, git)
        if use_git:
            research.repo_url = ws.git.bind(repo_url)
        ws.save('开展新研究：' + research.title)
        return ws

    @classmethod
    def open(cls, folder, git=None):
        root = Path(folder).expanduser().resolve()
        path = root / STATE
        if not path.exists():
            raise FileNotFoundError('不是研究文件夹（缺少 ' + str(STATE) + '）：' + str(root))
        research = Research.from_dict(json.loads(path.read_text(encoding='utf-8')))
        research.folder = str(root)
        return cls(research, git)

    # ---------- 持久化 ----------
    def save(self, commit_message=None):
        self.research.updated = now()
        (self.root / STATE).write_text(json.dumps(self.research.to_dict(), ensure_ascii=False, indent=2),
                                       encoding='utf-8')
        self.write('README.md', self.readme())
        if commit_message and self.git.initialized:
            self.git.commit(commit_message)

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def advance(self, stage):
        if stage.order > self.research.stage.order:
            self.research.stage = stage

    def require(self, stage):
        if self.research.stage.order < stage.order:
            raise RuntimeError('当前阶段为 ' + self.research.stage.value + '，需先完成 ' + stage.value)

    def readme(self):
        r = self.research
        lines = ['# ' + r.title, '', '> 由 ResearchPilot 维护，研究状态见 `.researchpilot/research.json`', '',
                 '| 项 | 内容 |', '| --- | --- |', '| 阶段 | ' + r.stage.value + ' |',
                 '| 仓库 | ' + (r.repo_url or '（仅本地 git）') + ' |',
                 '| 方向 | ' + (r.direction or r.prompt or '待确定').replace('\n', ' ') + ' |',
                 '| 文献 | ' + str(len(r.papers)) + ' 篇（references/） |',
                 '| Idea | ' + str(len(r.ideas)) + ' 条（ideas/ideas.md） |']
        if r.selected_idea:
            lines.append('| 已选 idea | ' + r.selected_idea + ' → ' + r.project_folder + ' |')
        return '\n'.join(lines) + '\n'
