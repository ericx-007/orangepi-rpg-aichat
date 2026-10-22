"""Keep this user's existing QQ, AstrBot and SSH helper running after logon."""

import ctypes
import json
import logging
import os
import subprocess
import sys
import time
from ctypes import wintypes
from logging.handlers import RotatingFileHandler
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "qq-runtime/state"
STOP = STATE / "supervisor.stop"
MAINTENANCE = STATE / "runtime-maintenance.json"
STATUS = STATE / "supervisor-status.json"
ROLES = ("tunnel", "astrbot", "napcat")


def component(role):
    """Inspect the recorded PID without adopting an unrelated process.

    Args:
        role: One of the three workspace-managed component names.

    Returns:
        A status dictionary containing a verified PID when running.
    """
    record = STATE / (role + ".pid")
    if role == "tunnel":
        try:
            tunnel = json.loads((ROOT / "logs/auto-tunnel-status.json").read_text())
            if tunnel.get("state") != "stopped":
                pid = int(tunnel["pid"])
            else:
                pid = int(record.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, KeyError):
            try:
                pid = int(record.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                return {"state": "missing"}
    else:
        try:
            pid = int(record.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return {"state": "missing"}
    try:
        process = psutil.Process(pid)
        argv = process.cmdline()
        cwd = Path(process.cwd()).resolve()
        if len(argv) < 2:
            return {"state": "pid_conflict", "pid": pid}
        if role == "astrbot":
            owned = (
                cwd == (ROOT / "qq-runtime/astrbot").resolve()
                and argv[1] == "main.py"
                and Path(argv[0]).resolve()
                == (ROOT / "qq-runtime/astrbot-venv/Scripts/python.exe").resolve()
            )
        elif role == "napcat":
            owned = (
                cwd == (ROOT / "qq-runtime/napcat").resolve()
                and Path(argv[1]).resolve()
                == (ROOT / "qq-runtime/napcat/index.js").resolve()
                and Path(argv[0]).resolve()
                == (ROOT / "qq-runtime/napcat/node.exe").resolve()
            )
        else:
            owned = cwd == ROOT and Path(argv[1]).resolve() == ROOT / "auto-tunnel.py"
        return {"state": "running" if owned else "pid_conflict", "pid": pid}
    except psutil.NoSuchProcess:
        return {"state": "missing"}
    except psutil.AccessDenied:
        return {"state": "unverifiable", "pid": pid}


def main():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    mutex = kernel.CreateMutexW(None, False, "Local\\OrangePiQQRuntimeSupervisor")
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle(mutex)
        return
    STATE.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("runtime-supervisor")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        STATE / "supervisor.log", maxBytes=1024 * 1024, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    attempts = {role: 0 for role in ROLES}
    retry_at = {role: 0 for role in ROLES}
    healthy_since = {role: None for role in ROLES}
    login = {}
    login_checked = 0
    logger.info("Starting current-user runtime supervisor")
    try:
        while not STOP.exists():
            now = time.time()
            pause_until = 0
            try:
                pause_until = float(json.loads(MAINTENANCE.read_text())["until"])
            except (OSError, ValueError, KeyError):
                pass
            report = {
                "pid": os.getpid(),
                "updated_at": now,
                "maintenance": now < pause_until,
                "components": {},
                "qq_login": login,
            }
            for role in ROLES:
                state = component(role)
                if state["state"] == "running":
                    if healthy_since[role] is None:
                        healthy_since[role] = now
                    elif now - healthy_since[role] >= 120:
                        attempts[role] = 0
                else:
                    healthy_since[role] = None
                if (
                    state["state"] == "missing"
                    and now >= pause_until
                    and now >= retry_at[role]
                ):
                    attempts[role] += 1
                    retry_at[role] = now + min(
                        300, 30 * 2 ** min(attempts[role] - 1, 4)
                    )
                    # Respect a deliberate tunnel stop instead of overriding it.
                    if role == "tunnel" and (ROOT / "logs/auto-tunnel.stop").exists():
                        state["state"] = "intentionally_stopped"
                    else:
                        logger.info("Starting missing owned component: %s", role)
                        try:
                            result = subprocess.run(
                                [
                                    sys.executable,
                                    str(
                                        ROOT / "experiments/qq-bridge/run-background.py"
                                    ),
                                    role,
                                ],
                                cwd=ROOT,
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                creationflags=subprocess.CREATE_NO_WINDOW,
                                timeout=15,
                                check=False,
                            )
                            state = component(role)
                            state["launch_exit_code"] = result.returncode
                        except (OSError, subprocess.TimeoutExpired):
                            state = {"state": "launch_failed"}
                state["next_retry_at"] = retry_at[role]
                report["components"][role] = state
            if now >= login_checked + 60:
                login_checked = now
                try:
                    from napcat_api import NapCat

                    client = NapCat()
                    info = client.post("/QQLogin/CheckLoginStatus")
                    if not isinstance(info, dict):
                        raise TypeError("Invalid login status response")
                    login = {
                        "checked_at": time.time(),
                        "logged_in": bool(info.get("isLogin")),
                        "core_ready": bool(info.get("coreReady")),
                        "phase": info.get("loginPhase"),
                        "needs_user_login": not bool(info.get("isLogin")),
                    }
                except (OSError, ValueError, RuntimeError, KeyError, TypeError):
                    login = {"checked_at": time.time(), "status": "unavailable"}
                # An expired login is NOT a crashed process. Leave the panel
                # available for QR/verification rather than looping restarts.
                report["qq_login"] = login
            temp = STATUS.with_suffix(".tmp")
            temp.write_text(json.dumps(report, indent=2), encoding="utf-8")
            for attempt in range(5):
                try:
                    temp.replace(STATUS)
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.05)
            for _ in range(15):
                if STOP.exists():
                    break
                time.sleep(1)
    finally:
        logger.info("Runtime supervisor stopped; component processes retained")
        kernel.CloseHandle(mutex)


if __name__ == "__main__":
    main()
