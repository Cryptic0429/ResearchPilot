import argparse
import base64
import hashlib
import concurrent.futures
from functools import wraps
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import secrets
import threading
import traceback
import urllib.error
import urllib.parse
import uuid
import webbrowser
from . import __version__
from .accounts import Accounts, AccountError, DEFAULT_PREFERENCES
from .agents import Orchestrator, model_config, configure_provider, restore_provider, provider_context, clear_provider_key, PURPOSES, validate_purpose, is_zhiyuan, validate_provider
from .credentials import ProviderCredentials
from .connections import ConnectionLibrary
from .environment import Environments
from .folder_picker import list_project_folders
from .project_flow import ProjectFlow
from types import SimpleNamespace
from .papers import PaperService
from .reader import ReaderService
from .projects import scan_path, snapshot, compare, public_project, redact
from .store import Store, now
from .workspaces import ProjectManager, ProjectError, UNSET

ROOT=Path(__file__).resolve().parent.parent


def scoped_provider(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with provider_context(self.model_settings):
            return method(self, *args, **kwargs)
    return call


def migrate_model_connections(store, persistent):
    """Move the legacy single connection to exactly one purpose; never clone keys."""
    try:
        if persistent:
            legacy = ProviderCredentials(store.directory)
            saved = legacy.load()
            if saved is not None:
                validate_provider(saved['base'], saved['style'], saved['auth'])
                purpose = 'translation' if is_zhiyuan(saved) else 'research'
                target = ProviderCredentials(store.directory, purpose)
                if target.load() is None:
                    target.save(saved)
                # Only retire the obsolete file after the replacement is readable.
                if target.load() is not None:
                    legacy.path.unlink()
        previous = store.get('provider_config')
        if isinstance(previous, dict):
            purpose = 'translation' if is_zhiyuan(previous) else 'research'
            key = 'provider_config:' + purpose
            if store.get(key) is None:
                store.set(key, {k:previous[k] for k in ('base','model','provider','style','auth')})
    except (ValueError, OSError, KeyError, TypeError):
        return '旧模型配置无法迁移，请在设置中重新保存对应连接'
    return ''


class Workspace:
    def __init__(self,data_dir,pool=None,allow_environment=True):
        self.store=Store(data_dir)
        self.model_profiles={purpose:({} if allow_environment else {'key':''}) for purpose in PURPOSES}
        self.model_credentials={purpose:(None if allow_environment else ProviderCredentials(self.store.directory,purpose)) for purpose in PURPOSES}
        migration_error=migrate_model_connections(self.store, not allow_environment)
        for purpose in PURPOSES:
            with provider_context(self.model_profiles[purpose], purpose):
                restore_provider(self.store,allow_environment,credentials=self.model_credentials[purpose])
                if migration_error:
                    self.model_profiles[purpose].update(key='',key_saved=False,credential_error=migration_error)
        # Compatibility aliases represent research only; translation is always explicit.
        self.model_settings=self.model_profiles['research']
        self.translation_settings=self.model_profiles['translation']
        self.credentials=self.model_credentials['research']
        self.connections=ConnectionLibrary(self.store,persistent=not allow_environment)
        self.projects=ProjectManager(self.store)
        self.flows={}
        self.library_store=Store(self.store.directory/'library')
        self.token=secrets.token_urlsafe(32)
        self.jobs={}
        self.lock=threading.RLock()
        self.pool=pool if pool is not None else concurrent.futures.ThreadPoolExecutor(max_workers=3)
        self.slots=threading.BoundedSemaphore(6)

    def job(self,label,fn,purpose='research',scope=None):
        validate_purpose(purpose)
        if not self.slots.acquire(blocking=False):
            raise ValueError('任务队列已满，请等待当前任务完成')
        jid=uuid.uuid4().hex
        # Each queued task keeps the caller's model settings, including its in-memory key.
        with provider_context(self.model_profiles[purpose], purpose):
            job_config=dict(model_config())
        with self.lock:
            # Bound finished in-memory jobs; persisted results remain in SQLite.
            if len(self.jobs)>100:
                for k in list(self.jobs):
                    if self.jobs[k]['status'] in ('done','error'):
                        del self.jobs[k]
                        break
            self.jobs[jid]=dict(id=jid,status='queued',label=label,progress=label,created_at=now(),purpose=purpose,
                project_id=scope.project_id if scope else None,research_id=scope.research_id if scope else None)
        def progress(text):
            with self.lock:
                self.jobs[jid]['progress']=text
        def work():
            with provider_context(job_config, purpose):
                try:
                    with self.lock:
                        self.jobs[jid]['status']='running'
                    result=fn(progress)
                    with self.lock:
                        self.jobs[jid].update(status='done',result=result,progress='已完成')
                except Exception as e:
                    with self.lock:
                        self.jobs[jid].update(status='error',error=safe_error(e),progress='任务未完成')
                finally:
                    try:
                        if scope:self.projects.touch(scope.project_id,scope.research_id)
                    finally:self.slots.release()
        self.pool.submit(work)
        return dict(job_id=jid)

    def project_flow(self,project_id):
        entry=self.projects.project(project_id)
        if entry.get('archived') or not entry['bound']:raise ProjectError('请先选择已绑定文件夹的项目')
        with self.lock:
            if project_id not in self.flows:
                self.flows[project_id]=ProjectFlow(self.projects.project_store(project_id),entry)
            return self.flows[project_id]

    @scoped_provider
    def state(self,project_id=UNSET,research_id=UNSET):
        models={}
        for purpose in PURPOSES:
            with provider_context(self.model_profiles[purpose],purpose):
                models[purpose]={k:v for k,v in model_config().items() if k!='key'}
        cfg=models['research']
        project,research=self.projects.selection(project_id,research_id)
        pid=project['id'] if project else None
        sid=research['id'] if research else None
        context=self.projects.context(pid,sid,require_bound=False) if sid else None
        with self.lock:
            active_jobs=[dict(id=j['id'],label=j['label'],status=j['status']) for j in self.jobs.values()
                if j['status'] in ('queued','running') and (j.get('project_id') is None or
                (j['project_id']==pid and (j['research_id'] is None or j['research_id']==sid)))]
        store=context.store if context else None
        return dict(version=__version__,model=cfg,models=models,connections=self.connections.list(),
            research_flow=self.project_flow(pid).state() if pid and project['bound'] else None,reading_notes=self.library_store.items(),
            projects=self.projects.list(),archived_projects=self.projects.list(archived=True),project=public_project(self.projects.snapshot(pid,sid)) if pid else None,
            project_record=project,research=research,researches=self.projects.researches(pid) if pid else [],
            search=(store.get('active_search') if store and store.get('active_search',{}).get('mode')=='live' else None),
            last_run=store.get('last_run') if store else None,notes=store.items() if store else [],events=store.events() if store else [],
            active_jobs=active_jobs)

    @scoped_provider
    def api(self,path,data,project_id=UNSET,research_id=UNSET):
        if path=='/api/reader/translate':
            return self.job('论文翻译',lambda progress:ReaderService().translate(data),purpose='translation')
        if path=='/api/reader/notes':
            body=data.get('body')
            if not isinstance(body,dict):raise ValueError('阅读笔记内容无效')
            return self.library_store.add('translation',str(data.get('title','双语阅读'))[:200],body)
        if path.startswith('/api/flow/'):
            project,_=self.projects.selection(project_id,research_id)
            if not project:raise ProjectError('请先选择项目并绑定文件夹')
            flow=self.project_flow(project['id'])
            if path=='/api/flow/confirm':return flow.confirm()
            scope=SimpleNamespace(project_id=project['id'],research_id=None)
            def scoped_work(fn):
                # Folder workflows belong to the project, independent of legacy research tabs.
                return self.job('研究方向探索',fn,scope=scope)
            if path=='/api/flow/turn':return scoped_work(lambda progress:flow.turn(data.get('message','')))
            if path=='/api/flow/analyze':return scoped_work(flow.analyze)
            if path=='/api/flow/continue':return scoped_work(flow.continue_research)
            if path=='/api/flow/select':return scoped_work(lambda progress:flow.select(data.get('idea_id'),progress))
            raise ValueError('未知研究步骤')
        if path.startswith('/api/model/'):
            return self.model_api(path,data)
        if path=='/api/projects/folders':
            return list_project_folders(data.get('path'))
        if path=='/api/projects/archive':
            self.projects.set_archived(data.get('id'),True)
            project,research=self.projects.selection(project_id,research_id)
            return dict(project_id=project['id'] if project else None,research_id=research['id'] if research else None)
        if path=='/api/projects/restore':
            self.projects.set_archived(data.get('id'),False)
            return self.projects.select(data.get('id'))
        if path=='/api/projects/create':
            return self.projects.create(data.get('name',''),data.get('path'),data.get('consent'))
        if path=='/api/projects/select':
            return self.projects.select(data.get('id'))
        if path=='/api/projects/bind':
            return self.projects.bind(data.get('id'),data.get('path'),data.get('consent'))
        if path=='/api/project/import':
            if 'files' in data:raise ProjectError('请先绑定本机项目文件夹，再创建研究任务')
            return self.projects.create(data.get('name',''),data.get('path'),data.get('consent'))
        selected,_=self.projects.selection(project_id,research_id)
        if path=='/api/research/create':
            return self.projects.create_research(selected['id'] if selected else None,data.get('title'))
        if path=='/api/research/select':
            return self.projects.select(selected['id'] if selected else None,data.get('id'))
        if path=='/api/project/refresh':
            return self.projects.refresh(selected['id'] if selected else None)
        context=self.projects.context(project_id,research_id)
        return self.research_api(path,data,context)

    def job_state(self,job_id,project_id=UNSET,research_id=UNSET):
        with self.lock:
            job=self.jobs.get(job_id)
            if job is None:return None
            if job.get('project_id') is not None:
                project,research=self.projects.selection(project_id,research_id)
                if not project or job['project_id']!=project['id'] or (job.get('research_id') is not None and (not research or job['research_id']!=research['id'])):
                    return None
            return dict(job)

    def research_api(self,path,data,context):
        store=context.store
        project=store.get('project')
        if path=='/api/reader/translate':
            # The reader sends only the selected text, never the PDF or project.
            return self.job('论文翻译',lambda progress:context.reader.translate(data),purpose='translation',scope=context)
        if path=='/api/search':
            query=str(data.get('query',''))
            def search(progress):
                progress('文献侦察 Scout · 请求 arXiv，通常需要数秒')
                result=context.papers.search(query,data.get('days',90),data.get('mode','live'))
                store.set('active_search',result)
                return result
            return self.job('检索论文',search,scope=context)
        search=store.get('active_search',{})
        papers=search.get('papers',[]) if search.get('mode')=='live' else []
        if path=='/api/run':
            ids=data.get('paper_ids',[])
            selected=[p for p in papers if p['id'] in ids] if ids else papers[:6]
            topic=str(data.get('topic') or search.get('query') or '研究探索')[:180]
            constraints=str(data.get('constraints',''))[:2000]
            return self.job('多角色协作',lambda progress:context.agents.run(topic,selected,project,constraints,
                data.get('use_model') is True,data.get('share_project') is True,progress),scope=context)
        if path=='/api/chat':
            message=str(data.get('message','')).strip()[:4000]
            if not message:
                raise ValueError('请输入问题')
            return self.job('项目顾问',lambda progress:context.agents.chat(message,project,papers,
                data.get('use_model') is True,data.get('share_project') is True),scope=context)
        if path=='/api/environment/plan':
            return context.env.plan(data,project)
        if path=='/api/environment/execute':
            # Reserve a job slot before consuming the one-use approval.
            with context.env.lock:
                # Check capacity without consuming approval if scheduling cannot proceed.
                # job() reserves capacity atomically; authorization is performed inside it.
                plan_id=str(data.get('plan_id',''))
                confirmation=str(data.get('confirmation',''))
                check=store.get('plan:'+plan_id)
                if not check or check.get('confirmation')!=confirmation:
                    raise ValueError('计划或授权短语无效')
                def execute(progress):
                    plan=context.env.authorize(plan_id,confirmation,store.get('project'))
                    return context.env.execute(plan,progress)
                return self.job('创建隔离环境',execute,scope=context)
        if path=='/api/notes/add':
            kind=data.get('kind','note')
            if kind not in ('note','idea','paper','experiment','run','translation'):
                raise ValueError('未知笔记类型')
            title=str(data.get('title','研究笔记')).strip()[:200]
            return store.add(kind,title,data.get('body',''))
        if path=='/api/notes/delete':
            store.delete(str(data.get('id','')))
            return dict(ok=True)
        raise ValueError('未知操作')

    def model_api(self,path,data):
        if path in ('/api/model/configure','/api/model/clear-key','/api/model/models','/api/model/check',
                    '/api/model/connections/save','/api/model/connections/use','/api/model/connections/remove'):
            purpose=validate_purpose(data.get('purpose','research'))
            with provider_context(self.model_profiles[purpose],purpose):
                if path=='/api/model/connections/save':
                    return dict(connections=self.connections.save(purpose,data,model_config()))
                if path=='/api/model/connections/use':
                    config=self.connections.load(purpose,data.get('id'))
                    return dict(model=configure_provider(config,self.store,credentials=self.model_credentials[purpose]),
                                connections=self.connections.list())
                if path=='/api/model/connections/remove':
                    return dict(connections=self.connections.remove(purpose,data.get('id')))
                if path=='/api/model/configure':
                    return configure_provider(data,self.store,credentials=self.model_credentials[purpose])
                if path=='/api/model/clear-key':
                    return clear_provider_key(self.store,credentials=self.model_credentials[purpose])
                if path=='/api/model/models':
                    from .agents import list_models
                    return self.job('获取'+('翻译' if purpose=='translation' else '科研')+'模型',lambda progress:list_models(),purpose=purpose)
                from .agents import model_call
                if purpose=='translation':
                    return self.job('翻译连接测试',lambda progress:dict(text=model_call('只将 source_text 翻译为简体中文，只返回译文。',dict(source_text='Connection successful.'))),purpose=purpose)
                return self.job('科研连接测试',lambda progress:dict(text=model_call('只回复“连接成功”。',dict(task='连接测试'))),purpose=purpose)
        raise ValueError('未知操作')


class App(Workspace):
    def __init__(self,data_dir):
        super().__init__(data_dir)
        self.accounts=Accounts(self.store.directory)
        self.workspaces={}

    def workspace(self,user):
        if user is None:
            return self
        with self.lock:
            if user['id'] not in self.workspaces:
                self.workspaces[user['id']]=Workspace(self.store.directory/'users'/user['id'],
                                                     pool=self.pool,allow_environment=False)
            return self.workspaces[user['id']]


def safe_error(error):
    if isinstance(error,urllib.error.HTTPError):
        return '外部服务返回 HTTP '+str(error.code)+'。'+({401:'请核对模型服务 API Key 是否正确或过期。',403:'请核对服务网络要求、访问权限及账号配额。',429:'请求频率或额度受限，请稍后重试。'}.get(error.code,'请检查接口地址、模型权限或服务状态。'))
    if isinstance(error,urllib.error.URLError):
        return '无法连接外部服务：'+str(error.reason)[:180]+'。请检查网络后重试。'
    text=str(error)[:1500]
    cfg=model_config()
    if cfg['key']:
        text=text.replace(cfg['key'],'[REDACTED]')
    return redact(text)


class Handler(BaseHTTPRequestHandler):
    server_version='ResearchPilot/1.0'
    def log_message(self,fmt,*args):
        # Query parameters and payloads are deliberately absent from access logs.
        print('%s %s'%(self.command,self.path.split('?')[0]))

    @property
    def app(self):
        return getattr(self,'_workspace',self.server.app)

    @property
    def cookie_name(self):
        return 'rp_account_'+str(self.server.server_port)

    def account_token(self):
        try:
            cookies=SimpleCookie()
            cookies.load(self.headers.get('Cookie',''))
            return cookies[self.cookie_name].value if self.cookie_name in cookies else None
        except CookieError:
            return None

    def select_workspace(self):
        token=self.account_token()
        self.user=self.server.app.accounts.resolve(token)
        if token and not self.user:
            raise AccountError('登录已过期，请重新登录或继续使用访客空间',401)
        expected=self.headers.get('X-RP-Workspace')
        actual=self.user['id'] if self.user else 'guest'
        if expected is not None and expected!=actual:
            raise AccountError('账号已在其他页面切换，请刷新后继续',409)
        self._workspace=self.server.app.workspace(self.user)

    def account_info(self):
        return dict(user=self.user,mode='account' if self.user else 'guest',
                    preferences=self.user['preferences'] if self.user else dict(DEFAULT_PREFERENCES),
                    email_verification=False)

    def request_scope(self):
        def value(header):
            raw=self.headers.get(header)
            return UNSET if raw is None else (None if raw=='-' else raw)
        return dict(project_id=value('X-RP-Project'),research_id=value('X-RP-Research'))

    def session_cookie(self,token,duration=None):
        cookie=SimpleCookie()
        cookie[self.cookie_name]=token
        cookie[self.cookie_name]['path']='/'
        cookie[self.cookie_name]['httponly']=True
        cookie[self.cookie_name]['samesite']='Strict'
        if duration is not None:
            cookie[self.cookie_name]['max-age']=duration
        # The server deliberately binds only to loopback HTTP. A future HTTPS deployment
        # must also set Secure and replace its local-host access policy.
        return cookie.output(header='').strip()

    def auth_api(self,path,data):
        accounts=self.server.app.accounts
        previous=self.account_token()
        if path=='/api/auth/logout':
            accounts.logout(previous)
            return self.send(200,dict(ok=True),cookie=self.session_cookie('',0))
        if path in ('/api/auth/register','/api/auth/login'):
            # Keep password verification and session creation together with password
            # changes, so an in-flight login cannot revive an obsolete credential.
            with accounts.lock:
                user=(accounts.register(data,self.client_address[0]) if path.endswith('register')
                      else accounts.login(data,self.client_address[0]))
                remember=data.get('remember') is True
                token,duration=accounts.create_session(user['id'],remember,previous)
            return self.send(200,dict(user=user),cookie=self.session_cookie(token,duration if remember else None))
        self.select_workspace()
        if not self.user:
            raise AccountError('请先登录账号',401)
        if path=='/api/auth/password':
            with accounts.lock:
                accounts.change_password(self.user,data,self.client_address[0])
                token,_=accounts.create_session(self.user['id'])
            return self.send(200,dict(ok=True),cookie=self.session_cookie(token))
        raise AccountError('接口不存在',404)

    def valid_host(self):
        return self.headers.get('Host','') in ('127.0.0.1:'+str(self.server.server_port),'localhost:'+str(self.server.server_port))

    def authenticated(self):
        return secrets.compare_digest(self.headers.get('X-RP-Token',''),self.server.app.token)

    def send(self,status,data,ctype='application/json; charset=utf-8',filename=None,script_hash=None,cookie=None):
        raw=json.dumps(data,ensure_ascii=False).encode() if ctype.startswith('application/json') else data
        self.send_response(status)
        self.send_header('Content-Type',ctype)
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        if cookie:
            self.send_header('Set-Cookie',cookie)
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'wasm-unsafe-eval'"+(" 'sha256-"+script_hash+"'" if script_hash else '')+"; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' blob:; worker-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:
            self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError):
            pass

    def do_GET(self):
        if not self.valid_host():
            return self.send(403,dict(error='无效 Host'))
        path=urllib.parse.urlparse(self.path).path
        try:
            if path.startswith('/api/'):
                if not self.authenticated():
                    return self.send(403,dict(error='会话令牌不匹配；请从本机页面访问'))
                self.select_workspace()
                if path=='/api/state':
                    return self.send(200,{**self.app.state(**self.request_scope()),'account':self.account_info()})
                if path=='/api/account':
                    return self.send(200,self.account_info())
                if path.startswith('/api/jobs/'):
                    job=self.app.job_state(path.rsplit('/',1)[-1],**self.request_scope())
                    return self.send(200 if job else 404,job or dict(error='任务不存在，服务重启后请查看研究笔记'))
                if path=='/api/chat/history':
                    context=self.app.projects.context(**self.request_scope())
                    p=context.store.get('project')
                    return self.send(200,context.store.get('chat:'+p['conversation_id'],[]))
                if path=='/api/export':
                    text=export_markdown(self.app.projects.context(**self.request_scope(),require_bound=False))
                    return self.send(200,text.encode(),'text/markdown; charset=utf-8','ResearchPilot-report.md')
                if path=='/api/bibtex':
                    return self.send(200,export_bibtex(self.app.projects.context(**self.request_scope(),require_bound=False)).encode(),'text/plain; charset=utf-8','references.bib')
                return self.send(404,dict(error='接口不存在'))
            if path.startswith('/vendor/pdfjs/'):
                vendor=(ROOT/'static'/'vendor'/'pdfjs').resolve()
                file=(ROOT/'static'/path.lstrip('/')).resolve()
                if vendor not in file.parents or not file.is_file():
                    return self.send(404,b'Not found','text/plain')
                ctype={'.mjs':'text/javascript', '.wasm':'application/wasm',
                       '.css':'text/css'}.get(file.suffix,mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
                return self.send(200,file.read_bytes(),ctype)
            allowed={'/':'index.html','/index.html':'index.html','/app.js':'app.js','/style.css':'style.css',
                     '/reader.js':'reader.js','/reader.css':'reader.css','/accounts.js':'accounts.js','/models.js':'models.js',
                     '/workflow.js':'workflow.js','/team.js':'team.js','/project-manager.js':'project-manager.js','/project-manager.css':'project-manager.css','/favicon.svg':'favicon.svg'}
            if path not in allowed:
                return self.send(404,b'Not found','text/plain')
            file=ROOT/'static'/allowed[path]
            raw=file.read_bytes()
            if file.name=='index.html':
                raw=raw.replace(b'__SESSION_TOKEN__',self.app.token.encode())
            ctype=mimetypes.guess_type(str(file))[0] or 'application/octet-stream'
            return self.send(200,raw,ctype+'; charset=utf-8')
        except AccountError as e:
            self.send(e.status,dict(error=str(e)))
        except ProjectError as e:
            self.send(e.status,dict(error=str(e),scope_error=True))
        except Exception as e:
            self.send(400,dict(error=safe_error(e)))

    def do_POST(self):
        if not self.valid_host() or not self.authenticated():
            return self.send(403,dict(error='无效来源或会话令牌'))
        origin=self.headers.get('Origin')
        if origin and origin not in ('http://127.0.0.1:'+str(self.server.server_port),'http://localhost:'+str(self.server.server_port)):
            return self.send(403,dict(error='跨站请求已拒绝'))
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<0:
                raise ValueError('请求长度无效')
            if size>2_000_000:
                return self.send(413,dict(error='上传上限 2 MB，请只选择项目代码与配置'))
            if not self.headers.get('Content-Type','').startswith('application/json'):
                return self.send(415,dict(error='仅接受 JSON'))
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict):
                raise ValueError('请求必须为 JSON 对象')
            path=urllib.parse.urlparse(self.path).path
            if path.startswith('/api/auth/'):
                return self.auth_api(path,data)
            self.select_workspace()
            if path=='/api/profile/update':
                if not self.user:
                    raise AccountError('登录后即可保存个人偏好',401)
                return self.send(200,dict(user=self.server.app.accounts.update_profile(self.user,data)))
            return self.send(200,self.app.api(path,data,**self.request_scope()))
        except AccountError as e:
            self.send(e.status,dict(error=str(e)))
        except ProjectError as e:
            self.send(e.status,dict(error=str(e),scope_error=True))
        except Exception as e:
            with provider_context(self.app.model_settings):
                self.send(400,dict(error=safe_error(e)))


