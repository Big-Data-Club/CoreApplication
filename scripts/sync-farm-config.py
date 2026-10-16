#!/usr/bin/env python3
"""Sync an existing gamefarm connection into Kubernetes; no SQL/provisioning."""
import base64
import hashlib
import json
import os
import secrets
import subprocess
import sys
from urllib.parse import quote, urlsplit

SECRET = 'bdc-farm-secrets'
SOURCE = 'bdc.io/farm-connection-source'


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


def connection_values(existing, config, shared, override=''):
    data = decode(existing) if existing else {}
    mode = (existing or {}).get('metadata', {}).get('annotations', {}).get(SOURCE)
    if override:
        data['FARM_DATABASE_URL'] = override
        mode = 'explicit'
    elif mode == 'shared' or not data.get('FARM_DATABASE_URL'):
        host = config['POSTGRES_HOST']
        user, password = shared['POSTGRES_USER'], shared['POSTGRES_PASSWORD']
        if not user or not password:
            raise RuntimeError('Existing PostgreSQL credentials are required')
        sslmode = config.get('AI_DB_SSL', 'require')
        data['FARM_DATABASE_URL'] = (
            f'postgresql://{quote(user, safe="")}:{quote(password, safe="")}@{host}:5432/gamefarm?sslmode={sslmode}'
        )
        mode = 'shared'
    else:
        # Preserve connections configured previously or using a dedicated DB role.
        mode = 'explicit'
    try:
        url = urlsplit(data['FARM_DATABASE_URL'])
        valid = (url.scheme in ('postgres', 'postgresql') and url.path == '/gamefarm'
                 and url.hostname and url.username and url.password and not url.fragment)
        _ = url.port
    except ValueError:
        valid = False
    if not valid:
        raise RuntimeError('FARM_DATABASE_URL must be a PostgreSQL connection to gamefarm with credentials')
    data.setdefault('FARM_EVENT_SECRET', secrets.token_urlsafe(48))
    if len(data['FARM_EVENT_SECRET'].encode()) < 32:
        raise RuntimeError('Existing FARM_EVENT_SECRET requires coordinated rotation; it was not replaced')
    data['FARM_REWARDS_ENABLED'] = 'true'
    return data, mode


def main():
    existing = read('secret', SECRET)
    config = read('configmap', 'bdc-config')
    shared = read('secret', 'bdc-secrets')
    if not config or not shared:
        raise RuntimeError('bdc-config and bdc-secrets must already exist')
    data, mode = connection_values(existing, config['data'], decode(shared), os.environ.get('FARM_DATABASE_URL', ''))
    if existing is None:
        existing = {'metadata': {'name': SECRET}}
        action = 'create'
    else:
        action = 'replace'
    existing['metadata'].setdefault('annotations', {})[SOURCE] = mode
    obj = {'apiVersion': 'v1', 'kind': 'Secret', 'type': 'Opaque',
           'metadata': existing['metadata'],
           'data': {k: base64.b64encode(v.encode()).decode() for k, v in data.items()}}
    kubectl(action, '-f', '-', obj=obj)
    # A stable digest forces pods to reload changed env even with the same image.
    print(hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest())


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(str(exc) if isinstance(exc, RuntimeError) else 'Farm configuration sync failed', file=sys.stderr)
        raise SystemExit(1)
