import os, tempfile
os.environ['QZK_DB_PATH']=os.path.join(tempfile.gettempdir(),'qzk_test.sqlite3')
os.environ['QZK_ADMIN_PASSWORD']='test-admin'
from fastapi.testclient import TestClient
from app.main import app
from app.db import init_db, new_license, register_device, create_session, get_session

def setup_module():
    try: os.remove(os.environ['QZK_DB_PATH'])
    except FileNotFoundError: pass
    init_db()

def test_license_device_session():
    r=new_license(1,'TEST-AAAA-BBBB-CCCC')
    assert r['license_key']=='TEST-AAAA-BBBB-CCCC'
    d=register_device(r['license_key'],'HWID-A','Laptop A')
    assert d['hwid']=='HWID-A'
    s,t=create_session(r['license_key'],'Test')
    assert s and t and get_session(t)['session_name']=='Test'

def test_http_and_ws():
    with TestClient(app) as c:
        assert c.get('/health').json()['ok'] is True
        lic=c.post('/api/admin/licenses',json={'admin_password':'test-admin','days':1,'license_key':'TEST-WS-AAAA'}).json()['license_key']
        c.post('/api/admin/devices',json={'admin_password':'test-admin','license_key':lic,'hwid':'A','label':'Laptop A'})
        c.post('/api/admin/devices',json={'admin_password':'test-admin','license_key':lic,'hwid':'B','label':'Laptop B'})
        sess=c.post('/api/admin/sessions',json={'admin_password':'test-admin','license_key':lic,'name':'AB'}).json()
        token=sess['token']
        with c.websocket_connect('/ws/agent/'+token+'?hwid=A&label=LaptopA') as a, c.websocket_connect('/ws/agent/'+token+'?hwid=B&label=LaptopB') as b, c.websocket_connect('/ws/control/'+token) as ctl:
            assert a.receive_json()['type']=='hello'
            assert b.receive_json()['type']=='hello'
            assert ctl.receive_json()['type']=='hello'
            ctl.send_json({'type':'state','state':{'text':'hello A+B','enabled':True}})
            # Presence events can arrive before the state; consume until state.
            def next_state(ws):
                for _ in range(5):
                    m=ws.receive_json()
                    if m.get('type')=='state': return m
                raise AssertionError('state broadcast not received')
            assert next_state(a)['state']['text']=='hello A+B'
            assert next_state(b)['state']['text']=='hello A+B'
        assert c.get('/api/session/'+token).status_code==200
