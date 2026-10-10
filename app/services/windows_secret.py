"""Windows built-in DPAPI, scoped to the current user; no extra dependency."""

import base64
import ctypes
from ctypes import wintypes


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def transform(value, protect):
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = crypt.CryptProtectData if protect else crypt.CryptUnprotectData
    function.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Blob),
    ]
    function.restype = wintypes.BOOL
    buffer = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
    original = Blob(len(value), buffer)
    result = Blob()
    if not function(ctypes.byref(original), None, None, None, None, 1, ctypes.byref(result)):
        raise OSError("Windows credential protection failed")
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(result.data)


def protect_key(key):
    return base64.b64encode(transform(key.encode("utf-8"), True)).decode("ascii")


def unprotect_key(value):
    return transform(base64.b64decode(value, validate=True), False).decode("utf-8")
