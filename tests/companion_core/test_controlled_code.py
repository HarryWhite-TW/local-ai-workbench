"""Host-boundary tests with synthetic source, never real model acceptance."""
import hashlib
from contextlib import ExitStack
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import tempfile
import unittest

from src.companion_core.chat import Conversations, now
from src.companion_core.controlled_code import AUTHORITY, BASE, TARGET, ControlledCode, ExistingSignIn, ExistingVault, locked_target
from src.companion_core.native_execution import DISABLED, NativeClient, observe_turn
from src.companion_core.domain import Failure
from src.companion_core.runtime import RuntimeFailure
from src.companion_core.siwc import ChatError, Vault

def make_engine(tmp_path):
    root, state = tmp_path/'candidate', tmp_path/'state'
    target = root/TARGET
    target.parent.mkdir(parents=True)
    target.write_bytes(b'const original = 1;\n')
    state.mkdir()
    auth = SimpleNamespace(lock=threading.RLock(), pending=None,
                           vault=SimpleNamespace(data={'active': 'owner'}))
    chat = Conversations(root, state, auth)
    with chat.connect() as db:
        db.execute('INSERT INTO chats VALUES (?,?,?,?,?)', ('chat', str(root.resolve()), 'owner', 'test', now()))
        db.execute('CREATE TABLE controlled_code (id TEXT PRIMARY KEY, chat TEXT NOT NULL, value TEXT NOT NULL)')
    result = object.__new__(ControlledCode)
    result.chat, result.root, result.head = chat, root, BASE
    result.worker, result.key = None, secrets.token_bytes(32)
    result.node = shutil.which('node')
    result.git = Mock(return_value=BASE.encode())
    result.runtime_source = {'root': 'synthetic-runtime', 'head': 'synthetic-wip'}
    result.check_repositories = Mock()  # Handle tests isolate filesystem behavior.
    return result


def preview(engine):
    return engine.respond('preview', {'chat': 'chat', 'question': 'Add a review summary copy button'})


def approval(job):
    return {'id': job['id'], 'token': job['token'], 'authority': AUTHORITY}


def response(job, replacement='const original = 2;\n'):
    return json.dumps({'target': TARGET, 'source_sha256': job['source']['sha256'], 'replacement': replacement})


class RepositoryIdentityTests(unittest.TestCase):
    """Real Git metadata; mocked initial snapshot is NOT Windows handle proof."""
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(__file__).resolve().parents[2]
        cls.temp = tempfile.TemporaryDirectory(prefix='eng01-git-')
        cls.root = Path(cls.temp.name).resolve() / 'candidate'
        subprocess.run(['git', '-C', str(cls.repo), 'worktree', 'add', '--detach', str(cls.root), BASE],
                       check=True, capture_output=True)
        cls.node = Path(cls.temp.name) / 'node.exe'
        cls.node.write_bytes(b'not executed')

    @classmethod
    def tearDownClass(cls):
        subprocess.run(['git', '-C', str(cls.repo), 'worktree', 'remove', str(cls.root)], check=True, capture_output=True)
        cls.temp.cleanup()

    def engine(self, root=None):
        with patch.object(ControlledCode, 'snapshot', return_value={}):
            return ControlledCode(MagicMock(), 'unused.exe', root=root or self.root, node=self.node)

    def test_saved_wip_runtime_can_use_mvp_worktree_and_trusted_asset(self):
        engine = self.engine()
        self.assertEqual(engine.head, BASE)
        self.assertNotEqual(engine.runtime_source['head'], BASE)
        self.assertEqual(engine.runtime_source['root'], str(self.repo))
        self.assertNotEqual(engine.runtime_source['git_dir'], engine.candidate_source['git_dir'])
        self.assertEqual(engine.served_asset, subprocess.check_output(['git', '-C', str(self.repo), 'show', BASE+':'+TARGET]))
        engine.check_repositories()

    def test_runtime_or_candidate_git_drift_is_rejected(self):
        for changed in (self.repo, self.root):
            for field in ('head', 'git_dir', 'common'):
                engine = self.engine()
                original = engine.repository
                def drift(root):
                    value = original(root)
                    if root == changed:
                        value[field] = 'changed'
                    return value
                with patch.object(engine, 'repository', side_effect=drift):
                    with self.assertRaises(ChatError): engine.snapshot()

    def test_runtime_nested_and_non_root_targets_are_rejected(self):
        for root in (self.repo, self.repo/'src', self.root/'src'):
            with self.subTest(root=root), self.assertRaises(ChatError): self.engine(root)

    def test_wip_target_head_is_rejected(self):
        original = ControlledCode.git
        def wrong_head(engine, *args, **kwargs):
            if args == ('rev-parse', 'HEAD') and not kwargs.get('root'):
                return engine.runtime_source['head'].encode()
            return original(engine, *args, **kwargs)
        with patch.object(ControlledCode, 'git', new=wrong_head):
            with self.assertRaises(ChatError): self.engine()

    def test_missing_explicit_target_is_rejected(self):
        with self.assertRaises(ChatError): ControlledCode(MagicMock(), 'unused.exe')


