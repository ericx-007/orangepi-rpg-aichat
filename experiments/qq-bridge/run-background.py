"""Launch an existing component through a same-user Windows background broker."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import psutil

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'qq-runtime';STATE=BASE/'state'
role=sys.argv[1]
assert role in {'astrbot','napcat','tunnel'}

# Serialize simultaneous manual/watchdog/logon launches of the same component.
launch_kernel=ctypes.WinDLL('kernel32',use_last_error=True)
launch_kernel.CreateMutexW.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR]
launch_kernel.CreateMutexW.restype=wintypes.HANDLE
launch_kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
launch_kernel.ReleaseMutex.argtypes=[wintypes.HANDLE]
launch_kernel.CloseHandle.argtypes=[wintypes.HANDLE]
launch_mutex=launch_kernel.CreateMutexW(None,False,'Local\\OrangePiRuntimeLaunch-'+role)
if not launch_mutex:raise ctypes.WinError(ctypes.get_last_error())
if launch_kernel.WaitForSingleObject(launch_mutex,5000) not in (0,128):
    launch_kernel.CloseHandle(launch_mutex)
    raise SystemExit('Another launch is still in progress')
def image_path(pid):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:return None
    try:
        buf=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(len(buf))
        return Path(buf.value) if kernel.QueryFullProcessImageNameW(handle,0,buf,ctypes.byref(size)) else None
    finally:kernel.CloseHandle(handle)
try:
    env=os.environ.copy()
    env.update(PYTHONUTF8='1',PYTHONUNBUFFERED='1')
    if role=='astrbot':
        exe=BASE/'astrbot-venv/Scripts/python.exe';cwd=BASE/'astrbot'
        argv=[str(exe),'main.py','--webui-dir',str(cwd/'data/dist')]
        env['ASTRBOT_ROOT']=str(cwd)
        stdout,stderr='astrbot.stdout.log','astrbot.stderr.log'
    elif role=='napcat':
        exe=BASE/'napcat/node.exe';cwd=BASE/'napcat'
        argv=[str(exe),str(cwd/'index.js')]
        env.update(NAPCAT_WORKDIR=str(STATE),NAPCAT_DISABLE_TIME_SYNC='1')
        stdout,stderr='runtime.stdout.log','runtime.stderr.log'
    else:
        exe=Path(sys.executable);cwd=ROOT;argv=[str(exe),str(ROOT/'auto-tunnel.py')]
        stdout,stderr='tunnel-launch.stdout.log','tunnel-launch.stderr.log'
    pid_file=STATE/(role+'.pid')
    if role=='tunnel':
        try:
            live=json.loads((ROOT/'logs/auto-tunnel-status.json').read_text())
            process=psutil.Process(int(live['pid']))
            command=process.cmdline()
            if live.get('state')!='stopped' and len(command)>1 and Path(command[1]).resolve()==ROOT/'auto-tunnel.py' and Path(process.cwd()).resolve()==ROOT:
                pid_file.write_text(str(process.pid),encoding='utf-8')
                (STATE/'background-tunnel.json').write_text(json.dumps({'role':'tunnel','pid':process.pid,
                    'adopted_at':time.time(),'pid_source':'existing tunnel helper status'}),encoding='utf-8')
                raise SystemExit(0)
        except (OSError,ValueError,KeyError,psutil.NoSuchProcess,psutil.AccessDenied):pass
    if role!='tunnel' and pid_file.exists():
        prior=image_path(int(pid_file.read_text(encoding='utf-8-sig').strip()))
        if prior:
            assert str(prior).lower()==str(exe).lower(),'Recorded PID belongs to another executable'
            raise SystemExit(0)
    with (STATE/stdout).open('ab',buffering=0) as out,(STATE/stderr).open('ab',buffering=0) as err:
        child=subprocess.Popen(argv,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    pid_file.write_text(str(child.pid),encoding='utf-8')
    (STATE/('background-'+role+'.json')).write_text(json.dumps({'role':role,'pid':child.pid,'broker_pid':os.getpid(),'broker_parent_pid':os.getppid(),'started_at':time.time()}),encoding='utf-8')
except SystemExit:raise
except Exception:
    import traceback
    with (STATE/'background-launch-errors.log').open('a',encoding='utf-8') as log:traceback.print_exc(file=log)
    raise
finally:
    launch_kernel.ReleaseMutex(launch_mutex)
    launch_kernel.CloseHandle(launch_mutex)
