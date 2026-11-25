"""Bounded PNG snapshots explicitly attached to one Codex chat turn."""
from base64 import b64decode
from binascii import Error, crc32
import re
import struct

from .siwc import ChatError


IMAGE_MODEL = 'gpt-6.2-sol'
IMAGE_EFFORT = 'medium'
PNG_PREFIX = 'data:image/png;base64,'
MAX_IMAGE = 4 * 1024 * 1024
IMAGE_SEND_LIMIT = 4 * ((MAX_IMAGE + 2) // 3) + 32768
LOCAL_IMAGE = re.compile(
    r'(?:只|僅)\s*(?:在)?本機|(?:不要|別|不得|禁止|不可|請勿)[^。！？\n]{0,12}(?:外送|上傳|傳給模型|傳給\s*OpenAI)'
    r'|(?:不要|別|不得|禁止|不可|請勿)[^。！？\n]{0,18}(?:分享|傳送|送出)[^。！？\n]{0,12}(?:圖片|截圖|附件)'
    r'|\blocal(?:ly)?[- ]only\b|\b(?:do not|don.t|never)\s+(?:upload|send|share)\s+(?:this|the|my)\s+(?:image|screenshot|attachment)\b',
    re.IGNORECASE,
)


def decode_image(url):
    if not isinstance(url, str) or not url.startswith(PNG_PREFIX):
        raise ChatError('圖片格式不支援。請重新選取 PNG、JPEG 或 WebP。')
    payload = url[len(PNG_PREFIX):]
    if len(payload) > 4 * ((MAX_IMAGE + 2) // 3):
        raise ChatError('圖片超過 4 MiB，請縮小後重新選取。')
    try:
        data = b64decode(payload, validate=True)
        if len(data) > MAX_IMAGE:
            raise ChatError('圖片超過 4 MiB，請縮小後重新選取。')
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError()
        offset, chunks, pixels = 8, 0, False
        while offset + 12 <= len(data):
            size, kind = struct.unpack_from('!I4s', data, offset)
            end = offset + 12 + size
            if end > len(data) or crc32(data[offset+4:end-4]) != struct.unpack_from('!I', data, end-4)[0]:
                raise ValueError()
            if chunks == 0:
                if kind != b'IHDR' or size != 13:
                    raise ValueError()
                w, h, depth, color, compression, filter_type, interlace = struct.unpack_from('!2I5B', data, offset+8)
                if not (1 <= w <= 4096 and 1 <= h <= 4096 and depth == 8 and color in (2, 6)
                        and compression == filter_type == interlace == 0):
                    raise ValueError()
            elif kind == b'IEND' and size == 0 and end == len(data) and pixels:
                return data
            elif kind == b'IDAT':
                pixels |= bool(size)
            elif pixels or kind not in (b'sRGB', b'gAMA', b'cHRM', b'pHYs', b'sBIT', b'iCCP'):
                raise ValueError()
            offset, chunks = end, chunks + 1
    except (Error, ValueError, struct.error):
        pass
    raise ChatError('無法讀取圖片，或圖片尺寸超過 4096 × 4096。請重新選取。')
