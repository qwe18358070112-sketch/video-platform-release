from __future__ import annotations

import ctypes
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import win32api
import win32con
import win32security


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SECURITY_MANDATORY_LOW_RID = 0x1000
SECURITY_MANDATORY_MEDIUM_RID = 0x2000
SECURITY_MANDATORY_HIGH_RID = 0x3000
SECURITY_MANDATORY_SYSTEM_RID = 0x4000


@dataclass(frozen=True)
class IntegrityLevel:
    rid: int
    label: str


def current_integrity_level() -> IntegrityLevel:
    return integrity_level_for_pid(win32api.GetCurrentProcessId())


def integrity_level_for_pid(process_id: int) -> IntegrityLevel:
    handle = win32api.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
    try:
        token = win32security.OpenProcessToken(handle, win32con.TOKEN_QUERY)
        try:
            sid, _attributes = win32security.GetTokenInformation(token, win32security.TokenIntegrityLevel)
        finally:
            win32api.CloseHandle(token)
    finally:
        win32api.CloseHandle(handle)

    subauth_count = sid.GetSubAuthorityCount()
    rid = int(sid.GetSubAuthority(subauth_count - 1))
    return IntegrityLevel(rid=rid, label=_label_for_integrity_rid(rid))


def is_running_as_admin() -> bool:
    try:
        return bool(win32security.CheckTokenMembership(None, win32security.CreateWellKnownSid(win32security.WinBuiltinAdministratorsSid, None)))
    except Exception:
        return False


def relaunch_as_admin(argv: list[str], cwd: str | Path) -> bool:
    params = subprocess.list2cmdline(argv)
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        sys.executable,
        params,
        str(Path(cwd).resolve()),
        win32con.SW_SHOWNORMAL,
    )
    return int(result) > 32


def _label_for_integrity_rid(rid: int) -> str:
    if rid >= SECURITY_MANDATORY_SYSTEM_RID:
        return "system"
    if rid >= SECURITY_MANDATORY_HIGH_RID:
        return "high"
    if rid >= SECURITY_MANDATORY_MEDIUM_RID:
        return "medium"
    if rid >= SECURITY_MANDATORY_LOW_RID:
        return "low"
    return "unknown"
