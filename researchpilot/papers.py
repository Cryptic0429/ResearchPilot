"""Live arXiv metadata retrieval."""
import collections
from datetime import datetime, timezone, timedelta
import math
import re
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from .store import now

QUERY_MAP = {'检索增强生成': 'retrieval augmented generation', '大语言模型': 'large language model',
             '图神经网络': 'graph neural network', '医学影像': 'medical image', '多模态': 'multimodal',
             '智能体': 'language model agent', '计算机视觉': 'computer vision', '蛋白质': 'protein',
             '时间序列': 'time series', '推荐系统': 'recommender system'}
STOP = set('the a an of to and in for on with by from via is are as using learning language large model models based neural networks new can we our that this'.split())
LOCK = threading.Lock()
LAST_REQUEST = 0.0


def keywords(papers):
    counter = collections.Counter()
    for p in papers:
        counter.update(set(w for w in re.findall(r'[a-z][a-z-]{3,}', p['title'].lower()) if w not in STOP))
    return [dict(term=k, count=v) for k,v in counter.most_common(8)]


class PaperService:
    def __init__(self, store):
        self.store = store

    def search(self, query, days=90, mode='live'):
        query = str(query).strip()[:180]
        if not query:
            raise ValueError('请输入研究领域或英文关键词')
        days = int(days)
        if days not in (7, 30, 90, 365):
            raise ValueError('时间窗口仅支持 7、30、90、365 天')
        if mode != 'live':
            raise ValueError('未知检索模式')
        normalized = QUERY_MAP.get(query, query)
        if re.search(r'[\u4e00-\u9fff]', normalized):
            raise ValueError('arXiv 以英文检索为主，请输入英文关键词，如 medical image segmentation')
        cachekey = 'search:' + normalized.lower() + ':' + str(days)
        cached = self.store.get(cachekey)
        if cached and time.time()-cached['timestamp'] < 900:
            return {**cached['data'], 'cached': True}
        since = (datetime.now(timezone.utc)-timedelta(days=days)).strftime('%Y%m%d0000')
        until = datetime.now(timezone.utc).strftime('%Y%m%d2359')
        # Treat ordinary search input as literal words, never as API query syntax.
        tokens = re.findall(r'[A-Za-z0-9-]+', normalized)
        if not tokens:
            raise ValueError('请输入有效的英文关键词')
        expression = ' AND '.join('all:'+w for w in tokens[:16])
        expression += ' AND submittedDate:['+since+' TO '+until+']'
        params = urllib.parse.urlencode(dict(search_query=expression, start=0, max_results=24,
                                             sortBy='submittedDate', sortOrder='descending'))
        global LAST_REQUEST
        with LOCK:
            time.sleep(max(0, 3.1-(time.monotonic()-LAST_REQUEST)))
            LAST_REQUEST = time.monotonic()
            req = urllib.request.Request('https://export.arxiv.org/api/query?'+params,
                                         headers={'User-Agent': 'ResearchPilot/1.0 (local academic prototype)'})
            with urllib.request.urlopen(req, timeout=22) as response:
                raw = response.read(3_000_000)
        root = ET.fromstring(raw)
        ns = {'a':'http://www.w3.org/2005/Atom'}
        papers = []
        for entry in root.findall('a:entry', ns):
            get = lambda tag: ' '.join((entry.findtext('a:'+tag, '', ns)).split())
            if not get('id').startswith(('http://arxiv.org/abs/', 'https://arxiv.org/abs/')):
                continue
            paper_id = get('id').split('/abs/')[-1]
            date = get('published')[:10]
            age = max(0, (datetime.now(timezone.utc).date()-datetime.strptime(date,'%Y-%m-%d').date()).days)
            title, abstract = get('title'), get('summary')
            relevance = sum(1 for w in tokens if w.lower() in (title+' '+abstract).lower()) / len(tokens)
            freshness = math.exp(-age/max(days/2,1))
            score = round(100*(0.55*relevance+0.45*freshness))
            cat = entry.find('a:category', ns)
            papers.append(dict(id=paper_id, title=title, abstract=abstract[:6000],
                authors=', '.join(x.findtext('a:name','',ns) for x in entry.findall('a:author',ns)[:4]),
                published=date, category=cat.attrib.get('term','') if cat is not None else '',
                url='https://arxiv.org/abs/'+paper_id, source='arXiv · 实时元数据', demo=False,
                score=score, score_detail=dict(relevance=round(relevance,3), freshness=round(freshness,3)),
                tags=[], evidence='仅题录与摘要；预印本状态及结论需到原文核验'))
        papers.sort(key=lambda p:p['score'], reverse=True)
        result = dict(papers=papers, mode='live', query=query, normalized_query=normalized, retrieved_at=now(),
            topics=keywords(papers), cached=False,
            note='候选排序 = 55% 关键词覆盖 + 45% 时效；先取 arXiv 最新 24 篇再排序。它是阅读优先级，不是引文热度或质量评分。')
        self.store.set(cachekey, dict(timestamp=time.time(), data=result))
        self.store.event('paper_search', dict(query=query, count=len(papers), source='arxiv'))
        return result