def export_markdown(app):
    search=app.store.get('active_search',{})
    run=app.store.get('last_run')
    p=app.store.get('project')
    lines=['# 研途 ResearchPilot · 研究工作记录','', '导出时间：'+now(),'',
           '检索模式：'+search.get('mode','未检索')+'；检索时间：'+search.get('retrieved_at','—'),'',
           '> 研究假设需要验证。基于摘要与有限静态扫描，不构成新颖性或有效性证明。','']
    if p:
        lines+=['## 项目',p['name']+' · '+str(p['file_count'])+' 个文件','快照：'+p['fingerprint'],'']
    if hasattr(app,'research_record'):
        lines+=['## 所属研究任务',app.research_record['title'],'项目 ID：'+app.project_id,
                '研究任务 ID：'+app.research_id,'']
    if run:
        lines+=['## 研究方向',run['topic'],'推理模式：'+run['engine'],'约束：'+run['constraints'],'']
        for card in run['ideas']:
            lines+=['### '+card['title'],'假设：'+card['hypothesis'],'','最小实验：'+card['experiment'],'',
                    '指标：'+card['metrics'],'','风险：'+card['risk'],'','参考：'+', '.join(card['refs']),'']
        lines+=['## 反方审查',run['review'],'','## 协作轨迹']+[t['role']+'：'+t['detail'] for t in run['trace']]+['']
        if run.get('agent_runs'):
            lines+=['## Agent 分析与实验计划',
                    '审查状态：'+('仍需修改' if run.get('review_status')=='needs_revision' else '已完成审查，假设仍待验证'),
                    '修订轮数：'+str(run.get('revision_count',0)), '']
            for message in run['agent_runs']:
                lines+=['### '+message['name']+' · 第 '+str(message['iteration'])+' 次调用',
                        '输入产物：'+', '.join(message['inputs']), '', '```json',
                        json.dumps(message['output'],ensure_ascii=False,indent=2), '```', '']
    # The latest run owns its reference set even after a new search.
    sources={x['id']:x for x in search.get('papers',[])}
    if run:
        sources.update({x['id']:x for x in run['papers']})
    lines+=['## 参考文献']+['- ['+x['title']+']('+x['url']+') · '+x['published']+' · '+x['source'] for x in sources.values()]
    lines+=['','## 保存的研究笔记']
    for item in app.store.items():
        body=item['body']
        if item['kind']=='translation' and isinstance(body,dict):
            source=body.get('source',{})
            lines+=['### '+item['title'],'来源：'+str(source.get('title','手动输入'))+
                    ('；PDF 页码：'+', '.join(map(str,source['pages'])) if source.get('pages') else ''),
                    '','原文：',body.get('source_text',''),'','译文：',body.get('translation',''),'',
                    '翻译引擎：'+str(body.get('provider',''))+' / '+str(body.get('model','')),'']
        else:
            lines+=['### '+item['title'],body if isinstance(body,str) else json.dumps(body,ensure_ascii=False,indent=2),'']
    return '\n'.join(lines)


