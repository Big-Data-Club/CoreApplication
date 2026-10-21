#!/usr/bin/env python3
"""Deploy only the warehouse release; reuse the production runner's kubeconfig."""
import argparse
import copy
import json
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def kubectl(*args,obj=None,allow_missing=False):
    result=subprocess.run(['kubectl','-n','default',*args],input=json.dumps(obj) if obj else None,
                          capture_output=True,text=True,timeout=120)
    if result.returncode:
        if allow_missing and 'NotFound' in result.stderr:
            return None
        raise RuntimeError('kubectl operation failed: '+' '.join(args[:3]))
    return result.stdout


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',required=True)
    parser.add_argument('--revision',required=True)
    args=parser.parse_args()
    if not re.fullmatch(r'[a-z0-9./_-]+@sha256:[0-9a-f]{64}',args.image):
        parser.error('An immutable registry image digest is required.')
    if not re.fullmatch(r'[0-9a-f]{40}',args.revision):
        parser.error('Full source commit SHA is required.')
    resources=json.loads((ROOT/'k3s/data-warehouse/resources.json').read_text())['items']
    deployment=next(x for x in resources if x['kind']=='Deployment')
    previous=kubectl('get','deployment','data-warehouse-worker','-o','json',allow_missing=True)
    previous=json.loads(previous) if previous else None
    for obj in resources:
        if obj['kind']!='Deployment':
            kubectl('apply','-f','-',obj=obj)
    for name in ('data-warehouse','data-warehouse-deployer'):
        credential=json.loads((ROOT/f'data-warehouse/config/{name}-identity.json').read_text())
        # Credential configuration is public routing metadata; contains no key.
        if credential.get('type')!='external_account' or 'private_key' in credential:
            raise RuntimeError('Only keyless external-account configuration is permitted')
        kubectl('apply','-f','-',obj={'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':name+'-identity'},
                                    'data':{'credentials.json':json.dumps(credential)}})
    pod=deployment['spec']['template']['spec']
    pod['containers'][0]['image']=args.image
    pod['containers'][0]['env'].append({'name':'BDC_VERSION','value':args.revision})
    deployment['spec']['template']['metadata']['annotations']={'bdc.io/source-revision':args.revision}
    migration_pod=copy.deepcopy(pod)
    migration_pod['serviceAccountName']='data-warehouse-deployer'
    migration_pod['restartPolicy']='Never'
    migration_pod['terminationGracePeriodSeconds']=30
    migration_pod['volumes']=[v for v in migration_pod['volumes'] if v['name']!='state']
    for volume in migration_pod['volumes']:
        if volume['name']=='gcp-configuration':
            volume['configMap']['name']='data-warehouse-deployer-identity'
    container=migration_pod['containers'][0]
    container['command']=['python','-m','worker.migrate']
    container['volumeMounts']=[v for v in container['volumeMounts'] if v['name']!='state']
    for key in ('startupProbe','livenessProbe','readinessProbe','ports'):
        container.pop(key,None)
    job_name='warehouse-schema-'+args.revision[:10]+'-'+uuid.uuid4().hex[:6]
    job={'apiVersion':'batch/v1','kind':'Job','metadata':{'name':job_name},
         'spec':{'backoffLimit':0,'activeDeadlineSeconds':600,'ttlSecondsAfterFinished':3600,
                 'template':{'metadata':{'labels':{'app':'data-warehouse-migration'}},'spec':migration_pod}}}
    kubectl('create','-f','-',obj=job)
    deadline=time.monotonic()+660
    while time.monotonic()<deadline:
        status=json.loads(kubectl('get','job',job_name,'-o','json'))['status']
        if status.get('failed'):
            raise RuntimeError('Warehouse schema Job failed; worker was not updated. Inspect sanitized migration logs.')
        if status.get('succeeded'):
            break
        time.sleep(3)
    else:
        raise RuntimeError('Warehouse schema Job did not finish; worker was not updated')
    try:
        kubectl('apply','-f','-',obj=deployment)
        result=subprocess.run(['kubectl','-n','default','rollout','status','deployment/data-warehouse-worker','--timeout=480s'],check=False)
        if result.returncode:
            raise RuntimeError('Warehouse rollout failed')
        status_code="import json,urllib.request; s=json.load(urllib.request.urlopen('http://127.0.0.1:8080/status',timeout=5)); print(json.dumps(s)); assert s['ready']; assert s['version']=='"+args.revision+"'"
        observed=json.loads(kubectl('exec','deployment/data-warehouse-worker','--','python','-c',status_code))
        # If real source records are waiting, readiness alone is insufficient:
        # require a successful upload before this release is called deployed.
        if observed.get('source_lag') or observed.get('pending_records'):
            baseline=observed.get('successful_batches',0)
            deadline=time.monotonic()+480
            while time.monotonic()<deadline:
                if observed.get('successful_batches',0)>baseline or (
                    observed.get('source_lag')==0 and observed.get('pending_records')==0
                ):
                    break
                time.sleep(5)
                observed=json.loads(kubectl('exec','deployment/data-warehouse-worker','--','python','-c',status_code))
            else:
                raise RuntimeError('Worker is ready but the waiting real batch was not acknowledged before the release deadline')
        print(json.dumps({'deployed':True,'image':args.image,'revision':args.revision,'worker_status':observed},indent=2))
    except Exception:
        if previous:
            # Restore the previous full pod spec, not a mutable latest image.
            restored=copy.deepcopy(previous)
            restored.pop('status',None)
            for name in ('resourceVersion','uid','creationTimestamp','generation','managedFields'):
                restored['metadata'].pop(name,None)
            kubectl('apply','-f','-',obj=restored)
            print('Restored the previous warehouse Deployment after a failed rollout.',file=sys.stderr)
        raise


if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        print(str(exc),file=sys.stderr)
        raise SystemExit(1)
