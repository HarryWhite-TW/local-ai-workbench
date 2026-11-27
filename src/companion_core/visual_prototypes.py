"""Scoped, inert and versioned visual proposals."""
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
import re
from uuid import UUID

from .resources import SENSITIVE_TEXT
from .siwc import ChatError


CSP = ("default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; "
       "frame-ancestors 'self'; base-uri 'none'; form-action 'none'; sandbox")
ELEMENTS = frozenset("""
    article aside b blockquote br button caption code dd div dl dt em figcaption figure
    footer h1 h2 h3 h4 h5 h6 header hr i kbd li main mark nav ol p pre s section small
    span strong sub sup table tbody td th thead time tr ul
""".split())
VOID = {"br", "hr"}
IDENTIFIERS = re.compile(r"[a-zA-Z0-9_ -]{1,160}\Z")
LANG = re.compile(r"[a-zA-Z0-9-]{1,35}\Z")
CONTROLS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
EXTERNAL_CSS = re.compile(
    r"[<\\]|/\*|\b(?:url|src|image-set|-webkit-image-set)\s*\("
    r"|@(?!media\b|supports\b|container\b)", re.I)


class InvalidPrototype(ValueError):
    pass


class Markup(HTMLParser):
    """Serialize a closed set of elements. Never forward source markup or attributes."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.stack = []
        self.nodes = 0

    def handle_starttag(self, tag, attrs):
        self.nodes += 1
        if tag not in ELEMENTS or self.nodes > 360 or len(self.stack) >= 28:
            raise InvalidPrototype("unsupported_element_or_structure")
        cleaned = {}
        for name, value in attrs:
            if name in cleaned or not isinstance(value, str):
                raise InvalidPrototype("unsupported_attribute")
            permitted = ((name in ("class", "id") and IDENTIFIERS.fullmatch(value))
                         or (name == "lang" and LANG.fullmatch(value))
                         or (name == "dir" and value in ("auto", "rtl", "ltr"))
                         or (name in ("aria-label", "title") and safe_text(value, 140))
                         or (name in ("colspan", "rowspan") and tag in ("td", "th")
                             and re.fullmatch(r"[1-9][0-9]?", value))
                         or (name == "type" and tag == "button" and value == "button")
                         or (name == "role" and value == "presentation"))
            if not permitted:
                raise InvalidPrototype("unsupported_attribute")
            cleaned[name] = value
        if tag == "button":
            cleaned["type"] = "button"
        attributes = "".join(f' {key}="{escape(value, quote=True)}"' for key, value in cleaned.items())
        self.parts.append(f"<{tag}{attributes}>")
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            raise InvalidPrototype("unbalanced_markup")
        self.parts.append(f"</{tag}>")

    def handle_startendtag(self, tag, attrs):
        if tag not in VOID:
            raise InvalidPrototype("unbalanced_markup")
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        if CONTROLS.search(data) or SENSITIVE_TEXT.search(data):
            raise InvalidPrototype("unsupported_text")
        self.parts.append(escape(data, quote=False))

    def handle_decl(self, decl):
        raise InvalidPrototype("unsupported_element_or_structure")

    def unknown_decl(self, data):
        raise InvalidPrototype("unsupported_element_or_structure")

    def handle_pi(self, data):
        raise InvalidPrototype("unsupported_element_or_structure")


def safe_text(value, cap):
    return (isinstance(value, str) and 0 < len(value.strip()) <= cap
            and not CONTROLS.search(value) and not SENSITIVE_TEXT.search(value))


@dataclass(frozen=True)
class Prototype:
    title: str
    html: str
    css: str
    parent: str | None

    def document(self):
        return ('<!doctype html><html><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{escape(self.title)}</title>'
                '<style>html{color-scheme:light dark}*{box-sizing:border-box}'
                f'body{{margin:0;font-family:system-ui}}\n{self.css}</style>'
                f'</head><body>{self.html}</body></html>').encode("utf-8")


def validate(title, html, css, parent=None):
    if (not safe_text(title, 90) or not isinstance(html, str) or not isinstance(css, str)
            or len(html) > 18000 or len(css) > 14000 or not html.strip()):
        raise InvalidPrototype("invalid_size_or_title")
    if CONTROLS.search(html) or CONTROLS.search(css) or SENSITIVE_TEXT.search(css) or EXTERNAL_CSS.search(css):
        raise InvalidPrototype("unsupported_style_or_resource")
    parser = Markup()
    try:
        parser.feed(html)
        parser.close()
    except AssertionError:
        raise InvalidPrototype("unbalanced_markup") from None
    if parser.stack or not parser.nodes:
        raise InvalidPrototype("unbalanced_markup")
    return Prototype(title.strip(), "".join(parser.parts), css, parent)


class VisualPrototypes:
    def __init__(self, chat):
        self.chat = chat
        self.pending = None
        with chat.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS chat_prototypes (
                turn TEXT PRIMARY KEY REFERENCES turns(id),
                parent TEXT REFERENCES chat_prototypes(turn),
                title TEXT NOT NULL, html TEXT NOT NULL, css TEXT NOT NULL)""")

    def list(self, db, chat_id, owner):
        return [dict(row) for row in db.execute("""
            SELECT p.turn, p.parent, p.title FROM chat_prototypes p
            JOIN turns t ON t.id=p.turn JOIN chats c ON c.id=t.chat
            WHERE c.id=? AND c.account=? AND c.workspace=? AND t.status='complete'
            ORDER BY t.rowid""", (chat_id, owner, self.chat.workspace))]

    def get(self, db, chat_id, owner, turn):
        try:
            if str(UUID(turn)) != turn:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ChatError("找不到這個對話的視覺版本。") from None
        row = db.execute("""
            SELECT p.title, p.html, p.css, p.parent FROM chat_prototypes p
            JOIN turns t ON t.id=p.turn JOIN chats c ON c.id=t.chat
            WHERE p.turn=? AND c.id=? AND c.account=? AND c.workspace=? AND t.status='complete'
        """, (turn, chat_id, owner, self.chat.workspace)).fetchone()
        if row is None:
            raise ChatError("找不到這個對話的視覺版本。")
        return validate(row["title"], row["html"], row["css"], row["parent"])

    def document(self, chat_id, turn):
        with self.chat.lock, getattr(self.chat.auth, "lock", self.chat.lock), self.chat.connect() as db:
            owner = self.chat._project_owner(db, chat_id, require_chat=True)
            return self.get(db, chat_id, owner, turn).document()

    def stage(self, chat_id, owner, turn, prototype):
        with self.chat.lock:
            if self.chat.busy == {"chat": chat_id, "turn": turn} and not self.chat.cancel_event.is_set():
                self.pending = (chat_id, owner, turn, prototype)

    def finish(self, db, turn, completed):
        entry, self.pending = self.pending, None
        if not completed or entry is None or entry[2] != turn:
            return
        chat_id, owner, _, value = entry
        try:
            if self.chat._project_owner(db, chat_id, require_chat=True) != owner:
                return
            if value.parent:
                self.get(db, chat_id, owner, value.parent)
        except (ChatError, InvalidPrototype):
            return
        db.execute("INSERT INTO chat_prototypes VALUES (?,?,?,?,?)",
                   (turn, value.parent, value.title, value.html, value.css))
