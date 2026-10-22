"""Reconnect the user's loopback model tunnel after Windows logon or board restart."""
import ctypes
from collections import deque
from ctypes import wintypes
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import socket
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parent
LOGS = ROOT / 'logs'
LOGS.mkdir(exist_ok=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
mutex = kernel32.CreateMutexW(None, False, 'Local\\OrangePiLocalLlmTunnel')
if not mutex:
    raise ctypes.WinError(ctypes.get_last_error())
if ctypes.get_last_error() == 183:
    kernel32.CloseHandle(mutex)
    raise SystemExit(0)

logger = logging.getLogger('tunnel')
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(LOGS / 'auto-tunnel.log', maxBytes=1024*1024, backupCount=2, encoding='utf-8')
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logger.addHandler(handler)
status_file = LOGS / 'auto-tunnel-status.json'
stop_file = LOGS / 'auto-tunnel.stop'
child = None
reader = None

def status(state, **extra):
    payload = {'state': state, 'updated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
               'url': 'http://127.0.0.1:8000', 'pid': __import__('os').getpid(), **extra}
    temporary = status_file.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    for attempt in range(5):
        try:
            temporary.replace(status_file)
            break
        except PermissionError:
            if attempt == 4: raise
            time.sleep(0.05)

def port_available():
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(('127.0.0.1', 8000))
            return True
        except OSError:
            return False

def pause(seconds):
    for _ in range(seconds):
        if stop_file.exists(): return
        time.sleep(1)

try:
    logger.info('Starting automatic SSH tunnel')
    while not stop_file.exists():
        if not port_available():
            status('port_in_use')
            logger.warning('Local port8000 is already in use; retrying without interrupting its owner')
            pause(15)
            continue
        status('connecting')
        command = [r'C:\Windows\System32\OpenSSH\ssh.exe', '-F', str(ROOT / 'config' / 'ssh.local.conf'), '-N', 'orangepi-local-llm']
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
        errors = deque(maxlen=20)
        def drain(stream, recent):
            for line in iter(stream.readline, b''):
                message = line.decode('utf-8', errors='replace').strip()
                if message:
                    recent.append(message)
                    logger.warning('SSH: %s', message)
        reader = threading.Thread(target=drain, args=(child.stderr, errors), daemon=True)
        reader.start()
        status('connecting', ssh_pid=child.pid)
        connected = False
        while child.poll() is None and not stop_file.exists():
            if not connected:
                try:
                    with socket.create_connection(('127.0.0.1',8000),timeout=0.2):
                        connected = True
                    status('forwarding', ssh_pid=child.pid)
                    logger.info('SSH tunnel forwarding on127.0.0.1:8000, process%s', child.pid)
                except OSError:
                    pass
            time.sleep(1)
        if stop_file.exists(): break
        reader.join(timeout=2)
        error = '\n'.join(errors)
        logger.warning('SSH exited with%s: %s', child.returncode, error[-1500:])
        status('reconnecting', last_error=error[-600:])
        child.stderr.close(); child = None; reader = None
        pause(5)
finally:
    if child is not None:
        if child.poll() is None:
            child.terminate()
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=5)
        if reader is not None: reader.join(timeout=2)
        child.stderr.close()
    status('stopped')
    kernel32.CloseHandle(mutex)
