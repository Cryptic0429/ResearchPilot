"""Account -> bound project folder -> isolated research tasks.

Explicit request IDs select a context. Mutable last-selection preferences are
only used when a browser first loads; background jobs keep their original scope.
"""
import json
from pathlib import Path
from types import SimpleNamespace
import threading
import uuid

from .agents import Orchestrator
from .environment import Environments
from .papers import PaperService
from .projects import scan_path, compare, public_project, snapshot
from .reader import ReaderService
from .store import Store, now


UNSET=object()


class ProjectError(ValueError):
    def __init__(self,message,status=400):
        super().__init__(message)
        self.status=status


class ResearchStore(Store):
    def __init__(self,directory,project):
        super().__init__(directory)
        self.project=project

    def get(self,key,default=None):
        return self.project() if key=='project' else super().get(key,default)


class ProjectManager:
    def __init__(self,store):
        self.store=store
        self.lock=threading.RLock()
        self.stores={}
        self.contexts={}
        self.migrate_legacy()

    def entries(self):
        return self.store.get('research_projects',[])

    def project(self,project_id):
        if not isinstance(project_id,str):raise ProjectError('请先创建项目并绑定文件夹')
        entry=next((p for p in self.entries() if p['id']==project_id),None)
        if not entry:raise ProjectError('当前账号中不存在此项目',404)
        return entry

    def project_store(self,project_id):
        self.project(project_id)  # Validate ownership before constructing a path.
        with self.lock:
            if project_id not in self.stores:
                self.stores[project_id]=Store(self.store.directory/'projects'/project_id)
            return self.stores[project_id]

    def researches(self,project_id):
        return self.project_store(project_id).get('researches',[])

    def selection(self,project_id=UNSET,research_id=UNSET):
        saved=self.store.get('research_selection',{})
        pid=saved.get('project_id') if project_id is UNSET else project_id
        sid=(saved.get('research_id') if pid==saved.get('project_id') else None) if research_id is UNSET else research_id
        if pid is None:
            if sid is not None:raise ProjectError('研究任务必须属于一个项目')
            return None,None
        project=self.project(pid)
        if project.get('archived'):
            return None,None
        research=None
        if sid is not None:
            research=next((r for r in self.researches(pid) if r['id']==sid),None)
            if research is None:raise ProjectError('此研究任务不属于当前项目',404)
        return project,research

    def snapshot(self,project_id,research_id=None):
        project=self.project(project_id)
        data={**snapshot(project['name'],[],allow_empty=True),**(self.project_store(project_id).get('snapshot') or {})}
        return dict(data,id=project_id,name=project['name'],local_path=project['path'],bound=project['bound'],
                    conversation_id=research_id or project_id)

    def context(self,project_id=UNSET,research_id=UNSET,require_bound=True):
        project,research=self.selection(project_id,research_id)
        if project is None:raise ProjectError('请先创建项目并绑定文件夹')
        if require_bound and not project['bound']:raise ProjectError('请先为历史项目绑定文件夹，再继续研究')
        if research is None:raise ProjectError('请先在当前项目中新建或选择研究任务')
        key=(project['id'],research['id'])
        with self.lock:
            if key not in self.contexts:
                directory=self.project_store(project['id']).directory/'researches'/research['id']
                store=ResearchStore(directory,lambda:self.snapshot(*key))
                self.contexts[key]=SimpleNamespace(store=store,papers=PaperService(store),agents=Orchestrator(store),
                    reader=ReaderService(),env=Environments(store),project_id=key[0],research_id=key[1],
                    project_record=project,research_record=research)
            context=self.contexts[key]
            context.project_record=project
            context.research_record=research
            return context

    def list(self,archived=False):
        return [dict(p,research_count=len(self.researches(p['id']))) for p in self.entries()
                if bool(p.get('archived'))==archived]

    def set_archived(self,project_id,archived):
        with self.lock:
            entry=self.project(project_id)
            updated=dict(entry,archived=archived)
            if archived:
                updated['archived_at']=entry.get('archived_at') or now()
            else:
                updated.pop('archived_at',None)
            self.store.set('research_projects',[updated if p['id']==project_id else p for p in self.entries()])
            if archived and self.store.get('research_selection',{}).get('project_id')==project_id:
                self.store.set('research_selection',dict(project_id=None,research_id=None))
            return updated

    def select(self,project_id,research_id=None):
        if project_id is not None and self.project(project_id).get('archived'):
            raise ProjectError('项目已归档，请先恢复项目。',409)
        self.selection(project_id,research_id)
        selected=dict(project_id=project_id,research_id=research_id)
        self.store.set('research_selection',selected)
        return selected

    def create(self,name,path,consent):
        if consent is not True:raise ProjectError('请确认允许读取绑定文件夹中的研究代码和配置')
        if not isinstance(path,str) or not path.strip():raise ProjectError('请选择已有的本机项目文件夹')
        data=scan_path(path,allow_empty=True)
        if not isinstance(name,str) or len(name.strip())>80:raise ProjectError('项目名称最多 80 个字符')
        with self.lock:
            existing=next((p for p in self.entries() if p['path']==data['local_path']),None)
            if existing:
                restored=bool(existing.get('archived'))
                if restored:self.set_archived(existing['id'],False)
                return dict(self.select(existing['id']),existing=True,restored=restored)
            entry=dict(id=uuid.uuid4().hex,name=name.strip() or data['name'],path=data['local_path'],
                       bound=True,legacy=False,created_at=now())
            directory=self.store.directory/'projects'/entry['id']
            project_store=Store(directory)
            project_store.set('snapshot',data)
            project_store.set('researches',[])
            self.store.set('research_projects',self.entries()+[entry])
            self.stores[entry['id']]=project_store
            return dict(self.select(entry['id']),existing=False)

    def bind(self,project_id,path,consent):
        if consent is not True:raise ProjectError('请确认允许读取绑定文件夹')
        data=scan_path(path,allow_empty=True)
        with self.lock:
            entry=self.project(project_id)
            if entry['bound']:raise ProjectError('此项目已绑定文件夹，请通过项目列表选择对应项目')
            if any(p['path']==data['local_path'] for p in self.entries() if p['id']!=project_id):
                raise ProjectError('此文件夹已绑定到另一个项目，请选择独立的文件夹')
            updated=dict(entry,path=data['local_path'],bound=True)
            self.project_store(project_id).set('snapshot',data)
            self.store.set('research_projects',[updated if p['id']==project_id else p for p in self.entries()])
            return self.select(project_id)

    def create_research(self,project_id,title):
        project=self.project(project_id)
        if not project['bound']:raise ProjectError('请先绑定项目文件夹')
        if not isinstance(title,str) or not 1<=len(title.strip())<=120:raise ProjectError('研究任务名称需为 1–120 个字符')
        with self.lock:
            research=dict(id=uuid.uuid4().hex,title=title.strip(),created_at=now(),updated_at=now())
            store=self.project_store(project_id)
            store.set('researches',store.get('researches',[])+[research])
            self.context(project_id,research['id'])
            return self.select(project_id,research['id'])

    def refresh(self,project_id):
        entry=self.project(project_id)
        if not entry['bound']:raise ProjectError('请先绑定项目文件夹')
        with self.lock:
            before=self.snapshot(project_id)
            data=scan_path(entry['path'],allow_empty=True)
            data['diff']=compare(before,data)
            self.project_store(project_id).set('snapshot',data)
            return public_project(self.snapshot(project_id))

    def touch(self,project_id,research_id):
        with self.lock:
            store=self.project_store(project_id)
            store.set('researches',[dict(r,updated_at=now()) if r['id']==research_id else r
                                    for r in store.get('researches',[])])

    def migrate_legacy(self):
        if self.store.get('project_layout_version')==1:return
        # Global records may contain several old topics. Preserve them together
        # without guessing which folder they belong to. The original rows stay.
        condition="key IN ('active_search','last_run') OR key LIKE 'chat:%' OR key LIKE 'plan:%' OR key LIKE 'team-run:%' OR key LIKE 'search:%'"
        with self.store.connection() as db:
            has_data=(db.execute('SELECT 1 FROM kv WHERE '+condition+" OR key='project' LIMIT 1").fetchone()
                      or db.execute('SELECT 1 FROM items LIMIT 1').fetchone())
            if not has_data:
                db.execute('INSERT OR REPLACE INTO kv VALUES (?,?)',('project_layout_version','1'))
                return
            pid,sid=uuid.uuid4().hex,uuid.uuid4().hex
            legacy=self.store.get('project')
            entry=dict(id=pid,name='历史研究记录',path=None,bound=False,legacy=True,created_at=now(),
                       suggested_path=(legacy or {}).get('local_path'))
            research=dict(id=sid,title='历史记录（归属待确认）',created_at=now(),updated_at=now())
            project_store=Store(self.store.directory/'projects'/pid)
            project_store.set('snapshot',legacy)
            project_store.set('researches',[research])
            target=Store(project_store.directory/'researches'/sid)
            db.execute('ATTACH DATABASE ? AS legacy_target',(str(target.path),))
            db.execute('INSERT INTO legacy_target.kv SELECT * FROM main.kv WHERE '+condition)
            db.execute('INSERT INTO legacy_target.items SELECT * FROM main.items')
            db.execute('INSERT INTO legacy_target.events SELECT * FROM main.events')
            conversations=db.execute("SELECT key,value FROM main.kv WHERE key LIKE 'chat:%'").fetchall()
            current_key='chat:'+((legacy or {}).get('conversation_id') or (legacy or {}).get('name') or 'general')
            for row in conversations:
                history=json.loads(row['value'])
                # Keep every old conversation discoverable without combining
                # messages from different former project contexts into one chat.
                transcript='\n\n'.join(('用户' if message.get('role')=='user' else '助手')+'：'+str(message.get('content','')) for message in history)
                db.execute('INSERT INTO legacy_target.items VALUES (?,?,?,?,?)',
                           (uuid.uuid4().hex,'note','历史对话记录 · '+row['key'][5:][:120],json.dumps(transcript,ensure_ascii=False),now()))
                if row['key']==current_key:
                    db.execute('INSERT OR REPLACE INTO legacy_target.kv VALUES (?,?)',('chat:'+sid,row['value']))
            # Never carry an old unconsumed environment approval into a new scope.
            for row in db.execute("SELECT key,value FROM legacy_target.kv WHERE key LIKE 'plan:%'").fetchall():
                plan=json.loads(row['value'])
                if plan.get('status') in ('awaiting_approval','authorized'):
                    plan.update(status='expired',expires_at=0)
                    db.execute('UPDATE legacy_target.kv SET value=? WHERE key=?',(json.dumps(plan,ensure_ascii=False),row['key']))
            db.execute('INSERT OR REPLACE INTO kv VALUES (?,?)',('research_projects',json.dumps(self.entries()+[entry],ensure_ascii=False)))
            db.execute('INSERT OR REPLACE INTO kv VALUES (?,?)',('project_layout_version','1'))
