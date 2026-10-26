"""LLM 与检索协议，以及对现有 researchpilot 服务的适配。"""
import json
import re
from typing import Callable, Dict, List, Protocol


class LLM(Protocol):
    def __call__(self, instruction: str, payload: dict) -> str: ...


class Searcher(Protocol):
    def __call__(self, query: str) -> List[Dict]: ...


def parse_json(text):
    """容忍 ```json 围栏的 JSON 解析。"""
    clean = re.sub(r'^```(?:json)?\s*|\s*```$', '', str(text).strip())
    return json.loads(clean)


def ask_json(llm, instruction, payload, required=()):
    obj = parse_json(llm(instruction + '\n只返回一个 JSON 对象，不要额外文字。', payload))
    if not isinstance(obj, dict) or any(k not in obj for k in required):
        raise ValueError('模型输出缺少字段：' + ', '.join(required))
    return obj


def existing_llm(purpose='research', config=None):
    """复用现有 agents.model_call（科研 / 翻译两组独立连接）。

    config 为 None 时使用现有环境变量：RP_RESEARCH_API_BASE / RP_RESEARCH_MODEL / RP_RESEARCH_API_KEY、
    RP_TRANSLATION_API_BASE / ...（详见 docs/模型分工与接入.md）。
    """
    from .. import agents

    def call(instruction, payload):
        with agents.provider_context(dict(config or {}), purpose):
            return agents.model_call(instruction, payload)
    return call


def arxiv_searcher(store, days=365):
    """复用现有 PaperService（arXiv 实时检索）。"""
    from ..papers import PaperService
    service = PaperService(store)
    return lambda query: service.search(query, days=days)['papers']


def make_llm(fn: Callable[[str, dict], str]) -> LLM:
    return fn
