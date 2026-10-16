"""Configuration contract tests; no live cluster or database required."""
import base64
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

spec = importlib.util.spec_from_file_location('sync', Path(__file__).parents[1] / 'sync-farm-config.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def secret(data, mode=None):
    return {'metadata': {'name': sync.SECRET, 'annotations': {sync.SOURCE: mode} if mode else {}},
            'data': {k: base64.b64encode(v.encode()).decode() for k, v in data.items()}}


class SyncTests(unittest.TestCase):
    config = {'POSTGRES_HOST': 'example.invalid', 'AI_DB_SSL': 'require'}
    shared = {'POSTGRES_USER': 'test_owner', 'POSTGRES_PASSWORD': 'test@:/pass'}

    def test_defaults_to_existing_credentials_and_gamefarm(self):
        data, mode = sync.connection_values(None, self.config, self.shared)
        url = urlsplit(data['FARM_DATABASE_URL'])
        self.assertEqual(url.path, '/gamefarm')
        self.assertEqual(url.hostname, self.config['POSTGRES_HOST'])
        self.assertEqual(unquote(url.password), self.shared['POSTGRES_PASSWORD'])
        self.assertEqual(mode, 'shared')
        self.assertEqual(data['FARM_REWARDS_ENABLED'], 'true')

    def test_retry_preserves_signing_secret_and_updates_shared_password(self):
        first, mode = sync.connection_values(None, self.config, self.shared)
        second, _ = sync.connection_values(secret(first, mode), self.config, dict(self.shared, POSTGRES_PASSWORD='rotated-test'))
        self.assertEqual(first['FARM_EVENT_SECRET'], second['FARM_EVENT_SECRET'])
        self.assertEqual(urlsplit(second['FARM_DATABASE_URL']).password, 'rotated-test')
        third, _ = sync.connection_values(secret(second, mode), self.config, dict(self.shared, POSTGRES_PASSWORD='rotated-test'))
        self.assertEqual(second, third)

    def test_explicit_github_secret_and_existing_connection_preserved(self):
        explicit = 'postgres://dedicated:test@db.invalid/gamefarm?sslmode=require'
        first, mode = sync.connection_values(None, self.config, self.shared, explicit)
        second, mode = sync.connection_values(secret(first, mode), self.config, self.shared)
        self.assertEqual(second, first)
        self.assertEqual(mode, 'explicit')

    def test_wrong_database_and_malformed_urls_fail_closed(self):
        for url in ['postgres://u:p@host/auth', 'https://u:p@host/gamefarm', 'postgres://u@host/gamefarm', 'postgres://u:p@[broken/gamefarm']:
            with self.assertRaises(RuntimeError):
                sync.connection_values(None, self.config, self.shared, url)

    def test_existing_short_signing_key_is_not_rotated(self):
        with self.assertRaises(RuntimeError):
            sync.connection_values(secret({'FARM_EVENT_SECRET': 'short'}), self.config, self.shared)

    def test_sync_only_writes_secret_and_outputs_digest(self):
        with patch.object(sync, 'read', side_effect=[None, {'data': self.config}, secret(self.shared)]), \
             patch.object(sync, 'kubectl') as kube, \
             patch.dict(sync.os.environ, {'FARM_DATABASE_URL': ''}), \
             patch('sys.stdout', new_callable=io.StringIO) as stdout:
            sync.main()
            kube.assert_called_once()
            self.assertEqual(kube.call_args.args, ('create', '-f', '-'))
            self.assertEqual(kube.call_args.kwargs['obj']['kind'], 'Secret')
            self.assertRegex(stdout.getvalue(), r'^[a-f0-9]{64}\n$')

    def test_kubectl_error_redacts_credentials(self):
        with patch.object(sync.subprocess, 'run') as run:
            run.return_value.returncode = 1
            run.return_value.stderr = 'password=private'
            with self.assertRaisesRegex(RuntimeError, '^Kubernetes request failed: create -f$'):
                sync.kubectl('create', '-f', '-', obj={'secret': 'private'})


if __name__ == '__main__':
    unittest.main()
