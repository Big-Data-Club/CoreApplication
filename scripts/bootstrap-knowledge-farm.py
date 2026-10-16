#!/usr/bin/env python3
"""Idempotent K3s/Neon bootstrap. Secrets remain in memory and Kubernetes.

Run under the shared deployment operation lock. No database traffic from CI:
all SQL runs in a short-lived Kubernetes Job using the existing Auth DB endpoint.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from urllib.parse import quote, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SECRET = 'bdc-farm-secrets'


def kubectl(*args, obj=None):
    result = subprocess.run(
        ['kubectl', '-n', os.environ.get('DEPLOY_NAMESPACE', 'default'), *args],
        input=json.dumps(obj) if obj is not None else None,
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        # kubectl may echo rejected Secret objects; never relay stderr.
        raise RuntimeError('Kubernetes request failed: ' + ' '.join(args[:2]))
    return result.stdout


def read(kind, name):
    raw = kubectl('get', kind, name, '--ignore-not-found', '-o', 'json')
    return json.loads(raw) if raw.strip() else None


def decode(obj):
    return {key: base64.b64decode(value).decode() for key, value in obj.get('data', {}).items()}


def direct_host(host):
    if host.endswith('.neon.tech'):
        first, rest = host.split('.', 1)
        return first.removesuffix('-pooler') + '.' + rest
    return host


def secret_values(existing, host, port, sslmode):
    data = decode(existing) if existing else {}
    url = data.get('FARM_DATABASE_URL')
    if url:
        parsed = urlsplit(url)
        if (parsed.scheme not in ('postgres', 'postgresql') or parsed.path != '/gamefarm'
                or direct_host(parsed.hostname or '') != direct_host(host)
                or (parsed.port or 5432) != int(port)):
            raise RuntimeError('Existing FARM_DATABASE_URL must target gamefarm on the current Auth host; migrate explicitly before retrying')
        user, password = unquote(parsed.username or ''), unquote(parsed.password or '')
        if not user or not password:
            raise RuntimeError('Existing farm connection requires a username and password')
    else:
        user, password = 'gamefarm_app', secrets.token_urlsafe(36)
        data['FARM_DATABASE_URL'] = f'postgresql://{quote(user, safe="")}:{quote(password, safe="")}@{host}:{port}/gamefarm?sslmode={sslmode}'
    data.setdefault('FARM_EVENT_SECRET', secrets.token_urlsafe(48))
    if len(data['FARM_EVENT_SECRET'].encode()) < 32:
        raise RuntimeError('Existing FARM_EVENT_SECRET is too short; coordinated secret rotation is required')
    data.update(FARM_DB_USER=user, FARM_DB_PASSWORD=password)
    data.setdefault('FARM_REWARDS_ENABLED', 'false')
    return data


def save_secret(existing, data):
    obj = {'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': SECRET},
           'type': 'Opaque', 'data': {k: base64.b64encode(v.encode()).decode() for k, v in data.items()}}
    if existing:
        obj['metadata'] = existing['metadata']
    kubectl('replace' if existing else 'create', '-f', '-', obj=obj)


def migration_sql(paths):
    # A committed migration's checksum is immutable. SQL + ledger are atomic.
    sql = ['BEGIN;', "SET LOCAL lock_timeout = '30s';", "SET LOCAL statement_timeout = '120s';",
           'SELECT pg_advisory_xact_lock(734620118);',
           'CREATE TABLE IF NOT EXISTS farm_deploy_migrations (version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());']
    for path in paths:
        version = path.name
        body = path.read_text()
        checksum = hashlib.sha256(body.encode()).hexdigest()
        sql += [f"SELECT EXISTS(SELECT FROM farm_deploy_migrations WHERE version = '{version}') AS applied \\gset",
                '\\if :applied',
                f"DO $check$ BEGIN IF NOT EXISTS(SELECT FROM farm_deploy_migrations WHERE version = '{version}' AND checksum = '{checksum}') THEN RAISE EXCEPTION 'Migration checksum mismatch'; END IF; END $check$;",
                '\\else', body,
                f"INSERT INTO farm_deploy_migrations(version, checksum) VALUES ('{version}', '{checksum}');",
                '\\endif']
    return '\n'.join(sql + ['COMMIT;'])


def main():
    config = read('configmap', 'bdc-config')
    if not config:
        raise RuntimeError('bdc-config is required')
    host = config['data']['POSTGRES_HOST']
    port = '5432'  # Matches the Auth datasource contract.
    sslmode = config['data'].get('AI_DB_SSL', 'require')
    existing = read('secret', SECRET)
    data = secret_values(existing, host, port, sslmode)
    # Persist generated credentials before SQL so interruption/retry never rotates them.
    save_secret(existing, data)
    name = 'farm-bootstrap-' + secrets.token_hex(5)
    source = ROOT / 'scripts/farm-bootstrap'
    files = {p.name: p.read_text() for p in source.iterdir() if p.suffix in ('.sql', '.sh')}
    files['auth.sql'] = migration_sql([ROOT / 'auth-and-management-service/migrations/V20261017__farm_score_receipts.sql'])
    files['farm.sql'] = migration_sql(sorted((ROOT / 'farm-service/migrations').glob('V*.sql')))
    cm = {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': name}, 'data': files}
    env = [{'name': key, 'value': value} for key, value in {
        'PGHOST': direct_host(host), 'PGPORT': port, 'PGSSLMODE': sslmode, 'PGCONNECT_TIMEOUT': '15',
    }.items()]
    for key, secret, field in [('PGDATABASE', 'bdc-secrets', 'POSTGRES_DB'),
                               ('PGUSER', 'bdc-secrets', 'POSTGRES_USER'),
                               ('PGPASSWORD', 'bdc-secrets', 'POSTGRES_PASSWORD'),
                               ('FARM_DB_USER', SECRET, 'FARM_DB_USER'),
                               ('FARM_DB_PASSWORD', SECRET, 'FARM_DB_PASSWORD')]:
        env.append({'name': key, 'valueFrom': {'secretKeyRef': {'name': secret, 'key': field}}})
    job = {'apiVersion': 'batch/v1', 'kind': 'Job', 'metadata': {'name': name}, 'spec': {
        'backoffLimit': 0, 'activeDeadlineSeconds': 240, 'ttlSecondsAfterFinished': 3600,
        'template': {'spec': {'restartPolicy': 'Never', 'automountServiceAccountToken': False,
            'containers': [{'name': 'migrate', 'image': 'postgres:16-alpine',
                'command': ['sh', '/migrations/run.sh'], 'env': env,
                'securityContext': {'runAsUser': 1000, 'runAsNonRoot': True, 'allowPrivilegeEscalation': False,
                                    'capabilities': {'drop': ['ALL']}},
                'resources': {'requests': {'cpu': '50m', 'memory': '32Mi'}, 'limits': {'cpu': '500m', 'memory': '128Mi'}},
                'volumeMounts': [{'name': 'sql', 'mountPath': '/migrations', 'readOnly': True}]}],
            'volumes': [{'name': 'sql', 'configMap': {'name': name}}]}}}}
    kubectl('create', '-f', '-', obj=cm)
    try:
        kubectl('create', '-f', '-', obj=job)
        kubectl('wait', '--for=condition=complete', 'job/' + name, '--timeout=250s')
    except RuntimeError:
        print(f'Bootstrap failed. Safe stage diagnostics: kubectl logs -n {os.environ.get("DEPLOY_NAMESPACE", "default")} job/{name}', file=sys.stderr)
        raise
    else:
        kubectl('delete', 'job', name, '--ignore-not-found')
        kubectl('delete', 'configmap', name, '--ignore-not-found')
    # Enable only after both schemas exist. Preserve all pre-existing keys.
    data['FARM_REWARDS_ENABLED'] = 'true'
    save_secret(read('secret', SECRET), data)
    print('gamefarm database, migrations and reward secret ready')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # No traceback/local variables/connection strings in CI logs.
        print(str(exc) if isinstance(exc, RuntimeError) else 'Farm bootstrap failed; check required configuration', file=sys.stderr)
        raise SystemExit(1)
