"""Host-owned checks for the two stylesheets a presentation candidate can change."""
import hashlib
import json
from pathlib import Path
import re
import stat


STYLES = ('chat.css', 'conversation-workspace.css')
MAX_STYLE_BYTES = 65536


def plain_path(path, directory=False):
    info = path.lstat()
    same_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink == 1
    if not same_type or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError('Unexpected file type, reparse point, or hard link')


def check_styles(directory):
    plain_path(directory, directory=True)
    if {p.name for p in directory.iterdir()} != set(STYLES):
        raise ValueError('Unexpected candidate contents')
    styles = {}
    for name in STYLES:
        path = directory / name
        plain_path(path)
        with path.open('rb') as source:
            data = source.read(MAX_STYLE_BYTES + 1)
        text = data.decode('utf-8')
        if (not data or len(data) > MAX_STYLE_BYTES or not text.strip()
                or any(ch in text for ch in ('<', '\\'))
                or re.search(r'url\s*\(|@import\b|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', text, re.I)):
            raise ValueError('Styles must be bounded UTF-8 text without external resources or markup')
        styles[name] = data
    return styles


if __name__ == '__main__':
    files = check_styles(Path(__file__).parent / 'editable')
    print(json.dumps({name:hashlib.sha256(content).hexdigest() for name, content in files.items()}, sort_keys=True))
