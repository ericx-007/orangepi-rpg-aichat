"""Stop only the three recorded workspace components before a managed restart."""
import json
from pathlib import Path
import time
import psutil
ROOT=Path(__file__).resolve().parents[2]
STATE=ROOT/'qq-runtime/state'
(STATE/'runtime-maintenance.json').write_text(json.dumps({'until':time.time()+900,'reason':'managed component stop'}))
for role in ['napcat','astrbot','tunnel']:
    record=ROOT/'logs/auto-tunnel-status.json' if role=='tunnel' else STATE/('background-'+role+'.json')
    pid=int(json.loads(record.read_text())['pid'])
    try:p=psutil.Process(pid)
    except psutil.NoSuchProcess:continue
    command=p.cmdline()
    if role=='napcat':assert Path(command[1]).resolve()==(ROOT/'qq-runtime/napcat/index.js').resolve()
    elif role=='astrbot':assert command[1]=='main.py' and Path(p.cwd()).resolve()==(ROOT/'qq-runtime/astrbot').resolve()
    else:assert Path(command[1]).resolve()==(ROOT/'auto-tunnel.py').resolve()
    if role=='tunnel':
        (ROOT/'logs/auto-tunnel.stop').write_text('managed restart')
        try:p.wait(timeout=12);print('STOPPED_OWNED_COMPONENT',role);continue
        except psutil.TimeoutExpired:pass
    children=p.children(recursive=True)
    for child in reversed(children):
        try:child.terminate()
        except psutil.NoSuchProcess:pass
    try:p.terminate()
    except psutil.NoSuchProcess:pass
    _,remaining=psutil.wait_procs(children+[p],timeout=5)
    for child in remaining:child.kill()
    print('STOPPED_OWNED_COMPONENT',role)
