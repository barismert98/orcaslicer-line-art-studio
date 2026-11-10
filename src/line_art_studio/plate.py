"""Loads a file onto the plate through OrcaSlicer's own open-in-running-instance message.

No plugin API adds objects to the plate. On Windows, a second OrcaSlicer process hands
its files to the first with WM_COPYDATA (GUI/InstanceCheck.cpp). Sending the same message
to our own main window loads the file like a drag and drop. It is an internal route, so a
caller must fall back to telling the user where the file is.
"""
from __future__ import annotations

import sys

WM_COPYDATA = 0x004A
_MARK = "Instance_Hash_Minor"
_COPYDATA_ID = 1


def escape_command_line(args: list) -> str:
    """Same quoting as Slic3r::escape_strings_cstyle."""
    out = []
    for arg in args:
        if arg and not any(c in arg for c in ' \t;\\"\r\n'):
            out.append(arg)
            continue
        body = arg.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "\\r").replace("\n", "\\n")
        out.append(f'"{body}"')
    return ";".join(out)


def add_to_plate(path: str) -> bool:
    """True when the message was delivered; the load itself then happens on the UI queue."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    class CopyData(ctypes.Structure):
        _fields_ = [
            ("dwData", ctypes.c_size_t),
            ("cbData", wintypes.DWORD),
            ("lpData", ctypes.c_void_p),
        ]

    # A private handle, so these signatures do not affect anyone else's ctypes.windll.
    user32 = ctypes.WinDLL("user32")
    kernel32 = ctypes.WinDLL("kernel32")
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [enum_proc, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    user32.GetPropW.restype = wintypes.HANDLE
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, ctypes.c_void_p]
    user32.SendMessageW.restype = ctypes.c_ssize_t

    own_process = kernel32.GetCurrentProcessId()
    found = []

    def check(hwnd, _lparam):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == own_process and user32.GetPropW(hwnd, _MARK):
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(enum_proc(check), 0)
    if not found:
        return False

    # The handler skips the first argument, which is normally the executable.
    text = ctypes.create_unicode_buffer(escape_command_line(["orca-slicer", path]))
    data = CopyData(_COPYDATA_ID, ctypes.sizeof(text), ctypes.cast(text, ctypes.c_void_p))
    user32.SendMessageW(found[0], WM_COPYDATA, 0, ctypes.byref(data))
    return True
