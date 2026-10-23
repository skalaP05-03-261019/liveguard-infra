#!/usr/bin/env python3
"""Compare resolved Compose against pre-HA baseline without exposing environment values."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
AGENT_REVISION='764eab26a8272d72fc79bcad5b6e7aa82ef8d8b0'
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
    p.add_argument('--portable', action='store_true',
                   help='CI invariants only: skip historical comparison, local paths and source provenance')
    args=p.parse_args()
    if not __debug__:
        raise RuntimeError('Run validation without Python optimization (-O/PYTHONOPTIMIZE)')
    base=['docker','compose','--profile','rabbit','--env-file',str(args.env_file.resolve()),
          '--project-directory',str(ROOT),'-p',args.project]
    new=json.loads(run(base+['-f',str(ROOT/'compose.yaml'),'config','--format','json']))
    unchanged=['db','backend','rag-mcp','rabbitmq','frontend']
    changes=['BUSINESS_MCP_CLIENT_CONCURRENCY','BUSINESS_MCP_CALL_TIMEOUT']
    if not args.portable:
        with tempfile.NamedTemporaryFile(mode='w',suffix='.yaml') as f:
            f.write(run(['git','-C',str(ROOT),'show',args.baseline+':compose.yaml']));f.flush()
            old=json.loads(run(base+['-f',f.name,'config','--format','json']))
        for name in unchanged:assert old['services'][name]==new['services'][name],name
        agent=new['services']['agent'].copy();agent['environment']=agent['environment'].copy()
        for key in changes:agent['environment'].pop(key)
        assert agent==old['services']['agent']
        assert old['volumes']==new['volumes']
    if not args.portable:
        for name,service in new['services'].items():
            if 'build' in service:
                assert (Path(service['build']['context'])/service['build'].get('dockerfile','Dockerfile')).is_file(),name
        source=new['services']['business-mcp-1']['build']['context']
        revision=run(['git','-C',source,'rev-parse','HEAD']).strip()
        if revision != AGENT_REVISION or run(['git','-C',source,'status','--porcelain']).strip():
            raise RuntimeError('Agent source must be a clean checkout of '+AGENT_REVISION)
        if new['services']['agent']['build']['context'] != source:
            raise RuntimeError('Agent and MCP must use the same verified source checkout')
    assert new['services']['business-mcp-1']['image']==new['services']['business-mcp-2']['image']
    for name in ('business-mcp-1','business-mcp-2'):
        assert not new['services'][name].get('ports')
    assert new['services']['agent']['environment']['BUSINESS_MCP_URL']=='http://business-mcp:8002/mcp'
    for name in ('liveguard_db','liveguard_agent_tasks','liveguard_rabbitmq'):
        assert new['volumes'][name]['name']==args.project+'_'+name
    report={'result':'PASS','unchanged_services':'NOT RUN' if args.portable else unchanged,'agent_changes':changes,
            'volumes':new['volumes'],'agent_url':new['services']['agent']['environment']['BUSINESS_MCP_URL'],
            'build_contexts_exist':'NOT RUN' if args.portable else True,
            'agent_source':'NOT RUN' if args.portable else AGENT_REVISION}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    existing=json.loads(args.output.read_text()) if args.output.exists() else {}
    existing['static']=report
    args.output.write_text(json.dumps(existing,indent=2)+'\n')
    print('PASS: portable invariants' if args.portable else 'PASS: source, unchanged services, volumes and Agent URL')
if __name__=='__main__':main()
