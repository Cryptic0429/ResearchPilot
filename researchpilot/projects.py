"""Bounded, read-only project snapshots. No repository code is imported or executed."""
import ast
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
from .store import now

ALLOWED = {'.py','.md','.txt','.toml','.yaml','.yml','.json','.r','.R','.js','.ts','.sh','.csv'}
SKIP_DIRS = {'node_modules','venv','env','__pycache__','dist','build','data','datasets','wandb','checkpoints','outputs'}
SECRET = re.compile(r'(secret|credential|password|token|private|id_rsa|id_ed25519|\.env|\.pem|\.key)', re.I)
ASSIGNMENT = re.compile(r'(?im)((?:[\w-]*(?:api[_-]?key|secret|password|token)[\w-]*)\s*[:=]\s*)[^\n,}]+')


def redact(text):
    text = ASSIGNMENT.sub(r'\1[REDACTED]', text)
    text = re.sub(r'\bsk-[A-Za-z0-9_-]{12,}', '[REDACTED]', text)
    return text


def safe_name(name):
    p = PurePosixPath(name.replace('\\','/'))
    return not p.is_absolute() and all(x not in ('..','') and not x.startswith('.') and x not in SKIP_DIRS and not SECRET.search(x) for x in p.parts)


def scan_path(path, allow_empty=False):
    root = Path(path).expanduser()
    if root.is_symlink():
        raise ValueError('请选择实际项目目录，不能使用符号链接')
    root = root.resolve()
    if not root.is_dir() or root == Path(root.anchor) or root == Path.home():
        raise ValueError('请选择具体项目文件夹，不能扫描磁盘根目录或用户主目录')
    files = []
    for base, dirs, names in os.walk(str(root), followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in SKIP_DIRS and not SECRET.search(d)
                         and not (Path(base)/d).is_symlink() and len((Path(base)/d).relative_to(root).parts)<=6)
        for name in sorted(names):
            p = Path(base)/name
            rel = p.relative_to(root).as_posix()
            if not safe_name(rel) or p.is_symlink() or p.suffix not in ALLOWED:
                continue
            if p.stat().st_size > 128_000:
                continue
            try:
                text = p.read_text(encoding='utf-8')
                if '\x00' not in text:
                    files.append(dict(path=rel, content=text))
            except (OSError, UnicodeError):
                continue
            if len(files)>=150:
                break
        if len(files)>=150:
            break
    result = snapshot(root.name, files, allow_empty=allow_empty)
    result['local_path'] = str(root)
    return result


def snapshot(name, files, allow_empty=False):
    selected, total = [], 0
    seen = set()
    for item in files[:500]:
        path = str(item.get('path',''))[:300]
        if not path or not safe_name(path) or path in seen or PurePosixPath(path).suffix not in ALLOWED:
            continue
        seen.add(path)
        raw = str(item.get('content',''))
        text = redact(raw[:16000])
        if total+len(text)>180_000 or len(selected)>=150:
            break
        total += len(text)
        selected.append(dict(path=path, content=text, hash=hashlib.sha256(raw.encode()).hexdigest(), lines=len(raw.splitlines()), truncated=len(raw)>16000))
    if not selected and not allow_empty:
        raise ValueError('未找到可分析的文本文件；支持 Python、README、requirements、配置等')
    digest = hashlib.sha256(''.join(f['path']+f['hash'] for f in sorted(selected,key=lambda x:x['path'])).encode()).hexdigest()
    requirements, imports, findings = [], set(), []
    joined = '\n'.join(f['content'] for f in selected)
    for f in selected:
        if PurePosixPath(f['path']).name == 'requirements.txt':
            requirements = [line.strip() for line in f['content'].splitlines() if line.strip() and not line.startswith('#')][:80]
        if f['path'].endswith('.py'):
            try:
                tree = ast.parse(f['content'])
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imports.update(a.name.split('.')[0] for a in node.names)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        imports.add(node.module.split('.')[0])
            except SyntaxError:
                pass
        for i,line in enumerate(f['content'].splitlines(),1):
            if re.search(r'TODO|FIXME|random\.seed|manual_seed|train_test_split|top_k\s*=|topk\s*=', line, re.I):
                findings.append(dict(file=f['path'], line=i, text=line.strip()[:200]))
    has_tests = any('test' in f['path'].lower() for f in selected)
    risks = []
    if not has_tests:
        risks.append('扫描范围内未发现测试文件；建议增加最小回归与数据泄漏检查。')
    if not re.search(r'random\.seed|manual_seed|random_state|seed\s*:', joined):
        risks.append('扫描文本中未发现常见随机种子设置；请核对实验可复现性。')
    if not re.search(r'held.?out|test.?set|测试集|train_test_split', joined, re.I):
        risks.append('扫描文本中未发现明确的留出测试集声明；请核对数据划分。')
    return dict(name=str(name)[:120], files=selected, file_count=len(selected), bytes=total, fingerprint=digest,
                requirements=requirements, imports=sorted(imports), findings=findings[:30], risks=risks,
                has_tests=has_tests, scanned_at=now(), local_path=None,
                limits='最多 150 个文件，单文件读取 ≤128 KB、分析前16k字符、总分析 ≤180k字符；跳过隐藏目录、敏感名称、符号链接与数据目录。缺失提示仅针对扫描范围。')


def compare(old, new):
    a = {x['path']:x['hash'] for x in old.get('files',[])}
    b = {x['path']:x['hash'] for x in new['files']}
    return dict(added=sorted(set(b)-set(a)), removed=sorted(set(a)-set(b)),
                changed=sorted(k for k in set(a)&set(b) if a[k]!=b[k]))


def public_project(project):
    if not project:
        return None
    return {**project, 'files':[{k:v for k,v in f.items() if k!='content'} for f in project['files']]}
