#!/usr/bin/env python3
"""Select only actual application source changes for the legacy rollout path."""
import os
import subprocess

WORKLOADS={
 'auth-and-management-service':('auth-service',),
 'frontend':('frontend',),
 'lms-service':('lms-service',),
 'ai-service':('ai-service','ai-worker','course-blueprint-worker','ai-lab-authoring-worker'),
 'recommender-service':('recommender-service',),
 'chat-service':('chat-service',),
 'lab-service':('lab-service',),
 'personalize-service':('personalize-service',),
 'dutylog':('dutylog-service',),
}


def select(paths):
    selected=[]
    for path in paths:
        for deployment in WORKLOADS.get(path.split('/',1)[0],()):
            if deployment not in selected:
                selected.append(deployment)
    return selected


def main():
    if os.environ.get('EVENT')=='workflow_dispatch':
        target=os.environ.get('MANUAL_TARGET','all')
        allowed=[d for names in WORKLOADS.values() for d in names]
        if target!='all' and target not in allowed:
            raise SystemExit('Unknown manual deployment target')
        deployments=allowed if target=='all' else [target]
    else:
        changed=subprocess.check_output(['git','diff','--name-only','HEAD^','HEAD'],text=True).splitlines()
        deployments=select(changed)
    with open(os.environ['GITHUB_OUTPUT'],'a') as output:
        output.write('services='+','.join(deployments)+'\n')


if __name__=='__main__':
    main()
