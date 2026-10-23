#!/usr/bin/env python3
"""Opt-in isolated Docker acceptance test. Never prints credentials or response bodies.
Requires --env-file with existing credentials and a prebuilt BUSINESS_MCP_IMAGE.
Uses real Infra Compose plus a temporary fixture override; no existing volumes mounted.
"""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]

def run(args, **kw):
    result = subprocess.run(args, capture_output=True, text=True, **kw)
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}): {args[0:2]} (output withheld)')
    return result.stdout.strip()

def mounts(projects):
    ids = run(['docker','ps','-aq']).split()
    data = json.loads(run(['docker','inspect',*ids])) if ids else []
    return {x['Id']: {'name':x['Name'], 'mounts':x['Mounts']} for x in data if x['Config'].get('Labels',{}).get('com.docker.compose.project') in projects}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--preserve-project', action='append', default=['liveguard-infra'],
                        help='Existing project whose container mounts must remain identical; repeatable')
    args=parser.parse_args()
    project='liveguard-mcp-ha-test-'+uuid.uuid4().hex[:10]
    base=['docker','compose','--env-file',str(args.env_file.resolve()),'-p',project,'-f',str(ROOT/'compose.yaml')]
    report={'project':project,'results':{},'limitations':['Fixture Backend; Spring and UNKNOWN effect acceptance are separate.']}
    before=mounts(set(args.preserve_project))
    config=json.loads(run(base+['config','--format','json']))
    for k in ('INTERNAL_SERVICE_TOKEN','BUSINESS_MCP_AGENT_TOKEN','AGENT_SERVICE_TOKEN'):
        service='backend' if k=='INTERNAL_SERVICE_TOKEN' else 'agent'
        if not config['services'][service]['environment'].get(k): raise RuntimeError('Missing credentials')
    image=config['services']['business-mcp-1']['image']
    # Use only existing secrets, passed to Compose internally; no generated credentials.
    override={'services':{
        'backend': {'image':image,'build':None,'ports':[], 'depends_on':{},'volumes':[str(ROOT/'scripts/fixtures')+':/fixture:ro'], 'command':['uvicorn','mcp_backend:app','--app-dir','/fixture','--host','0.0.0.0','--port','8080','--no-access-log']},
        'business-mcp-1':{'restart':'no'},'business-mcp-2':{'restart':'no'},
        'agent':{'image':image,'build':None,'ports':[],'volumes':[], 'environment':{'AGENT_TASK_DB_PATH':'/tmp/ha-test.sqlite3','AGENT_GATEWAY_FACTORY':'','MODEL_API_KEY':''}},
    }}
    # YAML tags reset inherited ports/dependencies/volumes without changing production Compose.
    with tempfile.TemporaryDirectory(prefix='liveguard-mcp-ha-') as td:
        path=Path(td)/'override.yaml'
        text='services:\n'
        for service,values in override['services'].items():
            text+=f'  {service}:\n'
            for key,value in values.items():
                tag='!reset ' if key in ('build','ports','depends_on','volumes') else ''
                if key=='volumes' and value: tag='!override '
                text+=f'    {key}: {tag}{json.dumps(value)}\n'
        path.write_text(text)
        cmd=base+['-f',str(path)]
        def compose(*a): return run(cmd+list(a),timeout=120)
        def cid(service): return compose('ps','-aq',service)
        def inspect(service): return json.loads(run(['docker','inspect',cid(service)]))[0]
        def ip(service): return next(iter(inspect(service)['NetworkSettings']['Networks'].values()))['IPAddress']
        def execute(service,code): return compose('exec','-T',service,'python','-c',code)
        def fixture(path): return execute('backend',f"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/test/{path}',data=b'').read()")
        def state(): return json.loads(execute('backend',"import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/test/state').read().decode())"))
        client="""import asyncio,json,os
from app.clients.business_mcp import BusinessMcpReadClient,BusinessMcpSettings
async def main():
 c=BusinessMcpReadClient(BusinessMcpSettings('http://business-mcp:8002/mcp',os.environ['BUSINESS_MCP_AGENT_TOKEN']))
 results=[]
 for _ in range(COUNT):
  r=await c.call('get_moderation_case',{'caseId':'00000000-0000-4000-8000-000000000001','traceId':'00000000-0000-4000-8000-000000000002'})
  results.append(r['data']['servedBy'])
 print(json.dumps(results))
asyncio.run(main())"""
        def reads(n=12): return json.loads(execute('agent',client.replace('COUNT',str(n))))
        def healthy(service):
            deadline=time.monotonic()+40
            while time.monotonic()<deadline:
                if inspect(service)['State'].get('Health',{}).get('Status')=='healthy':return
                time.sleep(.3)
            raise RuntimeError('Health convergence timeout: '+service)
        def distribution(expected):
            samples=reads(); assert set(samples)==set(expected), 'Wrong serving instances'
            return {address:samples.count(address) for address in set(samples)}
        try:
            compose('config','--quiet')
            resolved=json.loads(compose('config','--format','json'))
            for service in ('backend','agent','business-mcp-1','business-mcp-2','business-mcp'):
                assert not any(v['type']=='volume' for v in resolved['services'][service].get('volumes',[]))
            report['results']['static']='PASS'
            compose('up','-d','--no-deps','--no-build','backend','business-mcp-1','business-mcp-2','business-mcp','agent')
            for service in ('business-mcp-1','business-mcp-2','business-mcp'):healthy(service)
            ids=[inspect(s)['Image'] for s in ('business-mcp-1','business-mcp-2')];assert ids[0]==ids[1]
            report['image_id']=ids[0]
            report['results']['distribution']=distribution([ip('business-mcp-1'),ip('business-mcp-2')])
            original_ip=ip('business-mcp-1')
            compose('kill','-s','SIGKILL','business-mcp-1');time.sleep(4)
            report['results']['single_failure']=distribution([ip('business-mcp-2')])
            compose('up','-d','--no-deps','--no-build','--force-recreate','business-mcp','agent');healthy('business-mcp')
            report['results']['degraded_start']=distribution([ip('business-mcp-2')])
            compose('rm','-f','business-mcp-1')
            # Hold the released address so recreation must exercise a new DNS address.
            network=project+'_default'
            holder=project+'-address-holder'
            run(['docker','run','-d','--name',holder,'--network',network,image,'sleep','120'])
            try:
                compose('up','-d','--no-deps','--no-build','business-mcp-1');healthy('business-mcp-1');time.sleep(7)
                assert ip('business-mcp-1') != original_ip, 'IP did not change'
                report['dns_change']={'before':original_ip,'after':ip('business-mcp-1')}
                report['results']['recovery']=distribution([ip('business-mcp-1'),ip('business-mcp-2')])
            finally:run(['docker','rm','-f',holder])
            fixture('block-read')
            with concurrent.futures.ThreadPoolExecutor() as pool:
                active=pool.submit(reads,1)
                deadline=time.monotonic()+8
                while time.monotonic()<deadline:
                    waiting=state()['waitingRead']
                    if waiting:break
                    time.sleep(.05)
                else:raise RuntimeError('No active request')
                victim=next(s for s in ('business-mcp-1','business-mcp-2') if ip(s)==waiting)
                survivor='business-mcp-2' if victim.endswith('1') else 'business-mcp-1'
                stopping=pool.submit(compose,'stop',victim)
                time.sleep(1);assert not stopping.done() and not active.done()
                fixture('release-read');assert active.result()==[waiting];stopping.result()
            time.sleep(3)
            report['results']['graceful_inflight']=distribution([ip(survivor)])
            report['results']['drain_ready_503']='NOT RUN: signal closes listener before reliable HTTP sampling; application-level test required'
            compose('stop',survivor);time.sleep(3)
            status=execute('agent',"import urllib.request,urllib.error\ntry: print(urllib.request.urlopen('http://business-mcp:8002/ready').status)\nexcept urllib.error.HTTPError as e: print(e.code)")
            assert status=='503';report['results']['total_outage']='PASS: HTTP 503'
            secrets=[config['services']['agent']['environment']['BUSINESS_MCP_AGENT_TOKEN'],config['services']['backend']['environment']['INTERNAL_SERVICE_TOKEN']]
            logs=compose('logs','--no-color','business-mcp','business-mcp-1','business-mcp-2')
            assert all(secret not in logs for secret in secrets)
            report['results']['credential_logging']='PASS'
        except Exception:
            report['failure']='FAIL: acceptance interrupted; see failed assertion without secret output'
            raise
        finally:
            compose('down','--remove-orphans')
            after=mounts(set(args.preserve_project))
            preserved=all(after.get(k)==v for k,v in before.items())
            report['results']['existing_mounts']='PASS' if preserved else 'FAIL'
            report['preserved_mounts']=[v for v in before.values()]
            report['preserved_projects']=args.preserve_project
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(report,indent=2)+'\n')
            assert preserved, 'Existing mounts changed'
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
