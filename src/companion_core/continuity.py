"""Owner-scoped, DPAPI-encrypted UI continuity; never model input or authority."""
import json
import math
import os

from .siwc import ChatError, dpapi


MAX_BYTES = 1_100_000


class Continuity:
    def __init__(self, chat):
        self.chat = chat
        self.available = os.name == 'nt'
        with chat.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS companion_sessions (
                workspace TEXT NOT NULL, account TEXT NOT NULL,
                revision INTEGER NOT NULL, payload BLOB NOT NULL,
                PRIMARY KEY (workspace, account))''')

    def owner(self, db, body, keys):
        if (not self.available or not isinstance(body, dict)
                or set(body) != {'workspace', 'account', *keys}
                or body['workspace'] != self.chat.workspace
                or body['account'] != self.chat._project_owner(db)):
            raise ChatError('帳戶或工作區已變更，沒有讀取或保存接續資料。')
        return body['account']

    @staticmethod
    def number(value, minimum=0, maximum=10_000_000):
        return type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum

    def validate(self, db, value, account):
        if not isinstance(value, dict) or set(value) != {'selected', 'drafts', 'positions', 'preferences'}:
            raise ValueError()
        chats = {r[0] for r in db.execute('SELECT id FROM chats WHERE workspace=? AND account=?',
                                        (self.chat.workspace, account))} | {''}
        if not isinstance(value['selected'], str) or value['selected'] not in chats:
            raise ValueError()
        drafts, positions = value['drafts'], value['positions']
        if not isinstance(drafts, list) or len(drafts) > 64 or not isinstance(positions, list) or len(positions) > 256:
            raise ValueError()
        seen = set()
        for pair in drafts:
            if not isinstance(pair, list) or len(pair) != 2 or not isinstance(pair[0], str):
                raise ValueError()
            key = json.loads(pair[0])
            if (not isinstance(key, list) or len(key) != 2 or key[0] != account
                    or not isinstance(key[1], str) or key[1] not in chats
                    or pair[0] in seen or not isinstance(pair[1], str) or len(pair[1]) > 4000):
                raise ValueError()
            seen.add(pair[0])
        seen.clear()
        for pair in positions:
            if (not isinstance(pair, list) or len(pair) != 2 or not isinstance(pair[0], str)
                    or pair[0] not in chats or pair[0] in seen or not self.number(pair[1])):
                raise ValueError()
            seen.add(pair[0])
        preferences = value['preferences']
        if not isinstance(preferences, dict) or set(preferences) != {'material', 'sidebar', 'window'}:
            raise ValueError()
        material, window = preferences['material'], preferences['window']
        if (not isinstance(material, dict) or set(material) != {'theme', 'motion', 'quality'}
                or material['theme'] not in ('obsidian', 'umber', 'porcelain')
                or material['motion'] not in ('auto', 'full', 'reduced')
                or material['quality'] not in ('high', 'low')
                or preferences['sidebar'] not in (None, 'expanded', 'collapsed')
                or not isinstance(window, dict) or set(window) != {'mode', 'window', 'mini'}
                or window['mode'] not in ('floating', 'dock-left', 'dock-right', 'split-left', 'split-right', 'reading')):
            raise ValueError()
        for key in ('window', 'mini'):
            rect = window[key]
            if rect is not None and (not isinstance(rect, dict) or set(rect) != {'x', 'y', 'width', 'height'}
                    or not all(self.number(rect[k], -20000, 20000) for k in rect)
                    or rect['width'] <= 0 or rect['height'] <= 0):
                raise ValueError()
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf8')
        if len(encoded) > MAX_BYTES:
            raise ValueError()
        return encoded

    def get(self, body):
        with self.chat.lock, getattr(self.chat.auth, 'lock', self.chat.lock), self.chat.connect() as db:
            account = self.owner(db, body, set())
            row = db.execute('SELECT revision,payload FROM companion_sessions WHERE workspace=? AND account=?',
                             (self.chat.workspace, account)).fetchone()
            value = None
            if row:
                try:
                    if not isinstance(row['payload'], bytes) or len(row['payload']) > MAX_BYTES + 16384:
                        raise ValueError()
                    value = json.loads(dpapi(row['payload'], decrypt=True))
                    self.validate(db, value, account)
                except Exception:
                    raise ChatError('本機接續資料無法安全讀取；原記錄已保留，沒有覆寫。') from None
            self.owner(db, body, set())
            return {'account': account, 'workspace': self.chat.workspace,
                    'revision': row['revision'] if row else 0, 'value': value}

    def save(self, body):
        with self.chat.lock, getattr(self.chat.auth, 'lock', self.chat.lock), self.chat.connect() as db:
            account = self.owner(db, body, {'revision', 'value'})
            revision = body['revision']
            if type(revision) is not int or not 0 <= revision < 2**53:
                raise ChatError('接續資料版本不正確；沒有保存。')
            try:
                encoded = self.validate(db, body['value'], account)
            except (ValueError, TypeError, KeyError):
                raise ChatError('接續資料格式或範圍不正確；沒有保存。') from None
            current = db.execute('SELECT revision,payload FROM companion_sessions WHERE workspace=? AND account=?',
                                 (self.chat.workspace, account)).fetchone()
            if (current['revision'] if current else 0) != revision:
                raise ChatError('另一個視窗已保存較新的接續資料；本分頁草稿仍保留，請先核對已保存版本。')
            if current:
                try:
                    if not isinstance(current['payload'], bytes) or len(current['payload']) > MAX_BYTES + 16384:
                        raise ValueError()
                    self.validate(db, json.loads(dpapi(current['payload'], decrypt=True)), account)
                except Exception:
                    raise ChatError('本機接續資料無法安全讀取；原記錄已保留，沒有覆寫。') from None
            try:
                encrypted = dpapi(encoded)
            except Exception:
                raise ChatError('Windows 加密保存未完成；本分頁草稿仍保留。') from None
            self.owner(db, body, {'revision', 'value'})
            if revision:
                changed = db.execute('''UPDATE companion_sessions SET revision=?,payload=?
                    WHERE workspace=? AND account=? AND revision=?''',
                    (revision + 1, encrypted, self.chat.workspace, account, revision)).rowcount
            else:
                changed = db.execute('INSERT OR IGNORE INTO companion_sessions VALUES (?,?,?,?)',
                                     (self.chat.workspace, account, 1, encrypted)).rowcount
            if changed != 1:
                raise ChatError('另一個視窗已保存較新的接續資料；沒有覆寫。')
            return {'account': account, 'workspace': self.chat.workspace, 'revision': revision + 1}