def export_bibtex(app):
    search=app.store.get('active_search',{})
    result=[]
    for p in search.get('papers',[]):
        clean=lambda s: re.sub(r'[{}\\]','',s)
        result.append('@misc{arxiv'+re.sub(r'[^A-Za-z0-9]','',p['id'])+',\n  title={'+clean(p['title'])+'},\n  author={'+clean(p['authors'])+'},\n  year={'+p['published'][:4]+'},\n  eprint={'+p['id']+'},\n  archivePrefix={arXiv},\n  url={'+p['url']+'}\n}')
    return '\n\n'.join(result)


import re

def main():
    parser=argparse.ArgumentParser(description='研途 ResearchPilot · 科研辅助工作台')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--data-dir',default=str(ROOT/'.researchpilot'))
    parser.add_argument('--open',action='store_true')
    args=parser.parse_args()
    app=App(Path(args.data_dir).resolve())
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    server.daemon_threads=True
    server.app=app
    url='http://127.0.0.1:'+str(server.server_port)
    print('\n研途 ResearchPilot '+__version__+'\n打开 '+url+'\n数据目录：'+str(app.store.directory)+'\n按 Ctrl+C 停止\n',flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n正在关闭，等待已授权任务结束…')
    finally:
        server.server_close()
        app.pool.shutdown(wait=True)

if __name__=='__main__':
    main()
