"""references/ 目录：BibTeX + 每篇文献一个 md（摘要、被哪些 idea 引用、精读笔记）。"""
import re


def bibtex(paper):
    key = re.sub(r'\W+', '', paper.id) or 'paper'
    year = paper.published[:4]
    fields = dict(title=paper.title, author=paper.authors.replace(', ', ' and '), year=year, url=paper.url)
    if re.match(r'^\d{4}\.\d{4,5}', paper.id):
        fields.update(eprint=paper.id, archivePrefix='arXiv')
    body = ',\n'.join('  ' + k + ' = {' + v.replace('{', '').replace('}', '') + '}' for k, v in fields.items() if v)
    return '@misc{' + key + ',\n' + body + '\n}\n'


def paper_md(paper, cited_by):
    lines = ['# ' + paper.title, '', '- ID：' + paper.id, '- 作者：' + paper.authors, '- 日期：' + paper.published,
             '- 链接：' + paper.url, '- 来源：' + paper.source,
             '- 被引用于：' + (', '.join(cited_by) or '（暂无）'), '', '## 摘要', '', paper.abstract or '（无）', '',
             '## 精读笔记', '', paper.notes or '（尚未精读，可运行 `read` 命令）', '']
    return '\n'.join(lines)


def write_all(ws):
    r = ws.research
    cited = {}
    for idea in r.ideas:
        for ref in idea.refs:
            cited.setdefault(ref, []).append(idea.id)
    ws.write('references/references.bib', '\n'.join(bibtex(p) for p in r.papers.values()))
    for paper in r.papers.values():
        ws.write('references/' + paper.slug + '.md', paper_md(paper, cited.get(paper.id, [])))
