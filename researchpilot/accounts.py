"""Local email accounts, hashed credentials, revocable sessions and preferences.

Email is a login identifier here; no mailbox ownership is asserted or email sent.
"""
from contextlib import contextmanager
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
import uuid

from .store import now


ITERATIONS = 600_000
DEFAULT_PREFERENCES = dict(theme='system', default_view='home', research_field='',
    default_constraints='', search_days=90, translation_target='zh-CN', glossary='',
    sidebar_collapsed=False, context_hidden=False, prefer_model=False)
VIEWS = ('projects', 'overview', 'home', 'radar', 'reader', 'idea', 'project', 'env', 'notes', 'settings')


class AccountError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def normalize_email(value):
    if not isinstance(value, str):
        raise AccountError('请输入有效的邮箱地址')
    email = value.strip().lower()
    if len(email) > 254 or email.count('@') != 1:
        raise AccountError('请输入有效的邮箱地址')
    local, domain = email.split('@')
    if (not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}", local)
            or local.startswith('.') or local.endswith('.') or '..' in local
            or '.' not in domain or len(domain) > 253
            or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', part)
                   for part in domain.split('.'))):
        raise AccountError('请输入有效的邮箱地址')
    return email


def validate_password(value):
    if not isinstance(value, str) or not 10 <= len(value) <= 128:
        raise AccountError('密码需为 10–128 个字符，可使用中文、空格和符号')
    if not value.strip():
        raise AccountError('密码不能全部为空格')
    return value


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS)
    return 'pbkdf2_sha256${}${}${}'.format(ITERATIONS, salt, digest.hex())


def verify_password(password, encoded):
    if not isinstance(password, str) or len(password) > 128:
        return False
    algorithm, iterations, salt, expected = encoded.split('$')
    if algorithm != 'pbkdf2_sha256':
        return False
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(iterations))
    return hmac.compare_digest(digest.hex(), expected)


