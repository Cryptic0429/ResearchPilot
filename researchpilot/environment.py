"""Plan -> exact user confirmation -> constrained executor. No LLM commands."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import threading
import time
import uuid
from .store import now

PIN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,70}==[0-9][A-Za-z0-9. +!-]{0,35}$')
# No whitespace, options, URLs, editable installs, includes, or shell syntax.
VERSION = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,70}==[0-9][A-Za-z0-9.!+-]{0,35}$')


def validate_packages(lines):
    accepted, rejected=[],[]
    for raw in lines[:80]:
        line=raw.strip()
        if not line or line.startswith('#'):
            continue
        if VERSION.fullmatch(line):
            accepted.append(line)
        else:
            rejected.append(line[:200])
    return sorted(set(accepted)), rejected


class Environments:
    def __init__(self,store):
        self.store=store
        self.lock=threading.RLock()

    def plan(self, data, project):
        target=data.get('target','local')
        if target not in ('local','remote'):
            raise ValueError('未知环境目标')
        profile=data.get('profile','minimal')
        if profile not in ('minimal','project'):
            raise ValueError('未知依赖方案')
        lines=project.get('requirements',[]) if profile=='project' and project else []
        if profile=='project' and not lines:
            raise ValueError('项目中未发现 requirements.txt；请使用基础环境，或在项目中补充精确版本后刷新')
        packages,rejected=validate_packages(lines)
        if rejected:
            raise ValueError('自动安装仅接受 name==version；请先人工固定这些依赖：'+', '.join(rejected))
        plan_id=uuid.uuid4().hex
        if target=='remote':
            host=str(data.get('host','')).strip()
            user=str(data.get('user','')).strip()
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,200}',host) or '..' in host:
                raise ValueError('请输入有效 SSH 主机名或 IPv4 地址，不支持 SSH 别名或命令选项')
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,40}',user):
                raise ValueError('请输入有效 SSH 用户名')
            port=int(data.get('port',22))
            if not 1<=port<=65535:
                raise ValueError('SSH 端口不合法')
            directory='researchpilot-envs/'+plan_id[:12]
            remote_dir='$HOME/'+directory
            script='set -eu\numask 077\nmkdir -p "$HOME/researchpilot-envs"\npython3 -m venv "'+remote_dir+'"\n'
            py='"'+remote_dir+'/bin/python"'
            if packages:
                script+=py+' -m pip --isolated install --index-url https://pypi.org/simple --only-binary=:all: '+' '.join(shlex.quote(p) for p in packages)+'\n'
            script+=py+' -m pip freeze\n'+py+' --version\n'
            command=['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10',
                     '-o','ClearAllForwardings=yes','-p',str(port),user+'@'+host,'sh','-s']
            location=user+'@'+host+':~/'+directory
        else:
            directory=str(self.store.directory/'environments'/plan_id[:12])
            py=str(Path(directory)/('Scripts/python.exe' if os.name=='nt' else 'bin/python'))
            command=[[sys.executable,'-m','venv',directory]]
            if packages:
                command.append([py,'-m','pip','--isolated','install','--index-url','https://pypi.org/simple','--only-binary=:all:']+packages)
            command.extend([[py,'-m','pip','freeze'],[py,'--version']])
            script=None
            location=directory
        plan=dict(id=plan_id,target=target,profile=profile,packages=packages,location=location,command=command,
                  script=script,created_at=now(),expires_at=time.time()+900,status='awaiting_approval',
                  project_fingerprint=project['fingerprint'] if project else None,
                  confirmation='授权配置 '+plan_id[:8],
                  notice='将创建全新隔离环境；依赖从 PyPI 下载且仅接受 wheel。不会执行仓库脚本。可能消耗网络、磁盘及服务器资源。CUDA、系统库和未固定依赖需要人工处理。')
        plan['digest']=hashlib.sha256(json.dumps(command,sort_keys=True).encode()+(script or '').encode()).hexdigest()
        self.store.set('plan:'+plan_id,plan)
        self.store.event('environment_plan',dict(id=plan_id,target=target,location=location,packages=packages))
        return plan

    def authorize(self,plan_id,confirmation,project):
        with self.lock:
            plan=self.store.get('plan:'+plan_id)
            if not plan or plan['status']!='awaiting_approval' or time.time()>plan['expires_at']:
                raise ValueError('计划已失效或已执行，请重新生成')
            if confirmation!=plan['confirmation']:
                raise ValueError('请输入计划显示的完整授权短语')
            if plan['project_fingerprint'] != (project['fingerprint'] if project else None):
                raise ValueError('项目快照已改变，请重新生成安装计划')
            plan['status']='authorized'
            self.store.set('plan:'+plan_id,plan)
            self.store.event('environment_authorized',dict(id=plan_id,digest=plan['digest'],target=plan['target']))
            return plan

    def execute(self,plan,progress):
        logs=[]
        def run(args, stdin=None):
            progress('正在执行：'+shlex.join(args))
            env={k:v for k,v in os.environ.items() if not k.startswith(('PIP_','PYTHON','RP_','OPENAI_'))}
            result=subprocess.run(args,input=stdin,text=True,capture_output=True,timeout=240,env=env)
            logs.append(dict(command=args,code=result.returncode,stdout=result.stdout[-24000:],stderr=result.stderr[-12000:]))
            if result.returncode:
                raise ValueError('命令退出码 '+str(result.returncode)+'；'+result.stderr[-1000:])
        try:
            if plan['target']=='remote':
                run(plan['command'],plan['script'])
            else:
                for cmd in plan['command']:
                    run(cmd)
            plan['status']='completed'
        except Exception as error:
            plan['status']='failed'
            plan['error']=str(error)[:2000]
        plan['logs']=logs
        plan['finished_at']=now()
        self.store.set('plan:'+plan['id'],plan)
        self.store.event('environment_'+plan['status'],dict(id=plan['id'],target=plan['target']))
        return plan
