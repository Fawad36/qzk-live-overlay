from __future__ import annotations
import asyncio, json, secrets
from pathlib import Path
from typing import Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from .config import settings, ROOT
from .db import init_db, new_license, list_licenses, get_license, valid_license, register_device, list_devices, touch_device, create_session, get_session, save_state, load_state, add_event

init_db()
app=FastAPI(title=settings.app_name, version='1.0.0')
origins=[x.strip() for x in settings.cors_origins.split(',') if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=['*'], allow_headers=['*'])

class Hub:
    def __init__(self): self.clients={}; self.lock=asyncio.Lock()
    async def add(self, sid, ws, kind, hwid=''):
        async with self.lock: self.clients.setdefault(sid,[]).append((ws,kind,hwid))
    async def remove(self, ws):
        async with self.lock:
            for sid, arr in list(self.clients.items()):
                self.clients[sid]=[x for x in arr if x[0] is not ws]
                if not self.clients[sid]: self.clients.pop(sid,None)
    async def broadcast(self,sid,msg,exclude=None):
        raw=json.dumps(msg,separators=(',',':')); dead=[]
        async with self.lock:
            arr=list(self.clients.get(sid,[]))
        for ws,_,_ in arr:
            if ws is exclude: continue
            try: await ws.send_text(raw)
            except Exception: dead.append(ws)
        for ws in dead: await self.remove(ws)
    async def count(self,sid,kind=None):
        async with self.lock:
            arr=self.clients.get(sid,[])
            return sum(1 for _,k,_ in arr if kind is None or k==kind)
hub=Hub()

BASE=Path(__file__).resolve().parent.parent

def admin_ok(password):
    return secrets.compare_digest(password or '', settings.admin_password)
def require_admin(password):
    if not admin_ok(password): raise HTTPException(401,'Invalid admin password')

def html(name):
    p=BASE/'static'/name
    return HTMLResponse(p.read_text(encoding='utf-8'))

@app.get('/')
def root(): return {'name':settings.app_name,'version':app.version,'status':'ok'}
@app.get('/health')
def health(): return {'ok':True,'service':settings.app_name}
@app.get('/admin',response_class=HTMLResponse)
def admin(): return html('admin.html')
@app.get('/control',response_class=HTMLResponse)
def control(): return html('control.html')
@app.get('/overlay',response_class=HTMLResponse)
def overlay(): return html('overlay.html')

@app.get('/api/admin/licenses')
def api_licenses(password:str=Query(...)):
    require_admin(password); return [dict(x) for x in list_licenses()]
@app.post('/api/admin/licenses')
def api_new_license(body:dict):
    require_admin(body.get('admin_password')); row=new_license(int(body.get('days',0)),body.get('license_key') or None); return dict(row)
@app.post('/api/admin/devices')
def api_device(body:dict):
    require_admin(body.get('admin_password'))
    if not body.get('license_key') or not body.get('hwid'): raise HTTPException(400,'license_key and hwid required')
    row=register_device(body['license_key'],body['hwid'],body.get('label',''),body.get('role','agent'))
    if not row: raise HTTPException(400,'Invalid or expired license')
    return dict(row)
@app.get('/api/admin/devices')
def api_devices(password:str=Query(...),license_key:str|None=None):
    require_admin(password); return [dict(x) for x in list_devices(license_key)]
@app.post('/api/admin/sessions')
def api_session(body:dict):
    require_admin(body.get('admin_password'))
    row,token=create_session(body.get('license_key',''),body.get('name','Session'),int(body.get('days',0)))
    if not row: raise HTTPException(400,'Invalid or expired license')
    return {'id':row['id'],'name':row['session_name'],'token':token}

@app.get('/api/license/validate')
def validate(license_key:str,hwid:str):
    lic=get_license(license_key)
    if not valid_license(lic): raise HTTPException(403,'License invalid or expired')
    dev=register_device(license_key,hwid,label='validated',role='agent')
    return {'valid':True,'license':license_key,'hwid':hwid,'device_id':dev['id']}

@app.get('/api/session/{token}')
def session_info(token:str):
    row=get_session(token)
    if not row: raise HTTPException(404,'Session not found or expired')
    state=load_state(row); return {'session':row['session_name'],'state':state,'clients':0}

@app.websocket('/ws/agent/{token}')
async def ws_agent(ws:WebSocket,token:str,hwid:str=Query(...),label:str=Query('')):
    await ws.accept(); row=get_session(token)
    if not row:
        await ws.close(code=1008,reason='Invalid session'); return
    lic=get_license(row['license_key'])
    if not valid_license(lic): await ws.close(code=1008,reason='Invalid license'); return
    register_device(row['license_key'],hwid,label,'agent'); touch_device(row['license_key'],hwid)
    await hub.add(row['id'],ws,'agent',hwid)
    state=load_state(row)
    await ws.send_json({'type':'hello','session':row['session_name'],'state':state})
    await hub.broadcast(row['id'],{'type':'presence','count':await hub.count(row['id'],'agent')})
    try:
        while True:
            data=await ws.receive_text()
            try: msg=json.loads(data)
            except Exception: continue
            if msg.get('type')=='ping':
                await ws.send_json({'type':'pong'}); touch_device(row['license_key'],hwid); continue
            if msg.get('type')=='state_ack': continue
    except WebSocketDisconnect: pass
    finally:
        await hub.remove(ws); await hub.broadcast(row['id'],{'type':'presence','count':await hub.count(row['id'],'agent')})

@app.websocket('/ws/control/{token}')
async def ws_control(ws:WebSocket,token:str):
    await ws.accept(); row=get_session(token)
    if not row: await ws.close(code=1008,reason='Invalid session'); return
    await hub.add(row['id'],ws,'control')
    await ws.send_json({'type':'hello','state':load_state(row),'session':row['session_name']})
    try:
        while True:
            data=await ws.receive_text()
            try: msg=json.loads(data)
            except Exception: continue
            if msg.get('type')!='state': continue
            state=msg.get('state') or {}
            state['updated_at']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
            save_state(row['id'],state); add_event(row['id'],'state',state)
            await hub.broadcast(row['id'],{'type':'state','state':state},exclude=ws)
    except WebSocketDisconnect: pass
    finally: await hub.remove(ws)

@app.get('/api/admin/check')
def admin_check(password:str=Query(...)): require_admin(password); return {'ok':True}