class PortableBoundaryTests(unittest.TestCase):
    """Synthetic source and approvals only; never invoke a model or host writer."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = make_engine(Path(self.temp.name))
        def snapshot():
            raw = (self.engine.root/TARGET).read_bytes()
            return {'target': TARGET, 'root': str(self.engine.root), 'head': BASE,
                    'sha256': hashlib.sha256(raw).hexdigest(), 'identity': ['synthetic'],
                    'text': raw.decode(), 'runtime': self.engine.runtime_source}
        self.engine.snapshot = snapshot

    def test_preview_readback_and_runtime_identity_are_bound_to_approval(self):
        engine = self.engine
        job = preview(engine)
        self.assertEqual(engine.respond('state', {'chat':'chat'})[0], job)
        stored = engine.get(job['id'])
        stored['source']['runtime']['head'] = 'tampered'
        engine.save(stored)
        with self.assertRaises(ChatError): engine.respond('confirm', approval(job))
        self.assertIsNone(engine.worker)

    def test_static_validator_rejects_invalid_output_without_writing(self):
        engine = self.engine
        job = preview(engine)
        before = (engine.root/TARGET).read_bytes()
        for answer in (response(job, 'const broken = ;'), response(job, before.decode()),
                       response(job).replace(TARGET, 'AGENTS.md')):
            with self.assertRaises(ChatError): engine.validate(answer, job)
            self.assertEqual((engine.root/TARGET).read_bytes(), before)
        engine.validate(response(job), job)
        self.assertEqual(job['tests']['exitCode'], 0)
        self.assertFalse(job['tests']['generated_code_executed'])
        self.assertEqual((engine.root/TARGET).read_bytes(), before)

    def test_windows_writer_fails_closed_on_other_platforms(self):
        if os.name == 'nt': self.skipTest('Non-Windows rejection only')
        with self.assertRaises(ChatError):
            with locked_target(self.engine.root): self.fail('must not open')

    def test_tool_event_rejected(self):
        rpc = SimpleNamespace(notification=lambda _: {'method':'item/started','params':{
            'threadId':'thread','turnId':'turn','item':{'id':'tool','type':'commandExecution'}}})
        with self.assertRaises(RuntimeFailure):
            observe_turn(rpc,'thread','turn',threading.Event(),lambda **_:None)


class DailyEntrypointTests(unittest.TestCase):
    def test_controlled_flags_must_be_paired_before_any_vault_access(self):
        from src.companion_core.daily import main
        for flags in (['--controlled-engineering'], ['--controlled-worktree', 'unused']):
            with patch('sys.argv', ['daily', '--workspace', '.', *flags]), patch('sys.stderr'), \
                    patch('src.companion_core.controlled_code.ExistingVault') as vault:
                with self.assertRaises(SystemExit) as error: main()
                self.assertEqual(error.exception.code, 2)
                vault.assert_not_called()

    def test_daily_passes_explicit_target_separately_from_chat_workspace(self):
        from src.companion_core import daily
        repo = Path(__file__).resolve().parents[2]
        with ExitStack() as stack:
            stack.enter_context(patch('sys.argv', ['daily', '--workspace', str(repo), '--data-dir', 'unused',
                '--controlled-engineering', '--controlled-worktree', 'explicit-candidate', '--no-browser']))
            for name in ('ExistingVault', 'ExistingSignIn'):
                stack.enter_context(patch('src.companion_core.controlled_code.' + name))
            controlled = stack.enter_context(patch('src.companion_core.controlled_code.ControlledCode'))
            mocks = {name: stack.enter_context(patch.object(daily, name)) for name in
                     ('Conversations', 'NativeWork', 'Surface', 'ReviewStore', 'DocumentOrganizer', 'NativeCodex', 'make_server')}
            chat = mocks['Conversations'].return_value
            chat.worker = None
            mocks['Surface'].return_value.worker = None
            with patch('builtins.print'):
                self.assertEqual(daily.main(), 0)
            self.assertEqual(mocks['Conversations'].call_args.args[0], repo)
            self.assertEqual(controlled.call_args.args[0], chat)
            self.assertEqual(controlled.call_args.kwargs, {'root': 'explicit-candidate'})



@unittest.skipUnless(os.name == 'nt', 'Windows handle isolation contract')
class ControlledCodeTests(unittest.TestCase):
    def setUp(self):
        scratch=Path(__file__).absolute().parents[2]/'.eng01-safety-probe'
        scratch.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='host-tests-',dir=scratch)
        assert Path(self.temp.name).resolve().is_relative_to(scratch.resolve())
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.number=0

    def fresh_engine(self):
        self.number+=1
        base=self.base/str(self.number)
        base.mkdir()
        return make_engine(base)

    def test_preview_captures_exact_source_without_writing(self):
        engine=self.fresh_engine()
        before = (engine.root/TARGET).read_bytes()
        job = preview(engine)
        assert job['source']['sha256'] == hashlib.sha256(before).hexdigest()
        assert job['source']['text'].encode() == before
        assert (engine.root/TARGET).read_bytes() == before
        assert engine.chat.get('chat')['turns'][0]['id'] == job['turn']


    def test_old_approvals_cannot_write(self):
        for authority in ['READ_ONLY', 'ISOLATED_SAMPLE_WRITE', '']:
            with self.subTest(authority=authority):
                engine=self.fresh_engine()
                body = approval(preview(engine)); body['authority'] = authority
                with self.assertRaises(ChatError): engine.respond('confirm', body)
                assert engine.worker is None

    def test_arbitrary_http_target_is_rejected(self):
        engine=self.fresh_engine()
        with self.assertRaises(ChatError):
            engine.respond('preview', {'chat':'chat', 'question':'change', 'target':'../AGENTS.md'})


    def test_approval_binds_all_authority_dimensions(self):
        for change in ['content', 'identity', 'head', 'goal', 'expiry', 'account', 'token']:
            with self.subTest(change=change):
                engine=self.fresh_engine()
                job = preview(engine); body = approval(job)
                if change == 'content': (engine.root/TARGET).write_text('changed')
                elif change == 'identity':
                    (engine.root/TARGET).unlink(); (engine.root/TARGET).write_bytes(job['source']['text'].encode())
                elif change == 'head': engine.git.return_value=b'other'
                elif change == 'account': engine.chat.auth.vault.data['active']='other'
                elif change == 'token': body['token']='invalid'
                else:
                    stored=engine.get(job['id'])
                    stored['goal' if change=='goal' else 'expires']='different' if change=='goal' else 0
                    engine.save(stored)
                with self.assertRaises(ChatError): engine.respond('confirm',body)
                assert engine.worker is None

    def test_approval_is_consumed_and_state_readback_has_no_side_effect(self):
        engine=self.fresh_engine()
        job=preview(engine)
        engine.run=Mock()
        engine.respond('confirm',approval(job)); engine.worker.join()
        with self.assertRaises(ChatError): engine.respond('confirm',approval(job))
        one=engine.respond('state',{'chat':'chat'}); two=engine.respond('state',{'chat':'chat'})
        assert one==two and one[0]['state']=='RUNNING'
        engine.run.assert_called_once()


    def test_invalid_model_result_never_writes(self):
        for bad in ['wrong_path', 'wrong_hash', 'duplicate', 'syntax', 'same']:
            with self.subTest(bad=bad):
                engine=self.fresh_engine()
                job=preview(engine); before=(engine.root/TARGET).read_bytes(); value=json.loads(response(job))
                if bad=='wrong_path': value['target']='AGENTS.md'
                elif bad=='wrong_hash': value['source_sha256']='0'*64
                elif bad=='syntax': value['replacement']='const broken = ;'
                elif bad=='same': value['replacement']=before.decode()
                answer=json.dumps(value)
                if bad=='duplicate': answer=answer[:-1]+',"target":"'+TARGET+'"}'
                with self.assertRaises((ChatError,ValueError)): engine.validate(answer,job)
                assert (engine.root/TARGET).read_bytes()==before

    def test_host_static_validation_and_apply_only_touch_fixed_file(self):
        engine=self.fresh_engine()
        job=preview(engine); stored=engine.get(job['id'])
        other=engine.root/'unapproved.txt';other.write_bytes(b'untouched')
        engine.validate(response(job),stored)
        assert stored['tests']['exitCode']==0
        assert stored['tests']['generated_code_executed'] is False
        engine.apply(stored)
        after=(engine.root/TARGET).read_bytes()
        assert after==b'const original = 2;\n' and other.read_bytes()==b'untouched'
        assert stored['diff'] and stored['state']=='COMPLETED'
        assert engine.respond('state',{'chat':'chat'})[0]['final_sha256']==hashlib.sha256(after).hexdigest()
        assert (engine.root/TARGET).read_bytes()==after


    def test_source_race_after_model_validation_cannot_apply(self):
        engine=self.fresh_engine()
        job=preview(engine);stored=engine.get(job['id']);engine.validate(response(job),stored)
        (engine.root/TARGET).write_bytes(b'new source')
        with self.assertRaises(ChatError):engine.apply(stored)
        assert (engine.root/TARGET).read_bytes()==b'new source'


    def test_target_handle_excludes_concurrent_writes_and_deletion(self):
        engine=self.fresh_engine()
        with locked_target(engine.root,write=True):
            with self.assertRaises(PermissionError): (engine.root/TARGET).write_bytes(b'forbidden')
            with self.assertRaises(PermissionError): (engine.root/TARGET).unlink()
        assert (engine.root/TARGET).read_bytes()==b'const original = 1;\n'


    def test_hardlink_target_is_rejected(self):
        engine=self.fresh_engine()
        os.link(engine.root/TARGET,engine.root/'alias.js')
        with self.assertRaises(ChatError):engine.snapshot()


    def test_junction_ancestor_is_rejected(self):
        engine=self.fresh_engine(); tmp_path=self.base
        parent=(engine.root/TARGET).parent
        moved=tmp_path/'moved';parent.rename(moved)
        result=subprocess.run(['cmd','/c','mklink','/J',str(parent),str(moved)],capture_output=True)
        assert result.returncode==0
        try:
            with self.assertRaises(ChatError):engine.snapshot()
            assert (moved/'engineering-pilot.js').read_bytes()==b'const original = 1;\n'
        finally:
            os.rmdir(parent)  # Remove only the junction itself; never recurse into it.


    def test_unexpected_model_tool_event_is_rejected(self):
        rpc=SimpleNamespace(notification=lambda _: {'method':'item/started','params':{
            'threadId':'thread','turnId':'turn','item':{'id':'tool','type':'commandExecution'}}})
        with self.assertRaises(RuntimeFailure) as error:
            observe_turn(rpc,'thread','turn',threading.Event(),lambda **_:None)
        assert error.exception.reason==Failure.POLICY


    def test_default_native_client_keeps_existing_settings_unchanged(self):
        assert NativeClient('empty','existing.exe').settings==()
        assert {'shell_tool','apply_patch_freeform','unified_exec','code_mode','browser_use'}.issubset(DISABLED)

class ManualSignInTests(unittest.TestCase):
    """Synthetic identities only; never open or inspect a real authorization URL."""
    def setUp(self):
        self.vault = object.__new__(ExistingVault)
        self.vault._manual_login_save = False
        self.vault.data = {'host':'synthetic-host','active':'owner','accounts':{
            'owner':{'client_id':'oaiapp_synthetic','subject':'synthetic-subject',
                     'label':'Synthetic account','expires_at':0}}}
        self.auth = ExistingSignIn(self.vault)
        self.addCleanup(self.auth.http.close)

    def test_expired_access_never_refreshes_or_saves(self):
        self.auth._json = Mock(side_effect=AssertionError('No automatic refresh'))
        with patch.object(Vault,'save') as save:
            with self.assertRaises(ChatError): self.auth.access('owner')
            save.assert_not_called()
        self.auth._json.assert_not_called()
        self.assertIn('Continue with ChatGPT',self.auth.notice)
        self.assertIn('owner',self.vault.data['accounts'])

    def test_explicit_login_opens_default_browser_and_waits_without_save(self):
        attempts=[]
        def opened(_):
            attempts.append(True)  # Discard URL without inspecting or retaining it.
            return True
        with patch('src.companion_core.siwc.webbrowser.open',new=opened),patch.object(Vault,'save') as save:
            self.auth.begin('http://127.0.0.1:56144','owner')
            self.assertEqual(len(attempts),1)
            self.assertIsNotNone(self.auth.pending)
            save.assert_not_called()
        self.assertIn('官方登入頁面',self.auth.notice)
        self.assertFalse(self.vault._manual_login_save)

    def test_browser_failure_is_explicit_and_not_left_pending(self):
        with patch('src.companion_core.siwc.webbrowser.open',new=lambda _:False):
            with self.assertRaises(ChatError):self.auth.begin('http://127.0.0.1:56144','owner')
        self.assertIsNone(self.auth.pending)
        self.assertIn('無法開啟系統瀏覽器',self.auth.notice)

    def test_only_valid_user_callback_can_save(self):
        with patch('src.companion_core.siwc.webbrowser.open',new=lambda _:True):
            self.auth.begin('http://127.0.0.1:56144','owner')
        self.auth._json=Mock(return_value={})
        self.auth._record=Mock(return_value={'client_id':'oaiapp_synthetic','subject':'synthetic-subject','email':'synthetic@example.invalid'})
        with patch.object(Vault,'save') as save:
            self.auth.callback({'state':self.auth.pending['state'],'code':'synthetic-code'})
            save.assert_called_once()
        self.assertIsNone(self.auth.pending)
        self.assertFalse(self.vault._manual_login_save)
        with self.assertRaises(ChatError):self.vault.save()

    def test_invalid_or_failed_callback_cannot_save_or_leave_permission_open(self):
        with patch.object(Vault,'save') as save:
            with self.assertRaises(ChatError):self.auth.callback({})
            save.assert_not_called()
        self.assertFalse(self.vault._manual_login_save)
        with self.assertRaises(ChatError):self.vault.save()

    def test_logout_and_account_switch_remain_blocked(self):
        with patch.object(Vault,'save') as save:
            with self.assertRaises(ChatError):self.auth.select('owner')
            with self.assertRaises(ChatError):self.auth.logout()
            save.assert_not_called()
        self.assertEqual(self.vault.data['active'],'owner')


if __name__ == '__main__':
    unittest.main()
