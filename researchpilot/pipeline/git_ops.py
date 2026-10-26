"""本地文件夹 ↔ GitHub 仓库绑定（通过 git / gh 命令行，不保存任何凭据）。"""
import re
import shutil
import subprocess
from pathlib import Path

GITHUB_URL = re.compile(r'^(https://github\.com/|git@github\.com:)[\w.-]+/[\w.-]+?(\.git)?$')


class GitError(RuntimeError):
    pass


class GitRepo:
    def __init__(self, folder, runner=subprocess.run):
        self.folder = Path(folder)
        self.runner = runner

    def git(self, *args, check=True):
        if not shutil.which('git'):
            raise GitError('未找到 git，请先安装 git')
        result = self.runner(['git', *args], cwd=str(self.folder), capture_output=True, text=True)
        if check and result.returncode != 0:
            raise GitError('git ' + ' '.join(args) + ' 失败：' + (result.stderr or result.stdout).strip())
        return result.stdout.strip()

    @property
    def initialized(self):
        return (self.folder / '.git').exists()

    def init(self):
        if not self.initialized:
            self.git('init', '-b', 'main')
        return self

    def remote(self):
        return self.git('remote', 'get-url', 'origin', check=False) or ''

    def bind(self, repo_url):
        """绑定远程仓库；repo_url 为空时只做本地 git。"""
        self.init()
        if not repo_url:
            return ''
        if not GITHUB_URL.match(repo_url):
            raise GitError('仅支持 GitHub 仓库地址，如 https://github.com/user/repo.git')
        if self.remote():
            self.git('remote', 'set-url', 'origin', repo_url)
        else:
            self.git('remote', 'add', 'origin', repo_url)
        return repo_url

    def create_github(self, name, private=True):
        """可选：用 gh 在 GitHub 上新建仓库并绑定为 origin。"""
        if not shutil.which('gh'):
            raise GitError('未找到 GitHub CLI（gh），请手动创建仓库后传入 --repo')
        self.init()
        result = self.runner(['gh', 'repo', 'create', name, '--private' if private else '--public',
                              '--source', str(self.folder), '--remote', 'origin'],
                             cwd=str(self.folder), capture_output=True, text=True)
        if result.returncode != 0:
            raise GitError('gh repo create 失败：' + result.stderr.strip())
        return self.remote()

    def commit(self, message, paths=('.',)):
        self.git('add', *paths)
        if not self.git('status', '--porcelain'):
            return False
        self.git('commit', '-m', message)
        return True

    def push(self):
        if not self.remote():
            raise GitError('尚未绑定远程仓库')
        self.git('push', '-u', 'origin', 'HEAD')
