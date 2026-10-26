"""Private local storage for an account's recoverable model credentials.

This file backend keeps credentials out of research databases, browser storage,
exports and source packages. It relies on OS file permissions, not encryption.
"""
import json
import os
from pathlib import Path
import re
import stat
import tempfile


FIELDS = ('base', 'model', 'provider', 'style', 'auth', 'key')


class ProviderCredentials:
    def __init__(self, directory, purpose=None, connection_id=None):
        self.directory = Path(directory)
        if purpose not in (None, 'research', 'translation'):
            raise ValueError('未知模型用途')
        if connection_id is not None:
            if purpose is None or not isinstance(connection_id,str) or not re.fullmatch(r'[a-f0-9]{32}',connection_id):
                raise ValueError('无效服务配置 ID')
            filename='provider-'+purpose+'-'+connection_id+'-credentials.json'
        else:
            filename='provider-' + purpose + '-credentials.json' if purpose else 'provider-credentials.json'
        self.path = self.directory / filename

    def load(self):
        try:
            descriptor = os.open(str(self.path), os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                                 | getattr(os, 'O_NONBLOCK', 0))
        except FileNotFoundError:
            return None
        except OSError:
            raise ValueError('无法读取已保存的模型配置，请在设置中重新保存') from None
        try:
            with os.fdopen(descriptor, 'r', encoding='utf-8') as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError('invalid credential file')
                if os.name == 'posix':
                    os.fchmod(stream.fileno(), 0o600)
                raw = stream.read(32769)
                if len(raw) > 32768:
                    raise ValueError('credential file too large')
                data = json.loads(raw)
                if (not isinstance(data, dict) or data.get('version') != 1
                        or any(not isinstance(data.get(field), str) for field in FIELDS)):
                    raise ValueError('invalid credential data')
                return {field: data[field] for field in FIELDS}
        except (OSError, ValueError, UnicodeError):
            # Never include file contents or parser errors in an API response.
            raise ValueError('已保存的模型配置无法读取，请在设置中重新保存') from None

    def save(self, config):
        data = {'version': 1, **{field: config[field] for field in FIELDS}}
        raw = json.dumps(data, ensure_ascii=False)
        if len(raw) > 32768:
            raise ValueError('模型连接信息过长，无法保存')
        temporary = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            if os.name == 'posix':
                self.directory.chmod(0o700)
            descriptor, temporary = tempfile.mkstemp(prefix='.provider-', dir=str(self.directory))
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            # mkstemp creates a private file; replacing avoids partial writes and
            # never follows a pre-existing destination symlink.
            os.replace(temporary, self.path)
            temporary = None
        except OSError:
            raise ValueError('模型配置未保存，请检查本机数据目录的写入权限') from None
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
