# DOSBox の窓（だけ）に、大きさを変える知らせを送る試験の道具
#   python wintest.py drag <幅> <高さ>   人がふちをドラッグしたときと同じ順番で大きさを変える
#   python wintest.py set <幅> <高さ>    プログラムから大きさを変える（SDL がするのと同じ）
#   python wintest.py max | restore       最大化・元に戻す
#   python wintest.py size                いまの、窓の中の大きさ
import sys, os, json, ctypes
from ctypes import wintypes

u = ctypes.windll.user32
u.SetProcessDPIAware()
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'test', 'dosbox_ctl.json')
pid = json.load(open(STATE))['pid']
found = []


@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def cb(h, l):
    p = wintypes.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(p))
    if p.value == pid and u.IsWindowVisible(h): found.append(h)
    return True


u.EnumWindows(cb, 0)
h = found[0]
WM_ENTERSIZEMOVE, WM_EXITSIZEMOVE, WM_SYSCOMMAND = 0x231, 0x232, 0x112
SWP = 0x0002 | 0x0004 | 0x0010   # NOMOVE | NOZORDER | NOACTIVATE


def client():
    r = wintypes.RECT(); u.GetClientRect(h, ctypes.byref(r)); return r.right, r.bottom


def outer_for(w, hh):
    r = wintypes.RECT(0, 0, w, hh)
    u.AdjustWindowRectEx(ctypes.byref(r), u.GetWindowLongW(h, -16), False, u.GetWindowLongW(h, -20))
    return r.right - r.left, r.bottom - r.top


cmd = sys.argv[1]
if cmd == 'drag':
    w, hh = outer_for(int(sys.argv[2]), int(sys.argv[3]))
    u.SendMessageW(h, WM_ENTERSIZEMOVE, 0, 0)
    u.SetWindowPos(h, 0, 0, 0, w, hh, SWP)
    u.SendMessageW(h, WM_EXITSIZEMOVE, 0, 0)
elif cmd == 'set':
    w, hh = outer_for(int(sys.argv[2]), int(sys.argv[3]))
    u.SetWindowPos(h, 0, 0, 0, w, hh, SWP)
elif cmd == 'altenter':
    import time
    sc_alt, sc_ret = u.MapVirtualKeyW(0x12, 0), u.MapVirtualKeyW(0x0D, 0)
    u.PostMessageW(h, 0x104, 0x12, 1 | (sc_alt << 16) | (1 << 29))
    time.sleep(0.05)
    u.PostMessageW(h, 0x104, 0x0D, 1 | (sc_ret << 16) | (1 << 29))
    time.sleep(0.05)
    u.PostMessageW(h, 0x105, 0x0D, 1 | (sc_ret << 16) | (1 << 29) | (3 << 30))
    time.sleep(0.05)
    u.PostMessageW(h, 0x101, 0x12, 1 | (sc_alt << 16) | (3 << 30))
    time.sleep(1.5)
elif cmd == 'max':
    u.SendMessageW(h, WM_SYSCOMMAND, 0xF030, 0)
elif cmd == 'restore':
    u.SendMessageW(h, WM_SYSCOMMAND, 0xF120, 0)
print('窓の中の大きさ', client())
