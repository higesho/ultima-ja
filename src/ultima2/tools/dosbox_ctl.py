# DOSBox を起動したままにして、キー送信と画面撮影を何回でも行うための道具
# キーは DOSBox のウィンドウにだけ送る（ほかのウィンドウには一切送らない）
#
# 使い方:
#   python dosbox_ctl.py start <dosbox.exe> <conf>      起動して番号をファイルに記録
#   python dosbox_ctl.py keys "<キー>" [待ち秒] [画像.png] キーを送り、待ってから撮影
#   python dosbox_ctl.py shot <画像.png>                 撮影だけ
#   python dosbox_ctl.py stop                            終了
# キーの書き方: 普通の文字、\r = Enter、» « ↓ ↑ = 矢印キー、~ = 1秒待つ
import sys, os, time, subprocess, ctypes, json
from ctypes import wintypes
from PIL import Image

user32 = ctypes.windll.user32; gdi32 = ctypes.windll.gdi32; kernel32 = ctypes.windll.kernel32
user32.SetProcessDPIAware()
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'test', 'dosbox_ctl.json')
WM_KEYDOWN, WM_KEYUP, WM_CHAR = 0x100, 0x101, 0x102

def find_window(pid):
    found = []
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, l):
        p = wintypes.DWORD(); user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(h): found.append(h)
        return True
    user32.EnumWindows(cb, 0)
    return found[0] if found else None

def grab(h, path):
    if user32.IsIconic(h):
        user32.ShowWindow(h, 4)     # SW_SHOWNOACTIVATE: 前面に出さずに元に戻す
        time.sleep(0.5)
    for _ in range(10):
        try:
            return grab1(h, path)
        except ValueError:
            time.sleep(0.3)
    raise RuntimeError('撮影できませんでした')

def grab1(h, path):
    r = wintypes.RECT(); user32.GetClientRect(h, ctypes.byref(r))
    w, hh = r.right, r.bottom
    hdc = user32.GetDC(h); mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, hh); gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(h, mdc, 1 | 2)
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
    print('撮影', path)

VK = {'\r': 0x0D, ' ': 0x20, '»': 0x27, '«': 0x25, '↓': 0x28, '↑': 0x26, '\x1b': 0x1B}
EXT = {0x25, 0x26, 0x27, 0x28}
def send_keys(h, s, gap=0.5):
    for ch in s:
        if ch == '~': time.sleep(1.0); continue
        vk = VK.get(ch) or (user32.VkKeyScanW(ord(ch)) & 0xff)
        sc = user32.MapVirtualKeyW(vk, 0)
        lp = 1 | (sc << 16) | ((1 << 24) if vk in EXT else 0)
        user32.PostMessageW(h, WM_KEYDOWN, vk, lp)
        if ch not in VK: user32.PostMessageW(h, WM_CHAR, ord(ch), lp)
        time.sleep(0.08)
        user32.PostMessageW(h, WM_KEYUP, vk, lp | (3 << 30))
        time.sleep(gap)

def load():
    st = json.load(open(STATE))
    h = find_window(st['pid'])
    if not h: sys.exit('DOSBox が見つかりません（終了している可能性があります）')
    return st, h

cmd = sys.argv[1]
if cmd == 'start':
    exe, conf = sys.argv[2:4]
    flags = 0x00000008 | 0x00000200        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    p = subprocess.Popen([exe, '-conf', conf, '-noconsole'], creationflags=flags,
                         env=dict(os.environ, SDL_VIDEODRIVER='windib'))
    json.dump({'pid': p.pid}, open(STATE, 'w'))
    for _ in range(50):
        time.sleep(0.2)
        if find_window(p.pid): break
    print('起動しました pid', p.pid)
elif cmd == 'startraw':
    # python dosbox_ctl.py startraw <作業フォルダ> <dosbox.exe> <引数...>   GOG と同じ起動の再現用
    cwd, exe, args = sys.argv[2], sys.argv[3], sys.argv[4:]
    flags = 0x00000008 | 0x00000200
    p = subprocess.Popen([exe] + args, cwd=cwd, creationflags=flags,
                         env=dict(os.environ, SDL_VIDEODRIVER='windib'))
    json.dump({'pid': p.pid}, open(STATE, 'w'))
    for _ in range(50):
        time.sleep(0.2)
        if find_window(p.pid): break
    print('起動しました pid', p.pid)
elif cmd == 'keys':
    st, h = load()
    keys = sys.argv[2].replace('\\r', '\r')
    wait = float(sys.argv[3]) if len(sys.argv) > 3 else 1.5
    send_keys(h, keys)
    time.sleep(wait)
    if len(sys.argv) > 4: grab(h, sys.argv[4])
elif cmd == 'shot':
    st, h = load(); grab(h, sys.argv[2])
elif cmd == 'stop':
    st = json.load(open(STATE))
    subprocess.run(['taskkill', '/PID', str(st['pid']), '/F'], capture_output=True)
    print('終了しました')
