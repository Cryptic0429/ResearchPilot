"""流水线的数据模型（纯 dataclass，可 JSON 序列化）。"""
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from ..store import now


class Stage(str, Enum):
    CREATED = 'created'        # 0. 已绑定文件夹与仓库
    SCOPING = 'scoping'        # 1. 方向收敛中
    SCOPED = 'scoped'          # 1. 方向已确定
    ANALYZED = 'analyzed'      # 2. 已产出带来源的 idea
    SELECTED = 'selected'      # 3. 已选定 idea 并建好实现项目
    HANDED_OFF = 'handed_off'  # 5. 已交付编码代理

    @property
    def order(self):
        return list(Stage).index(self)


@dataclass
class Paper:
    id: str
    title: str
    authors: str = ''
    published: str = ''
    abstract: str = ''
    url: str = ''
    source: str = ''
    notes: str = ''            # 精读笔记（阶段 4 回写）

    @classmethod
    def from_dict(cls, data):
        return cls(**{k: str(data.get(k) or '') for k in cls.__dataclass_fields__})

    @property
    def slug(self):
        return ''.join(c if c.isalnum() or c in '.-' else '_' for c in self.id)[:80]


@dataclass
class Idea:
    id: str
    title: str
    hypothesis: str
    motivation: str = ''
    experiment: str = ''
    risk: str = ''
    refs: List[str] = field(default_factory=list)   # 必须是已收录 Paper.id

    @classmethod
    def from_dict(cls, data):
        return cls(id=str(data['id']), title=str(data['title']), hypothesis=str(data['hypothesis']),
                   motivation=str(data.get('motivation', '')), experiment=str(data.get('experiment', '')),
                   risk=str(data.get('risk', '')), refs=[str(r) for r in data.get('refs', [])])


@dataclass
class Turn:
    role: str      # user / assistant
    content: str
    created: str = field(default_factory=now)


@dataclass
class Research:
    id: str
    title: str
    folder: str
    repo_url: str = ''
    stage: Stage = Stage.CREATED
    prompt: str = ''
    direction: str = ''                       # 阶段 1 收敛后的研究方向
    queries: List[str] = field(default_factory=list)
    dialogue: List[Turn] = field(default_factory=list)
    papers: Dict[str, Paper] = field(default_factory=dict)
    ideas: List[Idea] = field(default_factory=list)
    selected_idea: Optional[str] = None
    project_folder: str = ''                  # 阶段 3 新建的实现项目
    project_repo_url: str = ''
    created: str = field(default_factory=now)
    updated: str = field(default_factory=now)

    def to_dict(self):
        data = asdict(self)
        data['stage'] = self.stage.value
        return data

    @classmethod
    def from_dict(cls, data):
        data = dict(data)
        data['stage'] = Stage(data.get('stage', 'created'))
        data['dialogue'] = [Turn(**t) for t in data.get('dialogue', [])]
        data['papers'] = {k: Paper.from_dict(v) for k, v in data.get('papers', {}).items()}
        data['ideas'] = [Idea.from_dict(i) for i in data.get('ideas', [])]
        return cls(**data)

    def idea(self, idea_id):
        for idea in self.ideas:
            if idea.id == idea_id:
                return idea
        raise KeyError('idea 不存在：' + idea_id)
