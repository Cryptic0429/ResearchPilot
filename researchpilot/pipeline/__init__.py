"""ResearchPilot 新架构：以「一次研究 = 一个绑定 GitHub 仓库的本地文件夹」为中心的阶段式流水线。

    0. 开展新研究      ResearchWorkspace.create   绑定本地文件夹 + GitHub 仓库
    1. 方向收敛        ScopingStage               prompt → 检索 → 交互，直到大致确定方向
    2. 文献分析        AnalysisStage              文献 → 分析 → idea（每条带 paper 来源）→ references/
    3. 选择 idea       SelectionStage             新建桌面项目文件夹（绑定 git）+ 初步架构 md + step-by-step
    4. 精读与翻译      ReadingStage               可在任意阶段回到文献精读 / 翻译，结果回写 references/
    5. 交付编码代理    handoff (AGENTS.md)        交给 Codex 等编码代理按步骤实现

各阶段只依赖 `LLM` 与 `Searcher` 两个协议，便于离线测试和替换模型 / 检索源。
"""
from .models import Idea, Paper, Research, Stage
from .workspace import ResearchWorkspace
from .pipeline import ResearchPipeline

__all__ = ['Idea', 'Paper', 'Research', 'Stage', 'ResearchWorkspace', 'ResearchPipeline']
