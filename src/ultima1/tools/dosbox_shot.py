# Run DOSBox with a conf, send keys ONLY to the DOSBox window, and capture its window image.
# Never uses global keyboard input or focus changes, so other windows are never affected.
# usage: python dosbox_shot.py <dosbox.exe> <conf> <out.png> [first_wait] ["wait:keys" ...]
#   keys: plain chars, \r = Enter, » « ↓ ↑ = arrow keys, ~ = pause 1s
import sys, time, subprocess, ctypes
from ctypes import wintypes
from PIL import Image

user32 = ctypes.windll.user32; gdi32 = ctypes.windll.gdi32
user32.SetProcessDPIAware()
exe, conf, out = sys.argv[1:4]
wait = float(sys.argv[4]) if len(sys.argv) > 4 else 6
keys = sys.argv[5:]
WM_KEYDOWN, WM_KEYUP, WM_CHAR = 0x100, 0x101, 0x102

import os
p = subprocess.Popen([exe, '-conf', conf, '-noconsole'], env=dict(os.environ, SDL_VIDEODRIVER='windib'))

def find_window():
    found = []
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, l):
        pid = wintypes.DWORD(); user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value == p.pid and user32.IsWindowVisible(h): found.append(h)
        return True
    user32.EnumWindows(cb, 0)
    return found[0] if found else None

def grab(path):
    h = find_window()
    if not h: print('DOSBox window not found'); return
    r = wintypes.RECT(); user32.GetClientRect(h, ctypes.byref(r))
    w, hh = r.right, r.bottom
    hdc = user32.GetDC(h); mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, hh); gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(h, mdc, 1 | 2)          # PW_CLIENTONLY | PW_RENDERFULLCONTENT
    class BIH(ctypes.Structure):
        _fields_ = [('biSize', wintypes.DWORD), ('biWidth', wintypes.LONG), ('biHeight', wintypes.LONG),
                    ('biPlanes', wintypes.WORD), ('biBitCount', wintypes.WORD), ('biCompression', wintypes.DWORD),
                    ('biSizeImage', wintypes.DWORD), ('biXPelsPerMeter', wintypes.LONG),
                    ('biYPelsPerMeter', wintypes.LONG), ('biClrUsed', wintypes.DWORD), ('biClrImportant', wintypes.DWORD)]
    bih = BIH(ctypes.sizeof(BIH), w, -hh, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * hh * 4)
    gdi32.GetDIBits(mdc, bmp, 0, hh, buf, ctypes.byref(bih), 0)
    Image.frombuffer('RGB', (w, hh), buf, 'raw', 'BGRX', 0, 1).save(path)
    gdi32.DeleteObject(bmp); gdi32.DeleteDC(mdc); user32.ReleaseDC(h, hdc)
    print('saved', path, w, hh)

VK = {'\r': 0x0D, ' ': 0x20, '»': 0x27, '«': 0x25, '↓': 0x28, '↑': 0x26, '\x1b': 0x1B}
EXT = {0x25, 0x26, 0x27, 0x28}
def send_keys(s):
    h = find_window()
    if not h: print('DOSBox window not found'); return
    for ch in s:
        if ch == '~': time.sleep(1.0); continue
        vk = VK.get(ch) or (user32.VkKeyScanW(ord(ch)) & 0xff)
        sc = user32.MapVirtualKeyW(vk, 0)
        lp = 1 | (sc << 16) | ((1 << 24) if vk in EXT else 0)
        user32.PostMessageW(h, WM_KEYDOWN, vk, lp)
        if ch not in VK: user32.PostMessageW(h, WM_CHAR, ord(ch), lp)
        time.sleep(0.08)
        user32.PostMessageW(h, WM_KEYUP, vk, lp | (3 << 30))
        time.sleep(0.12)

try:
    time.sleep(wait)
    for i, k in enumerate(keys):
        w, txt = k.split(':', 1)
        send_keys(txt.replace('\\r', '\r')); time.sleep(float(w))
        grab(out.replace('.png', f'_{i+1}.png'))
    if not keys: grab(out)
finally:
    p.kill()