def validate_name(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 40 or any(ord(c) < 32 for c in value):
        raise AccountError('昵称需为 1–40 个字符')
    return value.strip()


def validate_preferences(data, existing=None):
    if not isinstance(data, dict) or set(data) - set(DEFAULT_PREFERENCES):
        raise AccountError('个人偏好包含不支持的配置项')
    result = {**DEFAULT_PREFERENCES, **(existing or {})}
    for key, value in data.items():
        if key in ('research_field', 'default_constraints', 'glossary'):
            limit = {'research_field': 180, 'default_constraints': 2000, 'glossary': 1000}[key]
            valid = isinstance(value, str) and len(value) <= limit
        elif key in ('sidebar_collapsed', 'context_hidden', 'prefer_model'):
            valid = type(value) is bool
        elif key == 'search_days':
            valid = type(value) is int and value in (7, 30, 90, 365)
        else:
            choices = {'theme': ('system', 'light', 'dark'), 'default_view': VIEWS,
                       'translation_target': ('zh-CN', 'en')}
            valid = isinstance(value, str) and value in choices[key]
        if not valid:
            raise AccountError('个人偏好格式不正确：' + key)
        result[key] = value
    return result


class Accounts:
    def __init__(self, directory):
        self.path = Path(directory) / 'accounts.sqlite3'
        self.lock = threading.RLock()
        self.attempts = {}
        # Same work factor for unknown email addresses, without storing a real password.
        self.dummy_hash = 'pbkdf2_sha256${}${}${}'.format(ITERATIONS, '00' * 16, '00' * 32)
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL, display_name TEXT NOT NULL,
                    preferences TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
                CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
            ''')
        self.path.chmod(0o600)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(str(self.path), timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def throttle(self, action, address, email=''):
        stamp = time.monotonic()
        limits = [(action + ':ip:' + address, 30 if action == 'login' else 10)]
        if email:
            limits.append((action + ':email:' + email, 10))
        with self.lock:
            self.attempts = {k: [t for t in v if t > stamp - 900]
                             for k, v in self.attempts.items() if v and v[-1] > stamp - 900}
            if any(len(self.attempts.get(key, [])) >= limit for key, limit in limits):
                raise AccountError('尝试次数过多，请在 15 分钟后重试', 429)
            for key, _ in limits:
                self.attempts.setdefault(key, []).append(stamp)

    @staticmethod
    def public(row):
        return dict(id=row['id'], email=row['email'], display_name=row['display_name'],
                    created_at=row['created_at'],
                    preferences={**DEFAULT_PREFERENCES, **json.loads(row['preferences'])})

    def register(self, data, address):
        self.throttle('register', address)
        email = normalize_email(data.get('email'))
        password = validate_password(data.get('password'))
        name = validate_name(data.get('display_name') or email.split('@')[0][:40])
        user_id = uuid.uuid4().hex
        encoded = hash_password(password)
        try:
            with self.connection() as db:
                db.execute('INSERT INTO users VALUES (?,?,?,?,?,?)',
                           (user_id, email, encoded, name, json.dumps(DEFAULT_PREFERENCES), now()))
                user = self.public(db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone())
        except sqlite3.IntegrityError:
            raise AccountError('这个邮箱已注册，请直接登录') from None
        return user

    def login(self, data, address):
        # Count malformed attempts too; bound input before allocating per-email buckets.
        raw = data.get('email', '')
        email = raw.strip().lower() if isinstance(raw, str) and len(raw) <= 254 else ''
        self.throttle('login', address, email)
        with self.connection() as db:
            row = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        matched = verify_password(data.get('password'), row['password_hash'] if row else self.dummy_hash)
        if not row or not matched:
            raise AccountError('邮箱或密码不正确')
        return self.public(row)

    def create_session(self, user_id, remember=False, previous=None):
        token = secrets.token_urlsafe(32)
        duration = 30 * 86400 if remember else 12 * 3600
        with self.connection() as db:
            db.execute('DELETE FROM sessions WHERE expires_at<=?', (time.time(),))
            if previous:
                db.execute('DELETE FROM sessions WHERE token_hash=?', (self.token_hash(previous),))
            db.execute('INSERT INTO sessions VALUES (?,?,?)',
                       (self.token_hash(token), user_id, time.time() + duration))
        return token, duration

    @staticmethod
    def token_hash(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def resolve(self, token):
        if not token or len(token) > 128:
            return None
        with self.connection() as db:
            row = db.execute('SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id '
                             'WHERE token_hash=? AND expires_at>?',
                             (self.token_hash(token), time.time())).fetchone()
        return self.public(row) if row else None

    def logout(self, token):
        if token:
            with self.connection() as db:
                db.execute('DELETE FROM sessions WHERE token_hash=?', (self.token_hash(token),))

    def update_profile(self, user, data):
        if set(data) - {'display_name', 'preferences'}:
            raise AccountError('个人资料包含不支持的字段')
        with self.lock, self.connection() as db:
            row = db.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
            name = validate_name(data.get('display_name', row['display_name']))
            prefs = validate_preferences(data.get('preferences', {}), json.loads(row['preferences']))
            db.execute('UPDATE users SET display_name=?, preferences=? WHERE id=?',
                       (name, json.dumps(prefs, ensure_ascii=False), user['id']))
            return self.public(db.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone())

    def change_password(self, user, data, address):
        self.throttle('password', address, user['email'])
        password = validate_password(data.get('new_password'))
        with self.connection() as db:
            row = db.execute('SELECT password_hash FROM users WHERE id=?', (user['id'],)).fetchone()
        if not verify_password(data.get('current_password'), row['password_hash']):
            raise AccountError('当前密码不正确')
        encoded = hash_password(password)
        with self.connection() as db:
            # Reject a competing password change instead of reviving an old credential.
            changed = db.execute('UPDATE users SET password_hash=? WHERE id=? AND password_hash=?',
                                 (encoded, user['id'], row['password_hash'])).rowcount
            if not changed:
                raise AccountError('密码已发生变化，请重新登录')
            db.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
