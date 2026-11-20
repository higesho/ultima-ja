# DOSBox を起動したままにして、キー送信と画面撮影を何回でも行うための道具
# キーは DOSBox のウィンドウにだけ送る（ほかのウィンドウには一切送らない）
#
# ほかの作品の DOSBox が同時に動いていても取り違えないよう、ウィンドウはタイトルで指定する。
#   DOSBox 0.74 のタイトルは「DOSBox 0.74-2.1, Cpu speed: 3004 cycles, ... Program: AVATAR」の形で、
#   タイトルを自由に決める設定はない。そこで conf の cycles を他と重ならない値（U4 は 3004）にして、
#   タイトルの「3004 cycles」を目印にする。目印があり、しかも自分が起動したプロセスのウィンドウだけを相手にする。
#   前面のウィンドウは見ない。合うウィンドウが無い・2つ以上あるときは、何も送らずに止まる。
#
# 使い方:
#   python dosbox_ctl.py start <dosbox.exe> <conf>      起動して番号と目印をファイルに記録
#   python dosbox_ctl.py keys "<キー>" [待ち秒] [画像.png] キーを送り、待ってから撮影
#   python dosbox_ctl.py shot <画像.png>                 撮影だけ
#   python dosbox_ctl.py list                            DOSBox のウィンドウの一覧（確認用）
#   python dosbox_ctl.py stop                            終了
# キーの書き方: 普通の文字、\r = Enter、» « ↓ ↑ = 矢印キー、~ = 1秒待つ
import sys, os, re, time, subprocess, ctypes, json
from ctypes import wintypes
from PIL import Image

user32 = ctypes.windll.user32; gdi32 = ctypes.windll.gdi32; kernel32 = ctypes.windll.kernel32
user32.SetProcessDPIAware()
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'test', 'dosbox_ctl.json')
WM_KEYDOWN, WM_KEYUP, WM_CHAR = 0x100, 0x101, 0x102

def window_title(h):
    n = user32.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(h, b, n + 1)
    return b.value

def all_windows():
    """見えているウィンドウ全部: [(hwnd, pid, タイトル)]"""
    found = []
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, l):
        if user32.IsWindowVisible(h):
            p = wintypes.DWORD(); user32.GetWindowThreadProcessId(h, ctypes.byref(p))
            found.append((h, p.value, window_title(h)))
        return True
    user32.EnumWindows(cb, 0)
    return found

def title_mark(conf):
    """conf の cycles から、タイトルの目印「3004 cycles」を作る"""
    m = re.search(r'^\s*cycles\s*=\s*(\d+)\s*$', open(conf, encoding='utf-8', errors='replace').read(), re.M)
    if not m: sys.exit('conf に cycles=<数> がありません（タイトルの目印に使います）')
    return f' {m.group(1)} cycles'

def find_window(pid, mark):
    """タイトルが DOSBox で目印を含み、プロセス番号も合うウィンドウを1つだけ返す"""
    hits = [h for h, p, t in all_windows() if p == pid and t.startswith('DOSBox') and mark in t]
    if len(hits) > 1: sys.exit(f'目印「{mark.strip()}」のウィンドウが {len(hits)} 個あります。何も送りません')
    return hits[0] if hits else None

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
def send_keys(h, s, mark, gap=0.5):
    for ch in s:
        if ch == '~': time.sleep(1.0); continue
        if mark not in window_title(h):          # 1キーごとに、まだ同じウィンドウか確かめる
            sys.exit(f'ウィンドウのタイトルに目印「{mark.strip()}」がありません。送るのをやめます')
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
    h = find_window(st['pid'], st['mark'])
    if not h: sys.exit(f'目印「{st["mark"].strip()}」の DOSBox が見つかりません（終了している可能性があります）')
    return st, h

def launch(args, cwd, mark):
    flags = 0x00000008 | 0x00000200        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    others = [t for h, p, t in all_windows() if t.startswith('DOSBox') and mark in t]
    if others: sys.exit(f'目印「{mark.strip()}」の DOSBox がもう動いています: {others}')
    p = subprocess.Popen(args, cwd=cwd, creationflags=flags, env=dict(os.environ, SDL_VIDEODRIVER='windib'))
    json.dump({'pid': p.pid, 'mark': mark}, open(STATE, 'w'))
    for _ in range(50):
        time.sleep(0.2)
        if find_window(p.pid, mark): break
    print('起動しました pid', p.pid, '目印', mark.strip())

cmd = sys.argv[1]
if cmd == 'start':
    exe, conf = sys.argv[2:4]
    launch([exe, '-conf', conf, '-noconsole'], None, title_mark(conf))
elif cmd == 'startraw':
    # python dosbox_ctl.py startraw <作業フォルダ> <dosbox.exe> <引数...>   GOG と同じ起動の再現用
    # 目印は、引数の最後の -conf の cycles から作る
    cwd, exe, args = sys.argv[2], sys.argv[3], sys.argv[4:]
    confs = [args[i + 1] for i, a in enumerate(args[:-1]) if a == '-conf']
    if not confs: sys.exit('-conf がありません')
    marks = []
    for c in reversed(confs):                       # cycles が書いてある conf のうち、後から読まれるもの
        try:
            marks.append(title_mark(os.path.join(cwd, c)))
            break
        except SystemExit:
            continue
    if not marks: sys.exit('どの conf にも cycles がありません')
    launch([exe] + args, cwd, marks[0])
elif cmd == 'keys':
    st, h = load()
    keys = sys.argv[2].replace('\\r', '\r')
    wait = float(sys.argv[3]) if len(sys.argv) > 3 else 1.5
    send_keys(h, keys, st['mark'])
    time.sleep(wait)
    if len(sys.argv) > 4: grab(h, sys.argv[4])
elif cmd == 'rec':
    # 録音の開始・停止（DOSBox の Ctrl+F6。WAV は作業フォルダの capture に出る）。キーはこの窓にだけ送る
    st, h = load()
    if st['mark'] not in window_title(h): sys.exit('目印がありません。送りません')
    seq = [(WM_KEYDOWN, 0x11), (WM_KEYDOWN, 0x75), (WM_KEYUP, 0x75), (WM_KEYUP, 0x11)]
    for msg, vk in seq:
        sc = user32.MapVirtualKeyW(vk, 0)
        lp = 1 | (sc << 16) | ((3 << 30) if msg == WM_KEYUP else 0)
        user32.PostMessageW(h, msg, vk, lp)
        time.sleep(0.15)
    print('Ctrl+F6 を送りました')
elif cmd == 'shot':
    st, h = load(); grab(h, sys.argv[2])
elif cmd == 'list':
    for h, p, t in all_windows():
        if t.startswith('DOSBox'): print(p, t)
elif cmd == 'stop':
    st = json.load(open(STATE))
    subprocess.run(['taskkill', '/PID', str(st['pid']), '/F'], capture_output=True)
    print('終了しました')
