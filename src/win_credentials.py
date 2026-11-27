"""Store only origin-scoped API secrets in the signed-in user's Credential Manager."""
import ctypes
from ctypes import wintypes as wt

class Credential(ctypes.Structure):
    _fields_ = [("Flags", wt.DWORD), ("Type", wt.DWORD), ("TargetName", wt.LPWSTR),
                ("Comment", wt.LPWSTR), ("LastWritten", wt.FILETIME), ("BlobSize", wt.DWORD),
                ("Blob", ctypes.c_void_p), ("Persist", wt.DWORD), ("AttributeCount", wt.DWORD),
                ("Attributes", ctypes.c_void_p), ("TargetAlias", wt.LPWSTR), ("UserName", wt.LPWSTR)]

api = ctypes.WinDLL("advapi32", use_last_error=True)
def target(origin):
    return "CartethyiaPet/api/" + origin.lower()

def get_key(origin):
    ptr = ctypes.POINTER(Credential)()
    if not api.CredReadW(target(origin), 1, 0, ctypes.byref(ptr)):
        if ctypes.get_last_error() == 1168:
            return ""
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(ptr.contents.Blob, ptr.contents.BlobSize).decode("utf-16-le")
    finally:
        api.CredFree(ptr)

def save_key(origin, secret):
    if not secret:
        if not api.CredDeleteW(target(origin), 1, 0) and ctypes.get_last_error() != 1168:
            raise ctypes.WinError(ctypes.get_last_error())
        return
    data = secret.encode("utf-16-le")
    buf = ctypes.create_string_buffer(data)
    cred = Credential(Type=1, TargetName=target(origin), BlobSize=len(data),
                      Blob=ctypes.cast(buf, ctypes.c_void_p), Persist=2)
    if not api.CredWriteW(ctypes.byref(cred), 0):
        raise ctypes.WinError(ctypes.get_last_error())
