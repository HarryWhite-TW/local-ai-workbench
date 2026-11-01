"""Synthetic HTTP/JWT fixtures only; these tests never establish real model access."""
import base64
import hashlib
import http.client
import json
from pathlib import Path
import threading
import time
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
import jwt
import pytest

from src.companion_core.chat import Conversations, sources
from src.companion_core.daily import WorkNotConnected
from src.companion_core.review import ReviewStore
from src.companion_core.siwc import ChatError, ISSUER, SCOPES, SignIn, Vault
from src.companion_core.surface import Surface, make_server


@pytest.fixture
def env(tmp_path, monkeypatch):
    workspace = tmp_path / "project"
    workspace.mkdir()
    (workspace / "README.md").write_text("Public prototype\nLocal documents only\n", encoding="utf-8")
    (workspace / "AGENTS.md").write_text("No arbitrary tools\n", encoding="utf-8")
    vault = Vault(tmp_path / "private", workspace)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public.update(kid="test", alg="RS256", use="sig")
    calls = []
    opened = []
    config = {"nonce": None, "sub": "fixture-user", "scopes": SCOPES, "events": None}

    def token():
        claims = {"iss": ISSUER, "aud": "oaiapp_fixture", "sub": config["sub"],
                  "iat": int(time.time()), "exp": int(time.time()) + 3600,
                  "nonce": config["nonce"], "email": "fixture@example.invalid"}
        return {"access_token": "synthetic-access-only", "refresh_token": "synthetic-refresh-only",
                "token_type": "Bearer", "expires_in": 3600, "scope": config["scopes"],
                "id_token": jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test"})}

    def handle(request):
        calls.append(request)
        path = request.url.path
        if path.endswith("openid-configuration"):
            return httpx.Response(200, json={"issuer": ISSUER, "jwks_uri": ISSUER + "/.well-known/jwks.json",
                                            "revocation_endpoint": ISSUER + "/api/accounts/oauth/revoke"})
        if path.endswith("jwks.json"):
            return httpx.Response(200, json={"keys": [public]})
        if path.endswith("/token"):
            failure = config.get("token_failure")
            if isinstance(failure, Exception):
                raise failure
            if failure:
                return httpx.Response(failure, json={"error": "SYNTHETIC_PRIVATE_PROVIDER_DETAIL"})
            return httpx.Response(200, json=token())
        if path.endswith("/revoke"):
            return httpx.Response(200)
        if path.endswith("/models"):
            failure = config.get("model_failure")
            if isinstance(failure, Exception):
                raise failure
            if failure:
                return httpx.Response(failure, json={"error": "SYNTHETIC_PRIVATE_PROVIDER_DETAIL"})
            if config.get("malformed_models"):
                return httpx.Response(200, json={"unexpected": "SYNTHETIC_PRIVATE_PROVIDER_DETAIL"})
            return httpx.Response(200, json={"models": [{"slug": "fixture-model", "display_name": "Synthetic test model", "visibility": "list"}]})
        if path.endswith("/responses"):
            events = config["events"]
            if events is None:
                payload = json.loads(request.content)
                answer = "Synthetic test only."
                if "本輪選定來源" in payload["input"][-1]["content"]:
                    answer += " Public prototype [S1:L1]"
                if len(payload["input"]) > 1:
                    assert payload["input"][1]["role"] == "assistant"
                    answer += " Prior answer retained."
                events = [{"type": "response.created", "response": {"id": "resp_fixture"}},
                    {"type": "response.completed", "response": {"id": "resp_fixture", "status": "completed",
                     "output": [{"type": "message", "role": "assistant", "status": "completed",
                                 "content": [{"type": "output_text", "text": answer}]}]}}]
            return httpx.Response(200, text="".join("data: " + json.dumps(e) + "\n\n" for e in events),
                                  headers={"content-type": "text/event-stream"})
        raise AssertionError("Unexpected HTTP request")

    http = httpx.Client(transport=httpx.MockTransport(handle))
    auth = SignIn(vault, http)
    monkeypatch.setattr("src.companion_core.siwc.webbrowser.open", lambda url: opened.append(url) or True)
    chat = Conversations(workspace, vault.directory, auth)
    value = dict(workspace=workspace, vault=vault, auth=auth, chat=chat, config=config, opened=opened, calls=calls, key=key)
    yield value
    if chat.worker:
        chat.worker.join(5)
    http.close()
    vault.close()


def login(e):
    e["auth"].begin("http://127.0.0.1:12345")
    query = parse_qs(urlsplit(e["opened"][-1]).query)
    e["config"]["nonce"] = query["nonce"][0]
    e["auth"].callback({"code": "fixture-code", "state": query["state"][0], "client_id": "oaiapp_fixture"})
    return query


def send(e, chat=None, question="What is this project?", selected=None):
    c = e["chat"]
    c.catalog()
    selected = ["readme"] if selected is None else selected
    preview = sources(e["workspace"], selected)
    result = c.submit({"chat": chat, "question": question, "sources": selected, "model": "fixture-model",
                       "preview": {r["key"]: r["sha256"] for r in preview} if selected else None})
    c.worker.join(5)
    assert not c.worker.is_alive()
    return c.get(result["chat"])


def test_pkce_identity_dpapi_restart_and_exclusive_owner(env):
    query = login(env)
    assert query["client_id"] == ["dynamic_agent_client"]
    assert query["code_challenge_method"] == ["S256"]
    exchange = parse_qs(env["calls"][0].content.decode())
    verifier = exchange["code_verifier"][0]
    assert query["code_challenge"] == [base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")]
    assert exchange["client_id"] == ["oaiapp_fixture"]
    assert exchange["redirect_uri"] == query["redirect_uri"]
    assert b"synthetic-access" not in env["vault"].path.read_bytes()
    assert "synthetic-access" not in json.dumps(env["auth"].snapshot())
    with pytest.raises(ChatError, match="另一個"):
        Vault(env["vault"].directory, env["workspace"])
    original = json.loads(json.dumps(env["vault"].data))
    env["vault"].close()
    reopened = Vault(env["vault"].directory, env["workspace"])
    assert reopened.data == original
    reopened.close()


@pytest.mark.parametrize("bad", ["state", "nonce", "scope", "client", "denied", "expired"])
def test_oauth_rejects_invalid_grant_without_activating(env, bad):
    auth = env["auth"]
    auth.begin("http://127.0.0.1:12345")
    p = auth.pending
    env["config"]["nonce"] = p["nonce"]
    q = {"state": p["state"], "code": "fixture", "client_id": "oaiapp_fixture"}
    if bad == "state": q["state"] = "wrong"
    if bad == "nonce": env["config"]["nonce"] = "wrong"
    if bad == "scope": env["config"]["scopes"] = "openid profile email"
    if bad == "client": q.pop("client_id")
    if bad == "denied": q["error"] = "access_denied"
    if bad == "expired": p["until"] = 0
    with pytest.raises(ChatError): auth.callback(q)
    assert env["vault"].data["active"] is None
    assert not env["vault"].data["accounts"]


def test_reauthorization_identity_refresh_and_logout(env):
    login(env)
    auth = env["auth"]
    key = env["vault"].data["active"]
    auth.begin("http://127.0.0.1:22222", key)
    params = parse_qs(urlsplit(env["opened"][-1]).query)
    assert params["client_id"] == ["oaiapp_fixture"]
    assert "agent_name_hint" not in params and "id_token_hint" in params
    env["config"].update(nonce=auth.pending["nonce"], sub="wrong-user")
    with pytest.raises(ChatError, match="帳戶"):
        auth.callback({"state": auth.pending["state"], "code": "test"})
    env["config"]["sub"] = "fixture-user"
    saved = env["vault"].data["accounts"][key]
    saved["expires_at"] = 0
    assert auth.access(key) == "synthetic-access-only"
    refresh = next(r for r in reversed(env["calls"]) if r.url.path.endswith("/token"))
    assert parse_qs(refresh.content.decode())["grant_type"] == ["refresh_token"]
    host = env["vault"].data["host"]
    auth.logout()
    assert env["vault"].data["host"] == host
    assert env["vault"].data["accounts"][key]["client_id"] == "oaiapp_fixture"
    assert "refresh_token" not in env["vault"].data["accounts"][key]
    with pytest.raises(ChatError): auth.access(key)


@pytest.mark.parametrize("failure,reason", [
    (400, "未接受授權"), (401, "未接受授權"), (403, "拒絕存取"),
    (429, "限制請求"), (503, "暫時無法使用"),
    (httpx.ConnectError("SYNTHETIC_PRIVATE_PROVIDER_DETAIL"), "尚未取得服務回應"),
    (httpx.ReadTimeout("SYNTHETIC_PRIVATE_PROVIDER_DETAIL"), "連線逾時")],
    ids=["invalid-grant", "unauthorized", "forbidden", "rate", "service", "network", "timeout"])
def test_refresh_failure_explains_reason_without_retaining_model_readiness(env, failure, reason):
    login(env)
    c, auth, vault = env["chat"], env["auth"], env["vault"]
    c.catalog()
    account = vault.data["active"]
    record = vault.data["accounts"][account]
    identity = record["client_id"], record["subject"], vault.data["host"]
    record["expires_at"] = 0
    env["config"]["token_failure"] = failure
    with pytest.raises(ChatError, match=reason) as caught:
        c.catalog()
    assert "SYNTHETIC_PRIVATE_PROVIDER_DETAIL" not in str(caught.value)
    assert auth.snapshot()["notice"] == str(caught.value)
    assert not auth.snapshot()["accounts"][0]["signed_in"]
    assert c.models == [] and c.models_account is None
    assert vault.data["active"] == account
    assert (record["client_id"], record["subject"], vault.data["host"]) == identity
    assert not any(record.get(k) for k in ("access_token", "refresh_token", "id_token"))
    with pytest.raises(ChatError):
        c.submit({"chat": None, "question": "Do not send", "sources": [],
                  "model": "fixture-model", "preview": None})
    assert not any(r.url.path.endswith("/responses") for r in env["calls"])
    # Recovery explicitly repeats the official sign-in for the same registration.
    env["config"].pop("token_failure")
    auth.begin("http://127.0.0.1:12345", account)
    params = parse_qs(urlsplit(env["opened"][-1]).query)
    env["config"]["nonce"] = params["nonce"][0]
    auth.callback({"state": params["state"][0], "code": "fixture-code", "client_id": identity[0]})
    c.catalog()
    assert vault.data["active"] == account and auth.snapshot()["accounts"][0]["signed_in"]
    assert c.models_account == account


@pytest.mark.parametrize("failure,reason", [
    (401, "登入授權"), (403, "帳戶資格"), (429, "暫時受限"), (503, "暫時無法使用"),
    (httpx.ConnectError("SYNTHETIC_PRIVATE_PROVIDER_DETAIL"), "確認網路")],
    ids=["unauthorized", "forbidden", "rate", "service", "network"])
def test_model_catalog_failure_blocks_stale_model_and_allows_explicit_retry(env, failure, reason):
    login(env)
    c = env["chat"]
    c.catalog()
    env["config"]["model_failure"] = failure
    with pytest.raises(ChatError, match=reason) as caught:
        c.catalog()
    assert "SYNTHETIC_PRIVATE_PROVIDER_DETAIL" not in str(caught.value)
    assert c.models == [] and c.models_account is None
    assert not any(r.url.path.endswith("/responses") for r in env["calls"])
    env["config"].pop("model_failure")
    assert c.catalog()[0]["slug"] == "fixture-model"
    assert c.models_account == env["vault"].data["active"]


def test_unrecognized_catalog_is_not_reported_as_network_or_login_failure(env):
    login(env)
    env["config"]["malformed_models"] = True
    with pytest.raises(ChatError, match="回應格式無法驗證") as caught:
        env["chat"].catalog()
    assert "SYNTHETIC_PRIVATE_PROVIDER_DETAIL" not in str(caught.value)
    assert env["chat"].models == []


def test_conversation_followup_restart_sources_and_review_separation(env):
    login(env)
    first = send(env)
    assert first["turns"][0]["status"] == "complete"
    second = send(env, first["id"], "Explain that suggestion")
    assert "Prior answer retained" in second["turns"][1]["answer"]
    env["chat"] = Conversations(env["workspace"], env["vault"].directory, env["auth"])
    third = send(env, first["id"], "Continue after restart")
    assert len(third["turns"]) == 3
    expected = hashlib.sha256((env["workspace"] / "README.md").read_bytes()).hexdigest()
    assert all(t["sources"][0]["sha256"] == expected for t in third["turns"])
    assert not list(env["vault"].directory.glob("*.result.json"))
    assert "ACCEPTED" not in json.dumps(third)
    payload = json.loads(next(r for r in reversed(env["calls"]) if r.url.path.endswith("/responses")).content)
    assert set(payload) == {"model", "input", "instructions", "stream", "store"}
    assert payload["stream"] is True and payload["store"] is False
    assert len(payload["input"]) == 5


@pytest.mark.parametrize("events", [[], [{"type": "response.output_text.delta", "delta": "fake success"}],
    [{"type": "response.failed", "response": {"error": {"code": "subscription_sharing_usage_limit_exceeded"}}}],
    [{"type": "response.incomplete"}], [{"type": "response.completed", "response": {"id": "unknown", "status": "completed"}}]])
def test_stream_failure_never_becomes_answer(env, events):
    login(env)
    env["config"]["events"] = events
    result = send(env)
    assert result["turns"][0]["status"] == "failed"
    assert result["turns"][0]["answer"] is None
    assert result["turns"][0]["error"]


def test_missing_source_and_stale_preview_fail_before_model(env):
    login(env)
    c = env["chat"]
    c.catalog()
    with pytest.raises(ChatError):
        c.submit({"chat": None, "question": "test", "model": "fixture-model", "sources": ["readme"], "preview": {}})
    (env["workspace"] / "README.md").unlink()
    with pytest.raises(ChatError): send(env)
    assert not any(r.url.path.endswith("/responses") for r in env["calls"])
    assert not c.snapshot()["chats"]


def document_grant(e, chat_id, scope='excerpt', start=2, end=2):
    resources = e['chat'].resources
    item = next(d for d in resources.documents({'workspace': str(e['workspace'])})['documents'] if d['relative'] == 'README.md')
    body = {'workspace': str(e['workspace']), 'id': item['id'], 'version': item['version']}
    resources.preview(body)
    return resources.preview_source({**body, 'chat': chat_id, 'scope': scope,
                                     'start': start if scope == 'excerpt' else None,
                                     'end': end if scope == 'excerpt' else None})


@pytest.mark.parametrize('scope', ['name', 'excerpt'])
def test_document_handoff_exact_model_payload_single_send_and_historical_source(env, scope):
    login(env)
    conversation = send(env, selected=[])
    raw = '# Public document\nThe visible public code is ORCHID-47.\nUNSELECTED_PUBLIC_SENTINEL\n'
    (env['workspace'] / 'README.md').write_text(raw, encoding='utf-8')
    c = env['chat']; grant = document_grant(env, conversation['id'], scope)
    source = grant['source']
    expected = 'README.md' if scope == 'name' else raw.splitlines()[1]
    assert source['text'] == expected
    body = {'chat': conversation['id'], 'question': 'Discuss only the authorized source.',
            'sources': [source['key']], 'model': 'fixture-model', 'preview': {source['key']: source['sha256']}}
    result = c.submit(body); c.worker.join(5)
    saved = c.get(result['chat'])['turns'][-1]
    assert saved['status'] == 'complete' and saved['sources'] == [source]
    assert source['version'] == hashlib.sha256((env['workspace'] / 'README.md').read_bytes()).hexdigest()
    assert source['sha256'] == hashlib.sha256(expected.encode()).hexdigest()
    assert source['captured_at'] and source['relative'] == 'README.md'
    payload = json.loads(next(r for r in reversed(env['calls']) if r.url.path.endswith('/responses')).content)
    assert expected in payload['input'][-1]['content']
    assert 'UNSELECTED_PUBLIC_SENTINEL' not in json.dumps(payload)
    if scope == 'name':
        assert 'ORCHID-47' not in json.dumps(payload) and source['start_line'] is None
    else:
        assert source['start_line'] == source['end_line'] == 2
    before = len(env['calls'])
    with pytest.raises(ChatError): c.submit(body)
    assert len(env['calls']) == before
    (env['workspace'] / 'README.md').write_text('CURRENT_FILE_CHANGED\n', encoding='utf-8')
    env['chat'] = Conversations(env['workspace'], env['vault'].directory, env['auth'])
    assert env['chat'].get(result['chat'])['turns'][-1]['sources'] == [source]
    followup = send(env, result['chat'], 'Continue ordinary discussion.', selected=[])
    assert followup['turns'][-1]['status'] == 'complete' and followup['turns'][-1]['sources'] == []
    payload = json.loads(next(r for r in reversed(env['calls']) if r.url.path.endswith('/responses')).content)
    assert 'CURRENT_FILE_CHANGED' not in json.dumps(payload)
    assert 'ORCHID-47' not in json.dumps(payload)


@pytest.mark.parametrize('change', ['account', 'pending', 'signed-out', 'workspace', 'file', 'expiry', 'restart', 'chat', 'mixed', 'forged-preview'])
def test_document_handoff_invalid_scope_never_reaches_model(env, change, tmp_path):
    login(env)
    first = send(env, selected=[]); second = send(env, selected=[])
    c = env['chat']; grant = document_grant(env, first['id']); source = grant['source']
    body = {'chat': first['id'], 'question': 'Read the grant', 'sources': [source['key']],
            'model': 'fixture-model', 'preview': {source['key']: source['sha256']}}
    if change == 'account': c.auth.vault.data['active'] = 'foreign'
    if change == 'signed-out': c.auth.vault.data['active'] = None
    if change == 'pending': c.auth.pending = {'synthetic': True}
    if change == 'workspace': c.workspace = str(tmp_path / 'other')
    if change == 'file': (env['workspace'] / 'README.md').write_text('Changed', encoding='utf-8')
    if change == 'expiry': c.resources.handoff['expires'] = 0
    if change == 'restart':
        c = Conversations(env['workspace'], env['vault'].directory, env['auth'])
        c.models, c.models_account = env['chat'].models, env['chat'].models_account
    if change == 'chat': body['chat'] = second['id']
    if change == 'mixed': body['sources'].append('readme')
    if change == 'forged-preview': body['preview'][source['key']] = 'forged'
    before = len(env['calls'])
    with pytest.raises(ChatError): c.submit(body)
    assert len(env['calls']) == before
    assert c.worker is None or not c.worker.is_alive()


@pytest.mark.parametrize('start,end', [(True, 2), (1, False), (0, 1), (2, 1), (1, 100), (1.0, 2)])
def test_document_excerpt_must_be_exact_visible_lines(env, start, end):
    login(env)
    with pytest.raises(ChatError): document_grant(env, None, start=start, end=end)


def test_document_grant_revocation_and_stale_cancel_cannot_revoke_new_scope(env):
    login(env)
    old = document_grant(env, None, 'name'); new = document_grant(env, None)
    c = env['chat']; r = c.resources
    r.discard_source({'workspace': str(env['workspace']), 'key': old['source']['key']})
    assert r.source([new['source']['key']], None) == [new['source']]
    r.discard_source({'workspace': str(env['workspace']), 'key': new['source']['key']})
    with pytest.raises(ChatError): r.source([new['source']['key']], None)


def test_document_account_change_during_file_validation_revokes_grant(env, monkeypatch):
    import src.companion_core.resources as module
    login(env)
    grant = document_grant(env, None)
    original = module.read_text
    def changed(*args):
        result = original(*args)
        env['auth'].vault.data['active'] = 'foreign'
        return result
    monkeypatch.setattr(module, 'read_text', changed)
    with pytest.raises(ChatError): env['chat'].resources.source([grant['source']['key']], None)
    assert env['chat'].resources.handoff is None


@pytest.mark.parametrize('action', ['login', 'select', 'logout'])
def test_document_auth_actions_revoke_even_same_account_grant(env, action):
    login(env)
    c = env['chat']; grant = document_grant(env, None, 'name')
    account = env['auth'].vault.data['active']
    c.auth_action(action, {} if action == 'logout' else {'account': account}, 'http://127.0.0.1:12345')
    assert c.resources.handoff is None
    with pytest.raises(ChatError): c.resources.source([grant['source']['key']], None)


def test_document_excerpt_limits_apply_to_actual_bytes_and_lines(env):
    login(env)
    p = env['workspace'] / 'README.md'
    p.write_text(('公開文字' * 800) + '\nsecond\n', encoding='utf-8')
    with pytest.raises(ChatError): document_grant(env, None, start=1, end=1)
    p.write_text('\n'.join('Public line' for _ in range(41)), encoding='utf-8')
    with pytest.raises(ChatError): document_grant(env, None, start=1, end=41)
    with pytest.raises(ChatError): sources(env["workspace"], ["../private"])


def test_chat_http_guards_and_callback_no_reflection(env):
    surface = Surface(WorkNotConnected(), env["workspace"], ReviewStore(env["vault"].directory / "reviews"))
    server = make_server(surface, env["chat"])
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
        conn.request("POST", "/api/chat/logout", body="{}", headers={"Content-Type": "application/json"})
        response = conn.getresponse(); assert response.status == 403; response.read()
        conn.request("GET", "/auth/callback?state=private-value&code=private-code")
        response = conn.getresponse(); assert response.status == 400
        assert b"private" not in response.read()
        conn.close()
    finally:
        server.shutdown(); server.server_close(); thread.join()


@pytest.mark.parametrize("field,value", [("iss", "https://other.invalid"), ("aud", "wrong-client"),
    ("exp", 1), ("nonce", "wrong"), ("sub", ""), ("azp", "wrong-client")])
def test_signed_but_invalid_identity_rejected(env, field, value):
    claims = {"iss": ISSUER, "aud": "oaiapp_fixture", "sub": "test", "iat": int(time.time()),
              "exp": int(time.time()) + 60, "nonce": "expected"}
    claims[field] = value
    encoded = jwt.encode(claims, env["key"], algorithm="RS256", headers={"kid": "test"})
    with pytest.raises(ChatError): env["auth"]._claims(encoded, "oaiapp_fixture", "expected")


def test_bad_signature_and_replayed_callback_rejected(env):
    login(env)
    params = parse_qs(urlsplit(env["opened"][-1]).query)
    with pytest.raises(ChatError):
        env["auth"].callback({"state": params["state"][0], "code": "replay", "client_id": "oaiapp_fixture"})
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    encoded = jwt.encode({"iss": ISSUER, "aud": "oaiapp_fixture", "sub": "test", "iat": int(time.time()),
        "exp": int(time.time()) + 60, "nonce": "expected"}, other, algorithm="RS256", headers={"kid": "test"})
    with pytest.raises(ChatError): env["auth"]._claims(encoded, "oaiapp_fixture", "expected")


def test_source_bound_completion_and_no_tool_dispatch(env):
    login(env)
    for output in ([{"type": "function_call", "name": "shell", "arguments": "private"}],
                   [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Fabricated [S9:L999]"}]}]):
        env["config"]["events"] = [{"type": "response.created", "response": {"id": "fixture"}},
            {"type": "response.completed", "response": {"id": "fixture", "status": "completed", "output": output}}]
        result = send(env)
        assert result["turns"][0]["status"] == "failed"
        assert result["turns"][0]["answer"] is None


def text_stream(answer="Public prototype [S1:L1]", *, terminal_output=False):
    """Synthetic version of the observed SIWC event shape; no live payloads."""
    item = {"id": "msg_fixture", "type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": answer}]}
    identity = {"item_id": item["id"], "output_index": 0, "content_index": 0}
    return [
        {"type": "response.created", "response": {"id": "resp_fixture"}},
        {"type": "response.output_item.added", "output_index": 0,
         "item": {**item, "status": "in_progress", "content": []}},
        {"type": "response.output_text.delta", **identity, "delta": answer[:8]},
        {"type": "response.output_text.delta", **identity, "delta": answer[8:]},
        {"type": "response.output_text.done", **identity, "text": answer},
        {"type": "response.output_item.done", "output_index": 0, "item": item},
        {"type": "response.completed", "response": {"id": "resp_fixture", "status": "completed",
         "output": [item] if terminal_output else []}},
    ]


@pytest.mark.parametrize("terminal_output", [False, True])
def test_completed_stream_text_survives_empty_terminal_and_is_not_duplicated(env, terminal_output):
    login(env)
    env["config"]["events"] = text_stream(terminal_output=terminal_output)
    result = send(env)
    assert result["turns"][0]["status"] == "complete"
    assert result["turns"][0]["answer"] == "Public prototype [S1:L1]"
    assert result["turns"][0]["response_id"] == "resp_fixture"


@pytest.mark.parametrize("invalid", ["no_response_completed", "no_item_done", "delta_mismatch", "done_mismatch",
    "wrong_item", "wrong_response", "unfinished_item", "tool", "late_text", "failed_after_text"])
def test_stream_text_requires_matching_completed_identity_and_content(env, invalid):
    login(env)
    events = text_stream()
    if invalid == "no_response_completed": events.pop()
    elif invalid == "no_item_done": events.pop(5)
    elif invalid == "delta_mismatch": events[2]["delta"] = "inconsistent"
    elif invalid == "done_mismatch": events[4]["text"] = "inconsistent"
    elif invalid == "wrong_item": events[4]["item_id"] = "other-item"
    elif invalid == "wrong_response": events[-1]["response"]["id"] = "other-response"
    elif invalid == "unfinished_item": events[5]["item"]["status"] = "in_progress"
    elif invalid == "tool": events[5]["item"] = {"id": "msg_fixture", "type": "function_call"}
    elif invalid == "late_text": events.append(events[2])
    elif invalid == "failed_after_text": events[-1] = {"type": "response.failed", "response": {"error": {"code": "subscription_sharing_usage_unavailable"}}}
    env["config"]["events"] = events
    result = send(env)
    assert result["turns"][0]["status"] == "failed"
    assert result["turns"][0]["answer"] is None


@pytest.mark.parametrize("answer,reason", [("", "空"), ("x" * 50_001, "長度"),
    ("synthetic-access-only [S1:L1]", "憑證"), ("bad source [S9:L99]", "來源")],
    ids=["empty", "too-long", "credential", "invalid-source"])
def test_stream_output_checks_remain_closed_and_distinguish_reason(env, answer, reason):
    login(env)
    env["config"]["events"] = text_stream(answer)
    result = send(env)
    assert result["turns"][0]["status"] == "failed"
    assert result["turns"][0]["answer"] is None
    assert reason in result["turns"][0]["error"]
    assert "synthetic-access-only" not in result["turns"][0]["error"]


def test_failed_stream_does_not_enter_later_conversation_context(env):
    login(env)
    env["config"]["events"] = text_stream()
    first = send(env)
    env["config"]["events"] = text_stream()[:-1]
    second = send(env, first["id"], "Failed question must not enter history")
    assert second["turns"][1]["status"] == "failed"
    env["config"]["events"] = text_stream()
    third = send(env, first["id"], "Continue the completed answer")
    assert third["turns"][2]["status"] == "complete"
    request = next(r for r in reversed(env["calls"]) if r.url.path.endswith("/responses"))
    payload = json.loads(request.content)
    assert len(payload["input"]) == 3
    assert "Failed question must not enter history" not in json.dumps(payload)


def test_zero_sources_never_resolves_or_reads_workspace(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("ordinary chat must not inspect the filesystem")
    monkeypatch.setattr("src.companion_core.chat.Path", forbidden)
    assert sources("not-even-a-real-workspace", []) == []


def test_natural_chat_needs_no_sources_preview_or_citations(env):
    login(env)
    result = send(env, question="Hello, what do you think?", selected=[])
    turn = result["turns"][0]
    assert turn["status"] == "complete"
    assert turn["sources"] == [] and "[S" not in turn["answer"]
    payload = json.loads(next(r for r in reversed(env["calls"]) if r.url.path.endswith("/responses")).content)
    assert payload["input"] == [{"role": "user", "content": "Hello, what do you think?"}]
    assert "Public prototype" not in json.dumps(payload)


def test_sources_do_not_require_citations_for_general_opinion(env):
    login(env)
    env["config"]["events"] = text_stream("Synthetic opinion: I disagree with the proposed tradeoff.")
    turn = send(env)["turns"][0]
    assert turn["status"] == "complete" and len(turn["sources"]) == 1


@pytest.mark.parametrize("selected,answer", [([], "False [S1:L1]"),
    (["readme"], "False [S2:L1]"), (["readme"], "False [S1:L3]"),
    (["readme"], "False [S1:L0]"), (["readme"], "False [S1:Lunknown]"),
    (["readme"], "False [S1:L1-L2]")])
def test_optional_citations_still_require_current_source_and_exact_line(env, selected, answer):
    login(env)
    env["config"]["events"] = text_stream(answer)
    turn = send(env, selected=selected)["turns"][0]
    assert turn["status"] == "failed" and turn["answer"] is None
    assert "來源" in turn["error"]


@pytest.mark.parametrize("answer,reason", [("", "空"), ("x"*50_001, "長度"),
    ("synthetic-access-only", "憑證")], ids=["empty", "long", "credential"])
def test_plain_chat_keeps_output_safety_checks(env, answer, reason):
    login(env)
    env["config"]["events"] = text_stream(answer)
    turn = send(env, selected=[])["turns"][0]
    assert turn["status"] == "failed" and turn["answer"] is None
    assert reason in turn["error"]


def test_plain_chat_incomplete_stream_is_not_success(env):
    login(env)
    env["config"]["events"] = text_stream("Partial ordinary discussion")[:-1]
    turn = send(env, selected=[])["turns"][0]
    assert turn["status"] == "failed" and turn["answer"] is None


def test_old_sourced_turn_survives_plain_followup_and_restart(env):
    login(env)
    old = send(env)
    original = old["turns"][0]
    # The old snapshot is deliberately no longer the content of today's file.
    (env["workspace"] / "README.md").write_text("Changed today\n", encoding="utf-8")
    env["chat"] = Conversations(env["workspace"], env["vault"].directory, env["auth"])
    second = send(env, old["id"], "Continue our earlier discussion", selected=[])
    assert second["turns"][0] == original
    assert second["turns"][1]["status"] == "complete"
    payload = json.loads(next(r for r in reversed(env["calls"]) if r.url.path.endswith("/responses")).content)
    historical = payload["input"][0]["content"]
    assert original["created"] in historical and original["sources"][0]["sha256"] in historical
    assert "不是本輪資料" in historical and "Public prototype" not in historical
    assert payload["input"][-1]["content"] == "Continue our earlier discussion"
    assert "Changed today" not in json.dumps(payload)
    third = send(env, old["id"], "Now use today's project file")
    assert third["turns"][2]["sources"][0]["text"].splitlines() == ["Changed today"]
    assert third["turns"][2]["status"] == "complete"
    fourth = send(env, old["id"], "Back to ordinary conversation", selected=[])
    assert fourth["turns"][3]["status"] == "complete" and fourth["turns"][3]["sources"] == []


def test_nonempty_sources_still_require_current_preview_before_inference(env):
    login(env)
    c = env["chat"]
    c.catalog()
    old = sources(env["workspace"], ["readme"])
    (env["workspace"] / "README.md").write_text("Changed\n", encoding="utf-8")
    with pytest.raises(ChatError, match="預覽"):
        c.submit({"chat": None, "question": "test", "sources": ["readme"], "model": "fixture-model",
                  "preview": {r["key"]: r["sha256"] for r in old}})
    assert not any(r.url.path.endswith("/responses") for r in env["calls"])
    assert not c.snapshot()["chats"]
