#!/usr/bin/env python3
"""Compare resolved Compose against pre-HA baseline without exposing environment values."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
def run(args):
    result=subprocess.run(args,capture_output=True,text=True)
    if result.returncode:raise RuntimeError('Validation command failed; output withheld')
    return result.stdout

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--env-file',required=True,type=Path)
    p.add_argument('--project',required=True)
    p.add_argument('--baseline',default='abf54b11998ad1abbc05022ab190c348328eff8f')
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    base=['docker','compose','--profile','rabbit','--env-file',str(args.env_file.resolve()),
          '--project-directory',str(ROOT),'-p',args.project]
    with tempfile.NamedTemporaryFile(mode='w',suffix='.yaml') as f:
        f.write(run(['git','-C',str(ROOT),'show',args.baseline+':compose.yaml']));f.flush()
        old=json.loads(run(base+['-f',f.name,'config','--format','json']))
        new=json.loads(run(base+['-f',str(ROOT/'compose.yaml'),'config','--format','json']))
    unchanged=['db','backend','rag-mcp','rabbitmq','frontend']
    for name in unchanged:assert old['services'][name]==new['services'][name],name
    agent=new['services']['agent'].copy();agent['environment']=agent['environment'].copy()
    changes=['BUSINESS_MCP_CLIENT_CONCURRENCY','BUSINESS_MCP_CALL_TIMEOUT']
    for key in changes:agent['environment'].pop(key)
    assert agent==old['services']['agent']
    assert old['volumes']==new['volumes']
    for name,service in new['services'].items():
        if 'build' in service:
            assert (Path(service['build']['context'])/service['build'].get('dockerfile','Dockerfile')).is_file(),name
    assert new['services']['business-mcp-1']['image']==new['services']['business-mcp-2']['image']
    for name in ('business-mcp-1','business-mcp-2'):
        assert not new['services'][name].get('ports')
    report={'result':'PASS','unchanged_services':unchanged,'agent_changes':changes,
            'volumes':new['volumes'],'agent_url':new['services']['agent']['environment']['BUSINESS_MCP_URL'],
            'build_contexts_exist':True}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: unchanged services, volumes, Agent URL and valid build contexts')
if __name__=='__main__':main()
