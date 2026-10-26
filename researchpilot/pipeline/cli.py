"""命令行入口：python -m researchpilot.pipeline <command> ...

    new      <folder> --title T [--repo URL] [--no-git]
    start    <folder> "<prompt>"
    chat     <folder> "<message>"
    confirm  <folder> [--direction D]
    analyze  <folder>
    select   <folder> <idea-id> [--project DIR] [--repo URL]
    read     <folder> <paper-id> [--translate] [--fulltext FILE]
    status   <folder>

模型连接沿用现有环境变量（见 docs/模型分工与接入.md）：
    RP_RESEARCH_API_BASE  RP_RESEARCH_MODEL  RP_RESEARCH_API_KEY        科研任务
    RP_TRANSLATION_API_BASE  RP_TRANSLATION_MODEL  RP_TRANSLATION_API_KEY 文献翻译
"""
import argparse
import json
import sys
from pathlib import Path

from ..store import Store
from .llm import arxiv_searcher, existing_llm
from .pipeline import ResearchPipeline
from .workspace import ResearchWorkspace


def build(folder):
    llm, tllm = existing_llm('research'), existing_llm('translation')
    searcher = arxiv_searcher(Store(Path(folder).expanduser() / '.researchpilot' / 'cache'))
    return ResearchPipeline.open(folder, llm, searcher, translation_llm=tllm)


def main(argv=None):
    p = argparse.ArgumentParser(prog='researchpilot.pipeline', description='ResearchPilot 阶段式研究流水线')
    sub = p.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('new'); c.add_argument('folder'); c.add_argument('--title', default='')
    c.add_argument('--repo', default=''); c.add_argument('--no-git', action='store_true')
    for name in ('start', 'chat'):
        c = sub.add_parser(name); c.add_argument('folder'); c.add_argument('text')
    c = sub.add_parser('confirm'); c.add_argument('folder'); c.add_argument('--direction')
    c = sub.add_parser('analyze'); c.add_argument('folder')
    c = sub.add_parser('select'); c.add_argument('folder'); c.add_argument('idea')
    c.add_argument('--project'); c.add_argument('--repo', default=''); c.add_argument('--no-git', action='store_true')
    c = sub.add_parser('read'); c.add_argument('folder'); c.add_argument('paper')
    c.add_argument('--translate', action='store_true'); c.add_argument('--fulltext')
    c = sub.add_parser('status'); c.add_argument('folder')
    a = p.parse_args(argv)

    if a.cmd == 'new':
        ResearchWorkspace.create(a.folder, a.title or Path(a.folder).name, a.repo, not a.no_git)
        out = '已创建研究：' + str(Path(a.folder).expanduser().resolve())
    else:
        pipe = build(a.folder)
        if a.cmd == 'start': out = pipe.start(a.text)
        elif a.cmd == 'chat': out = pipe.chat(a.text)
        elif a.cmd == 'confirm': out = pipe.confirm_direction(a.direction)
        elif a.cmd == 'analyze': out = [i.__dict__ for i in pipe.analyze()]
        elif a.cmd == 'select':
            out = pipe.select(a.idea, project_folder=a.project, repo_url=a.repo, use_git=not a.no_git)
        elif a.cmd == 'read':
            if a.translate: out = pipe.translate(a.paper)
            else:
                text = Path(a.fulltext).read_text(encoding='utf-8') if a.fulltext else ''
                out = pipe.close_read(a.paper, text)
        else: out = pipe.status()
    print(out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:  # 命令行给出简洁错误
        sys.exit('错误：' + str(error))
