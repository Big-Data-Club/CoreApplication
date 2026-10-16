"""Offline deployment contract tests; no cluster or credentials required."""
import base64
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('bootstrap', Path(__file__).parents[1] / 'bootstrap-knowledge-farm.py')
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


def existing(data):
    return {'data': {key: base64.b64encode(value.encode()).decode() for key, value in data.items()}}


class BootstrapTests(unittest.TestCase):
    def test_retry_preserves_credentials_and_signature_key(self):
        first = bootstrap.secret_values(None, 'example-pooler.region.neon.tech', '5432', 'require')
        second = bootstrap.secret_values(existing(first), 'example-pooler.region.neon.tech', '5432', 'require')
        self.assertEqual(first, second)
        self.assertIn('/gamefarm?sslmode=require', first['FARM_DATABASE_URL'])
        self.assertEqual(first['FARM_REWARDS_ENABLED'], 'false')
        self.assertNotEqual(first['FARM_DB_PASSWORD'], first['FARM_EVENT_SECRET'])

    def test_existing_wrong_database_or_host_fails_closed(self):
        for url in ['postgres://u:p@host/oldfarm', 'postgres://u:p@other/gamefarm']:
            with self.assertRaises(RuntimeError):
                bootstrap.secret_values(existing({'FARM_DATABASE_URL': url}), 'host', '5432', 'require')

    def test_encoded_credentials_and_unknown_keys_preserved(self):
        data = bootstrap.secret_values(existing({'FARM_DATABASE_URL': 'postgres://farm:p%40%3A%2F@host/gamefarm',
                                                  'FARM_EVENT_SECRET': 'x' * 32, 'extra': 'keep'}), 'host', '5432', 'require')
        self.assertEqual(data['FARM_DB_PASSWORD'], 'p@:/')
        self.assertEqual(data['extra'], 'keep')

    def test_direct_neon_host_only(self):
        self.assertEqual(bootstrap.direct_host('ep-test-pooler.region.neon.tech'), 'ep-test.region.neon.tech')
        self.assertEqual(bootstrap.direct_host('postgres-pooler.internal'), 'postgres-pooler.internal')

    def test_migration_ledger_checksum_and_transaction(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'V001__example.sql'
            path.write_text('CREATE TABLE example (id INT);')
            sql = bootstrap.migration_sql([path])
            self.assertTrue(sql.startswith('BEGIN;'))
            self.assertTrue(sql.endswith('COMMIT;'))
            self.assertIn('Migration checksum mismatch', sql)
            self.assertIn('pg_advisory_xact_lock', sql)
            self.assertIn('\\if :applied', sql)

    def test_failed_job_never_enables_rewards(self):
        config = {'data': {'POSTGRES_HOST': 'test-host', 'AI_DB_SSL': 'require'}}
        with patch.object(bootstrap, 'read', side_effect=[config, None]), \
             patch.object(bootstrap, 'save_secret') as save, \
             patch.object(bootstrap, 'kubectl') as kube:
            def execute(*args, **kwargs):
                if args[0] == 'wait':
                    raise RuntimeError('Job failed')
                return ''
            kube.side_effect = execute
            with self.assertRaises(RuntimeError):
                bootstrap.main()
            self.assertEqual(save.call_count, 1)
            self.assertEqual(save.call_args.args[1]['FARM_REWARDS_ENABLED'], 'false')

    def test_kubectl_error_never_exposes_secret(self):
        with patch.object(bootstrap.subprocess, 'run') as run:
            run.return_value.returncode = 1
            run.return_value.stderr = 'password=private'
            with self.assertRaisesRegex(RuntimeError, '^Kubernetes request failed: create -f$'):
                bootstrap.kubectl('create', '-f', '-', obj={'secret': 'private'})


if __name__ == '__main__':
    unittest.main()
