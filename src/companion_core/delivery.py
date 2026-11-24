"""SIWC transport only. OAuth stays on the host; no API-key fallback/retries."""
from contextlib import contextmanager
import ssl

import httpx2
from openai import OpenAI
import truststore

from .siwc import RESOURCE


def capabilities(model):
    """Only normalize the explicit catalog schema; never infer from a slug."""
    levels = model.get('supported_reasoning_levels')
    known = {'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'}
    efforts = []
    if isinstance(levels, list):
        efforts = list(dict.fromkeys(v['effort'] for v in levels
            if isinstance(v, dict) and isinstance(v.get('effort'), str)
            and v['effort'] in known))
    default = model.get('default_reasoning_level')
    return {'reasoning_efforts': efforts, 'default_effort': default if default in efforts else None}


@contextmanager
def sdk_stream(token, request, factory=None):
    if factory is not None:  # Dependency injection for isolated transport tests only.
        with factory(token, request) as stream:
            yield stream
        return
    with httpx2.Client(verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
                       trust_env=False, follow_redirects=False,
                       timeout=httpx2.Timeout(300, connect=15)) as http:
        with OpenAI(api_key=token, base_url=RESOURCE, max_retries=0,
                    http_client=http) as client:
            with client.responses.create(**request) as stream:
                yield stream
