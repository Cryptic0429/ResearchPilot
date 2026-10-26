"""阶段 3：选择 idea → 新建桌面项目文件夹（绑定 git）→ 初步架构 md + step-by-step → 交付 Codex。

生成的实现项目::

    <project>/
      README.md
      docs/ARCHITECTURE.md      初步架构
      docs/steps/01-xxx.md ...  逐步实现计划（每步有目标、产出、验收标准）
      docs/references.bib       从研究文件夹复制的引用
      AGENTS.md                 给 Codex 等编码代理的工作约定
"""
from pathlib import Path
import re

from .. import references
from ..git_ops import GitRepo
from ..llm import ask_json
from ..models import Stage

INSTRUCTION = (
    '你是科研工程架构师。为选定的 idea 设计一个最小可行的实验代码项目。返回字段：'
    'overview（项目目标）、architecture（Markdown，含模块划分、数据流、目录结构、技术选型）、'
    'steps（数组，每项含 title、goal、deliverables（字符串数组）、acceptance（验收标准字符串数组））。'
    '步骤应小而可验证，先基线后改进，便于编码代理逐步实现。'
)


def slugify(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:40] or 'step'


class SelectionStage:
    def __init__(self, workspace, llm, git_factory=GitRepo):
        self.ws, self.llm, self.git_factory = workspace, llm, git_factory

    def run(self, idea_id, project_folder=None, repo_url='', use_git=True):
        self.ws.require(Stage.ANALYZED)
        r = self.ws.research
        idea = r.idea(idea_id)
        folder = Path(project_folder or Path.home() / 'Desktop' / (slugify(idea.title) or 'research-project'))
        folder = folder.expanduser().resolve()
        if folder.exists() and any(folder.iterdir()):
            raise FileExistsError('项目文件夹已存在且非空：' + str(folder))
        folder.mkdir(parents=True, exist_ok=True)
        sources = [dict(id=p, title=r.papers[p].title, abstract=r.papers[p].abstract[:1000]) for p in idea.refs]
        plan = ask_json(self.llm, INSTRUCTION, dict(direction=r.direction, idea=idea.__dict__, sources=sources),
                        required=('overview', 'architecture', 'steps'))
        files = self.render(idea, plan)
        for relative, text in files.items():
            path = folder / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
        if use_git:
            git = self.git_factory(folder)
            r.project_repo_url = git.bind(repo_url)
            git.commit('初始化：' + idea.title + ' 的架构与实现步骤')
        r.selected_idea, r.project_folder = idea.id, str(folder)
        self.ws.advance(Stage.SELECTED)
        self.ws.save('选定 idea ' + idea.id + ' 并创建项目 ' + folder.name)
        return dict(folder=str(folder), files=sorted(files), steps=len(plan['steps']))

    def render(self, idea, plan):
        r = self.ws.research
        steps = plan['steps']
        files = {}
        index = []
        for n, step in enumerate(steps, 1):
            name = 'docs/steps/%02d-%s.md' % (n, slugify(step['title']))
            index.append('%d. [%s](%s)' % (n, step['title'], name))
            files[name] = '\n'.join(
                ['# Step %d · %s' % (n, step['title']), '', '## 目标', '', step.get('goal', ''), '', '## 产出', '']
                + ['- ' + d for d in step.get('deliverables', [])] + ['', '## 验收标准', '']
                + ['- [ ] ' + a for a in step.get('acceptance', [])] + [''])
        refs = '\n'.join('- ' + r.papers[p].title + ' (' + r.papers[p].url + ')' for p in idea.refs)
        files['README.md'] = '\n'.join(['# ' + idea.title, '', plan['overview'], '', '## 研究假设', '',
            idea.hypothesis, '', '## 实现步骤', ''] + index + ['', '## 参考文献', '', refs,
            '', '> 研究过程记录位于：' + r.folder, ''])
        files['docs/ARCHITECTURE.md'] = '# 初步架构\n\n' + plan['architecture'].strip() + '\n'
        files['docs/references.bib'] = '\n'.join(references.bibtex(r.papers[p]) for p in idea.refs)
        files['AGENTS.md'] = '\n'.join([
            '# 编码代理工作约定（Codex 等）', '',
            '1. 先读 `README.md` 与 `docs/ARCHITECTURE.md`，理解研究假设与整体架构。',
            '2. 严格按 `docs/steps/` 的编号顺序实现，每次只完成一个 step。',
            '3. 每个 step 完成后：运行测试、勾选该文件中的验收标准、单独提交一次 git commit。',
            '4. 不得修改研究假设；若发现架构不可行，在对应 step 文件末尾写明原因并停止。',
            '5. 实验结果写入 `results/`，并注明随机种子、配置与运行环境。', '',
            '## 步骤索引', ''] + index + [''])
        return files
