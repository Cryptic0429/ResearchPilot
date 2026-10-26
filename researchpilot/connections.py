"""Saved official/relay/local connection snapshots, scoped to one workspace.

Public metadata lives in SQLite; keys use private credential files for accounts,
or memory only for guests. Applying a snapshot is always an explicit operation.
"""
import threading
import uuid

from .credentials import ProviderCredentials
from .store import now


CONFIG_FIELDS=('provider','base','model','style','auth')
SOURCES=('official','relay','local','custom')


class ConnectionLibrary:
    def __init__(self,store,persistent):
        self.store=store
        self.persistent=persistent
        self.lock=threading.RLock()
        self.guest_entries=[]
        self.guest_configs={}

    def entries(self):
        return self.store.get('model_connections',[]) if self.persistent else self.guest_entries

    def write_entries(self,entries):
        if self.persistent:self.store.set('model_connections',entries)
        else:self.guest_entries=entries

    def credentials(self,entry):
        return ProviderCredentials(self.store.directory,entry['purpose'],entry['id'])

    def resolve(self,purpose,connection_id):
        if purpose not in ('research','translation') or not isinstance(connection_id,str):
            raise ValueError('无效服务配置')
        entry=next((e for e in self.entries() if e['id']==connection_id and e['purpose']==purpose),None)
        if entry is None:raise ValueError('当前用途下不存在此服务配置')
        return entry

    def config(self,entry):
        config=self.credentials(entry).load() if self.persistent else self.guest_configs.get(entry['id'])
        if config is None or any(config.get(k)!=entry[k] for k in CONFIG_FIELDS):
            raise ValueError('服务配置无法读取，请重新保存')
        if not config['key'] and config['auth']!='none':
            raise ValueError('服务配置缺少密钥，请重新保存')
        return dict(config)

    def list(self):
        with self.lock:
            result=[]
            for entry in self.entries():
                try:
                    config=self.config(entry)
                    available=True
                    key_saved=bool(self.persistent and config['key'])
                except ValueError:
                    available=False
                    key_saved=False
                result.append({**entry,'available':available,'key_saved':key_saved})
            return result

    def save(self,purpose,data,config):
        if purpose not in ('research','translation'):raise ValueError('未知模型用途')
        label=data.get('label')
        source=data.get('source','custom')
        if not isinstance(label,str) or not 1<=len(label.strip())<=60:
            raise ValueError('服务配置名称需为 1–60 个字符')
        if not isinstance(source,str) or source not in SOURCES:
            raise ValueError('服务来源仅支持官方、中转站、本地或自定义')
        if not config['ready']:
            raise ValueError('请先保存并配置好当前连接，再存入服务配置库')
        if source=='local':
            from urllib.parse import urlparse
            if urlparse(config['base']).hostname not in ('localhost','127.0.0.1'):
                raise ValueError('本地来源需使用 localhost 或 127.0.0.1 地址')
        with self.lock:
            entries=self.entries()
            previous=next((e for e in entries if e['purpose']==purpose and e['label']==label.strip()),None)
            if previous is None and sum(e['purpose']==purpose for e in entries)>=20:
                raise ValueError('每种用途最多保存 20 组服务配置')
            entry=dict(id=uuid.uuid4().hex,purpose=purpose,label=label.strip(),source=source,
                       updated_at=now(),**{k:config[k] for k in CONFIG_FIELDS})
            private={k:config[k] for k in CONFIG_FIELDS+('key',)}
            # Use a new credential file when replacing a named snapshot. A failed
            # metadata write cannot change the old snapshot or active connection.
            if self.persistent:self.credentials(entry).save(private)
            else:self.guest_configs[entry['id']]=private
            updated=[e for e in entries if previous is None or e['id']!=previous['id']]+[entry]
            try:self.write_entries(updated)
            except Exception:
                self.remove_credentials(entry)
                raise
            if previous:self.remove_credentials(previous)
            return self.list()

    def remove_credentials(self,entry):
        if self.persistent:
            try:self.credentials(entry).path.unlink()
            except FileNotFoundError:pass
        else:self.guest_configs.pop(entry['id'],None)

    def load(self,purpose,connection_id):
        with self.lock:return self.config(self.resolve(purpose,connection_id))

    def remove(self,purpose,connection_id):
        with self.lock:
            entry=self.resolve(purpose,connection_id)
            self.remove_credentials(entry)
            self.write_entries([e for e in self.entries() if e['id']!=connection_id])
            return self.list()
