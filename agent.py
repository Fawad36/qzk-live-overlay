from __future__ import annotations
import argparse, asyncio, hashlib, json, os, platform, queue, socket, subprocess, threading, tkinter as tk
from urllib.parse import quote, urlsplit
import urllib.request
import websockets

DEFAULT_PORT = int(os.getenv('QZK_PORT', '9000'))

def get_hwid():
    override=os.getenv('QZK_HWID','').strip()
    if override: return override
    raw=[]
    if platform.system()=='Windows':
        for cmd in [
            ['powershell','-NoProfile','-Command','(Get-CimInstance Win32_ComputerSystemProduct).UUID'],
            ['powershell','-NoProfile','-Command','(Get-CimInstance Win32_BIOS).SerialNumber']]:
            try:
                out=subprocess.check_output(cmd,stderr=subprocess.DEVNULL,text=True,timeout=5).strip()
                if out: raw.append(out)
            except Exception: pass
    if not raw: raw=[platform.node(),platform.machine()]
    return hashlib.sha256('|'.join(raw).encode()).hexdigest()

class Overlay:
    def __init__(self, events):
        self.events=events
        self.root=tk.Tk(); self.root.title('QZK Overlay Agent'); self.root.attributes('-topmost',True)
        self.root.overrideredirect(True); self.root.configure(bg='#111111'); self.root.attributes('-alpha',0.96)
        self.label=tk.Label(self.root,text='',bg='#111111',fg='#efefef',font=('Segoe UI',16,'bold'),justify='left',anchor='nw')
        self.label.pack(fill='both',expand=True,padx=8,pady=6); self.root.geometry('700x100+40+40')
        self.root.bind('<Escape>',lambda e:self.root.destroy()); self.root.after(30,self.poll)
    def apply(self,s):
        if not isinstance(s,dict): return
        size=max(8,min(120,int(s.get('font_size',16))))
        weight='bold' if s.get('bold',True) else 'normal'
        self.label.config(text=s.get('text',''),fg=s.get('text_color','#efefef'),font=(s.get('font_family','Segoe UI'),size,weight))
        self.root.attributes('-alpha',max(0.05,min(1,float(s.get('opacity',100))/100)))
        width=max(200,min(2400,int(s.get('width',700)))); height=max(50,min(600,int(s.get('height',100))))
        x=int(s.get('x',40)); y=int(s.get('y',40))
        self.root.geometry(f'{width}x{height}+{x}+{y}')
        self.root.deiconify() if s.get('enabled',True) else self.root.withdraw()
    def poll(self):
        try:
            while True: self.apply(self.events.get_nowait())
        except queue.Empty: pass
        self.root.after(30,self.poll)
    def run(self): self.root.mainloop()

def websocket_base(server):
    server=server.strip().rstrip('/')
    if server.startswith('https://'): return 'wss://'+server[8:]
    if server.startswith('http://'): return 'ws://'+server[7:]
    if server.startswith(('wss://','ws://')): return server
    if server: return 'ws://'+server
    raise ValueError('Server URL is empty')

def http_base(server):
    s=server.strip().rstrip('/')
    if s.startswith('ws://'): return 'http://'+s[5:]
    if s.startswith('wss://'): return 'https://'+s[6:]
    if s.startswith(('http://','https://')): return s
    return 'http://'+s

def preflight(server, quiet=False):
    s=http_base(server)
    try:
        with urllib.request.urlopen(s+'/health', timeout=3) as r:
            return getattr(r,'status',200) < 400
    except Exception as e:
        if not quiet:
            host=urlsplit(s).hostname or ''
            print(f'Server health check failed: {e}')
            if host in ('127.0.0.1','localhost','::1'):
                print('If server is on Laptop B and agent is on Laptop A, use Laptop B LAN IP, e.g. http://192.168.1.10:9000')
        return False

def discover_server(port=DEFAULT_PORT, timeout=0.22):
    """Best-effort LAN discovery. It never leaves the local subnet."""
    candidates=[]
    try:
        local=socket.gethostbyname(socket.gethostname())
        parts=local.split('.')
        if len(parts)==4 and parts[0] != '127':
            prefix='.'.join(parts[:3])
            candidates=[f'{prefix}.{i}' for i in range(1,255) if i != int(parts[3])]
    except Exception:
        return None
    found=queue.Queue()
    def probe(ip):
        try:
            with socket.create_connection((ip,port),timeout=timeout): found.put(ip)
        except OSError: pass
    threads=[]
    for ip in candidates:
        t=threading.Thread(target=probe,args=(ip,),daemon=True); t.start(); threads.append(t)
    for t in threads: t.join(timeout+0.05)
    while not found.empty():
        ip=found.get()
        url=f'http://{ip}:{port}'
        if preflight(url,quiet=True): return url
    return None

async def socket_loop(server,token,label,events):
    hwid=get_hwid(); backoff=0.5; discovery_done=False
    while True:
        try:
            if server.lower() in ('auto','discover') or (not discovery_done and urlsplit(http_base(server)).hostname in ('127.0.0.1','localhost','::1')):
                found=await asyncio.to_thread(discover_server,DEFAULT_PORT)
                discovery_done=True
                if found:
                    print('Discovered server:',found); server=found
                elif server.lower() in ('auto','discover'):
                    print('LAN server not found yet; retrying...'); await asyncio.sleep(2); discovery_done=False; continue
            if not preflight(server):
                await asyncio.sleep(backoff); backoff=min(backoff*2,8); continue
            ws_base=websocket_base(server)
            uri=ws_base+'/ws/agent/'+quote(token,safe='')+'?hwid='+quote(hwid,safe='')+'&label='+quote(label,safe='')
            print('Connecting:',ws_base+'/ws/agent/<token>')
            async with websockets.connect(uri,ping_interval=15,ping_timeout=8,close_timeout=2,max_size=2**20) as ws:
                print('Connected | label=',label,'| HWID=',hwid); backoff=0.5
                async for raw in ws:
                    try: m=json.loads(raw)
                    except Exception: continue
                    if m.get('type') in ('hello','state'): events.put(m.get('state') or {})
                    elif m.get('type')=='ping': await ws.send(json.dumps({'type':'pong'}))
        except asyncio.CancelledError: raise
        except Exception as e:
            print('Disconnected:',e); await asyncio.sleep(backoff); backoff=min(backoff*2,8)

def main():
    global DEFAULT_PORT
    p=argparse.ArgumentParser(description='QZK Live Overlay Agent')
    p.add_argument('--server',default=os.getenv('QZK_SERVER','auto'))
    p.add_argument('--token',default=os.getenv('QZK_TOKEN',''))
    p.add_argument('--label',default=os.getenv('QZK_LABEL',platform.node()))
    p.add_argument('--port',type=int,default=DEFAULT_PORT)
    p.add_argument('--no-window',action='store_true'); a=p.parse_args()
    if not a.token: raise SystemExit('Missing --token')
    DEFAULT_PORT=a.port
    events=queue.Queue()
    t=threading.Thread(target=lambda:asyncio.run(socket_loop(a.server,a.token,a.label,events)),daemon=True); t.start()
    if a.no_window: t.join()
    else:
        try: Overlay(events).run()
        except tk.TclError as e: raise SystemExit('Desktop overlay could not start: '+str(e))
if __name__=='__main__': main()
