"""Recover a failed Deployment without accepting readiness from its old revision."""
import importlib.util
import json
import unittest
import sys
import copy
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('warehouse_deploy',Path(__file__).parents[1]/'deploy-data-warehouse.py')
deploy=importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


def deployment(ready, observed=2, revision='release'):
    return json.dumps({
        'metadata':{'generation':2},
        'spec':{'replicas':1,'template':{'metadata':{'annotations':{'bdc.io/source-revision':revision}}}},
        'status':{'observedGeneration':observed,'replicas':1,'updatedReplicas':int(ready),
                  'readyReplicas':int(ready),'availableReplicas':int(ready),
                  'conditions':[{'type':'Progressing','status':'False','reason':'ProgressDeadlineExceeded'}]},
    })


class RolloutTests(unittest.TestCase):
    def test_scheduled_snapshot_is_pinned_after_worker_verification(self):
        revision='a'*40
        image='unit-registry/warehouse@sha256:'+'b'*64
        applied=[]
        verified=[]
        def command(*args,obj=None,**kwargs):
            if args[:3]==('get','deployment','data-warehouse-worker'):
                return None
            if args[:2]==('get','job'):
                return json.dumps({'status':{'succeeded':1}})
            if args[0]=='exec':
                verified.append(True)
                return json.dumps({'ready':True,'version':revision,'source_lag':0,'pending_records':0})
            if obj:
                if obj['kind']=='CronJob':
                    self.assertTrue(verified)
                applied.append(copy.deepcopy(obj))
            return ''
        with patch.object(deploy,'kubectl',side_effect=command),patch.object(deploy,'wait_for_rollout'):
            with patch.object(sys,'argv',['deploy','--image',image,'--revision',revision]):
                with patch('builtins.print'):
                    deploy.main()
        cron=next(obj for obj in applied if obj['kind']=='CronJob')
        scheduled=cron['spec']['jobTemplate']['spec']['template']['spec']
        self.assertEqual(scheduled['containers'][0]['image'],image)
        self.assertEqual(scheduled['serviceAccountName'],'data-warehouse')
        migration=next(obj for obj in applied if obj['kind']=='Job')
        self.assertEqual(migration['spec']['template']['spec']['serviceAccountName'],'data-warehouse-deployer')
        self.assertFalse(any(v['name']=='state' for v in migration['spec']['template']['spec']['volumes']))

    def test_old_deadline_condition_does_not_abort_new_generation(self):
        with patch.object(deploy,'kubectl',side_effect=[deployment(False,1),deployment(False),deployment(True)]) as get:
            with patch.object(deploy.time,'sleep'):
                deploy.wait_for_rollout('release')
        self.assertEqual(get.call_count,3)

    def test_unready_new_generation_still_has_a_bounded_deadline(self):
        with patch.object(deploy,'kubectl',return_value=deployment(False)):
            with patch.object(deploy.time,'monotonic',side_effect=[0,0,2]):
                with patch.object(deploy.time,'sleep'):
                    with self.assertRaisesRegex(RuntimeError,'timed out'):
                        deploy.wait_for_rollout('release',timeout=1)

    def test_other_revision_is_never_accepted(self):
        with patch.object(deploy,'kubectl',return_value=deployment(True,revision='other')):
            with self.assertRaisesRegex(RuntimeError,'different source revision'):
                deploy.wait_for_rollout('release')


if __name__=='__main__':
    unittest.main()
