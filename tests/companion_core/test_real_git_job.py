from pathlib import Path
import json
import shutil
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src.companion_core.chat import Conversations
from src.companion_core.real_git_job import AUTHORITY, RealGitJob
from src.companion_core.siwc import ChatError


class SelectableGitContract(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        workspace = root / 'candidate'
        workspace.mkdir()
        state = root / 'real-git-job' / 'state'
        state.mkdir(parents=True)
        self.auth = SimpleNamespace(lock=threading.RLock(), pending=None,
                                    vault=SimpleNamespace(data={'active': 'owner'}))
        self.chat = Conversations(workspace, state, self.auth)
        self.adapter = RealGitJob(self.chat, 'unused.exe')
        origin = Path(__file__).resolve().parents[3] / 'real-git-job' / 'projects'
        self.projects = []
        for name, target in [('reverb-core', 'src/elysia_core/cli.py'), ('sampleproject', 'src/sample/simple.py')]:
            shutil.copytree(origin/name, self.adapter.home/'projects'/name)
            project = self.adapter.respond('register', dict(name=name, folder=name, nonSensitive=True))
            self.projects.append((project, target))

    def choose(self, n):
        project, _ = self.projects[n]
        self.adapter.respond('select', {'project': project['id']})
        return project

    def preview(self, n):
        project, target = self.projects[n]
        origin = self.adapter.respond('preview', dict(chat=None, project=project['id'], goal='fixture only',
                                                       targets=[target], test=''))['chat']
        [card] = self.adapter.respond('state', dict(chat=origin))
        return card, dict(id=card['id'], chat=origin, project=project['id'], token=card['token'], authority=AUTHORITY)

    def test_drift_rejects_confirm_and_preserves_git_identity(self):
        project = self.choose(0)
        card, approval = self.preview(0)
        candidate = Path(project['root'])
        (candidate/'drift.txt').write_text('untracked')
        [current] = self.adapter.respond('state', dict(chat=approval['chat']))
        self.assertEqual(current['current']['head'], card['before']['head'])
        self.assertNotEqual(current['current']['sha256'], card['before']['sha256'])
        with patch('src.companion_core.real_git_job.Thread') as worker:
            with self.assertRaises(ChatError):
                self.adapter.respond('confirm', approval)
            worker.assert_not_called()

    def test_switch_and_replacement_revoke_old_approval(self):
        self.choose(0)
        _, approval = self.preview(0)
        _, new = self.preview(0)
        self.choose(1)
        self.choose(0)
        with patch('src.companion_core.real_git_job.Thread') as worker:
            for item in [approval, new]:
                with self.assertRaises(ChatError):
                    self.adapter.respond('confirm', item)
            worker.assert_not_called()

    def test_owner_scope_restart_and_multiple_jobs(self):
        self.choose(0)
        first, approval = self.preview(0)
        with patch('src.companion_core.real_git_job.Thread') as worker:
            self.adapter.respond('confirm', approval)
            self.choose(1)
            second, other = self.preview(1)
            with self.assertRaises(ChatError):
                self.adapter.respond('confirm', other)
            reopened = RealGitJob(self.chat, 'unused.exe')
            with self.assertRaises(ChatError):
                reopened.respond('continue', dict(chat=None, project=other['project'], id=first['id']))
            reopened.respond('confirm', other)
            reopened = RealGitJob(self.chat, 'unused.exe')
            history = reopened.respond('catalog', {})['jobs']
            self.assertEqual({row['id'] for row in history}, {first['id'], second['id']})
            chat = reopened.respond('continue', dict(chat=None, project=other['project'], id=second['id']))['chat']
            [card] = reopened.respond('state', dict(chat=chat))
            self.assertNotEqual(chat, other['chat'])
            self.assertEqual((card['id'],card['state']), (second['id'],'UNKNOWN'))
            self.assertNotIn('token', card)
            self.auth.vault.data['active'] = 'other-owner'
            self.assertEqual(reopened.respond('catalog', {})['jobs'], [])
            with self.assertRaises(ChatError):
                reopened.respond('state', dict(chat=chat))
            self.assertEqual(worker.call_count, 2)

    def test_host_rejects_unapproved_output_and_test_overlap(self):
        project = self.choose(1)
        _, target = self.projects[1]
        with self.assertRaises(ChatError):
            self.adapter.respond('preview', dict(chat=None, project=project['id'], goal='bad test',
                                                targets=[target], test=target))
        _, approval = self.preview(1)
        with self.chat.connect() as db:
            job = json.loads(db.execute('SELECT data FROM git_jobs WHERE id=?',(approval['id'],)).fetchone()[0])
        scratch = self.adapter.execution_root(job)
        (scratch/target).parent.mkdir(parents=True)
        (scratch/target).write_text('# known deterministic edit\n')
        (scratch/'unapproved.py').write_text('raise RuntimeError')
        original = self.adapter.snapshot(Path(project['root']))
        with self.assertRaises(ChatError):
            self.adapter.apply(job, scratch)
        self.assertEqual(self.adapter.snapshot(Path(project['root'])), original)


if __name__ == '__main__':
    unittest.main()
