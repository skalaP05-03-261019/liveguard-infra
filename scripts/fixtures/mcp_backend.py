"""Read-only synthetic Backend: source IP only, no request body logging."""
import asyncio
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
app=FastAPI()
release=asyncio.Event()
waiting=None
block=False
@app.middleware('http')
async def auth(request:Request,call_next):
    if request.url.path.startswith('/internal/') and request.headers.get('x-service-token')!=os.environ['INTERNAL_SERVICE_TOKEN']:
        return JSONResponse(status_code=401,content={'error':'UNAUTHENTICATED'})
    return await call_next(request)
@app.get('/internal/cases/{case_id}')
async def case(case_id:str,request:Request):
    global waiting,block
    if block:
        block=False;waiting=request.client.host
        await release.wait();waiting=None
    return {'data':{'caseId':case_id,'servedBy':request.client.host}}
@app.get('/test/state')
async def state():return {'waitingRead':waiting}
@app.post('/test/block-read')
async def hold():
    global block
    release.clear();block=True
    return {}
@app.post('/test/release-read')
async def finish():
    release.set()
    return {}
