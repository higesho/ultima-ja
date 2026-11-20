# -*- coding: utf-8 -*-
"""Ultima IX を起動したままにして、キー送信・撮影・メモリ計測を行う道具。
前面のウインドウは使わない。起動したプロセスの番号でウインドウを探し、
タイトルも確かめて、そのウインドウにだけ送る・撮る。

使い方:
  python u9_ctl.py start                     起動（前面に出さないように頼む）
  python u9_ctl.py title                     プロセス番号とウインドウタイトルを表示
  python u9_ctl.py shot <画像.png>           撮影
  python u9_ctl.py keys "<キー>" [待ち秒] [画像.png]   キーを送る
  python u9_ctl.py hold <キー> <秒>          キーを押しっぱなしにする（歩くなど）
  python u9_ctl.py click <x> <y> [待ち秒] [画像.png]
  python u9_ctl.py mem                       メモリを1回測る
  python u9_ctl.py watch <秒> <間隔秒> <記録.csv>   メモリを測り続ける
  python u9_ctl.py stop                      終了
キーの書き方: 普通の文字、\\r = Enter、\\e = Esc、» « ↓ ↑ = 矢印、~ = 1秒待つ
"""
import sys, os, time, subprocess, ctypes, json, csv
from ctypes import wintypes

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi
user32.SetProcessDPIAware()
sys.stdout.reconfigure(encoding='utf-8')
HOME = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
GAME = os.environ.get('U9_GAME') or HOME     # 別のフォルダ（試験用の写しなど）で動かすときは U9_GAME で指す
TEST = os.path.join(HOME, 'jp_work', 'test')
STATE = os.path.join(TEST, 'u9_ctl.json')
EXE = os.environ.get('U9_EXE') or os.path.join(GAME, 'u9.exe')
WM_KEYDOWN, WM_KEYUP, WM_CHAR = 0x100, 0x101, 0x102


def title_of(h):
    n = user32.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(h, b, n + 1)
    return b.value


def windows_of(pid):
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, l):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(h):
            found.append((h, title_of(h)))
        return True
    user32.EnumWindows(cb, 0)
    return found


def find_window(pid):
    # タイトルに「Ultima」が入っている、そのプロセスの見えているウインドウだけを使う
    for h, t in windows_of(pid):
        if 'Ultima' in t:
            return h
    return None


def grab(h, path):
    from PIL import Image
    r = wintypes.RECT()
    user32.GetClientRect(h, ctypes.byref(r))
    w, hh = r.right, r.bottom
    hdc = user32.GetDC(h)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, hh)
    gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(h, mdc, 1 | 2)          # クライアント部分だけ、DirectX の中身も含める

    class BIH(ctypes.Structure):
        _fields_ = [('biSize', wintypes.DWORD), ('biWidth', wintypes.LONG), ('biHeight', wintypes.LONG),
                    ('biPlanes', wintypes.WORD), ('biBitCount', wintypes.WORD), ('biCompression', wintypes.DWORD),
                    ('biSizeImage', wintypes.DWORD), ('biXPelsPerMeter', wintypes.LONG),
                    ('biYPelsPerMeter', wintypes.LONG), ('biClrUsed', wintypes.DWORD), ('biClrImportant', wintypes.DWORD)]
    bih = BIH(ctypes.sizeof(BIH), w, -hh, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * hh * 4)
    gdi32.GetDIBits(mdc, bmp, 0, hh, buf, ctypes.byref(bih), 0)
    Image.frombuffer('RGB', (w, hh), buf, 'raw', 'BGRX', 0, 1).save(path)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(h, hdc)
    print('撮影', path, '(%s, %dx%d)' % (title_of(h), w, hh))


VK = {'\r': 0x0D, ' ': 0x20, '»': 0x27, '«': 0x25, '↓': 0x28, '↑': 0x26, '\x1b': 0x1B}
EXT = {0x25, 0x26, 0x27, 0x28}


def key_lp(vk, up=False):
    sc = user32.MapVirtualKeyW(vk, 0)
    lp = 1 | (sc << 16) | ((1 << 24) if vk in EXT else 0)
    return lp | (3 << 30) if up else lp


def send_keys(h, s, gap=0.4):
    for ch in s:
        if ch == '~':
            time.sleep(1.0)
            continue
        vk = VK.get(ch) or (user32.VkKeyScanW(ord(ch)) & 0xff)
        user32.PostMessageW(h, WM_KEYDOWN, vk, key_lp(vk))
        if ch not in VK:
            user32.PostMessageW(h, WM_CHAR, ord(ch), key_lp(vk))
        time.sleep(0.08)
        user32.PostMessageW(h, WM_KEYUP, vk, key_lp(vk, True))
        time.sleep(gap)


# ---- メモリ計測 ----
class PMC(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t),
                ('PrivateUsage', ctypes.c_size_t)]


class MBI(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_uint64), ('AllocationBase', ctypes.c_uint64),
                ('AllocationProtect', wintypes.DWORD), ('PartitionId', wintypes.WORD),
                ('RegionSize', ctypes.c_uint64), ('State', wintypes.DWORD),
                ('Protect', wintypes.DWORD), ('Type', wintypes.DWORD)]


kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_uint64, ctypes.POINTER(MBI), ctypes.c_size_t]
kernel32.VirtualQueryEx.restype = ctypes.c_size_t
psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]


def measure(pid):
    """私用メモリ・作業セット・32ビットの番地空間の使い方（確保済み＋予約）を MB で返す"""
    hp = kernel32.OpenProcess(0x0400 | 0x0010, False, pid)   # QUERY_INFORMATION | VM_READ
    if not hp:
        return None
    try:
        pmc = PMC(); pmc.cb = ctypes.sizeof(PMC)
        psapi.GetProcessMemoryInfo(hp, ctypes.byref(pmc), pmc.cb)
        addr, commit, reserve, largest_free = 0, 0, 0, 0
        m = MBI()
        # LAA なしの32ビットなので、使えるのは 0x80000000 までの 2GB
        while addr < 0x80000000 and kernel32.VirtualQueryEx(hp, addr, ctypes.byref(m), ctypes.sizeof(m)):
            # 2GB の境目をまたぐ領域（WoW64 の予約）は境目までだけ数える
            size = min(m.BaseAddress + m.RegionSize, 0x80000000) - m.BaseAddress
            if m.State == 0x1000:
                commit += size
            elif m.State == 0x2000:
                reserve += size
            elif m.State == 0x10000 and addr < 0x80000000:
                largest_free = max(largest_free, m.RegionSize)
            addr = m.BaseAddress + m.RegionSize
        mb = 1 / (1024 * 1024)
        return dict(private=round(pmc.PrivateUsage * mb, 1), working=round(pmc.WorkingSetSize * mb, 1),
                    commit=round(commit * mb, 1), reserve=round(reserve * mb, 1),
                    used_va=round((commit + reserve) * mb, 1), largest_free=round(largest_free * mb, 1))
    finally:
        kernel32.CloseHandle(hp)


# ---- u9probe.dll との共有メモリ（u9probe.c の SHARED と同じ並び） ----
PROBE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'probe')
OFF_CMD, OFF_DONE, OFF_PATH, OFF_KEEP, OFF_HWND, OFF_KEYS = 0, 4, 8, 268, 272, 276
OFF_MX, OFF_MY, OFF_STAT = 532, 536, 540
SH_SIZE = 556
VKNAME = {'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27, 'shift': 0x10, 'ctrl': 0x11,
          'alt': 0x12, 'space': 0x20, 'enter': 0x0D, 'esc': 0x1B, 'tab': 0x09}


def shared(pid):
    import mmap
    return mmap.mmap(-1, SH_SIZE, tagname='Local\\U9PROBE_%d' % pid)


def vk_of(name):
    if name.lower() in VKNAME:
        return VKNAME[name.lower()]
    if len(name) == 1:
        return user32.VkKeyScanW(ord(name)) & 0xff
    return int(name, 0)


def probe_stat(pid):
    import struct
    sh = shared(pid)
    c, kb, tot, sites = struct.unpack_from('<iiii', sh, OFF_STAT)
    hw = struct.unpack_from('<i', sh, OFF_HWND)[0]
    return dict(live_count=c, live_mb=round(kb / 1024, 1), total_allocs=tot, sites=sites, hwnd=hw)


def probe_dump(pid, path, timeout=20):
    import struct
    sh = shared(pid)
    done = struct.unpack_from('<i', sh, OFF_DONE)[0]
    p = os.path.abspath(path).encode('mbcs') + b'\0'
    sh[OFF_PATH:OFF_PATH + len(p)] = p
    struct.pack_into('<i', sh, OFF_CMD, 1)
    end = time.time() + timeout
    while time.time() < end:
        if struct.unpack_from('<i', sh, OFF_DONE)[0] != done:
            return True
        time.sleep(0.2)
    return False


def probe_hold(pid, names, sec):
    """差し込みキーを sec 秒押しっぱなしにする（ゲームが前面でなくても効く）"""
    # ゲームはキーの押し下げ・離しの通知も見るので、両方を送る
    sh = shared(pid)
    h = find_window(pid)
    vks = [vk_of(n) for n in names]
    for v in vks:
        sh[OFF_KEYS + v] = 0x80
        user32.PostMessageW(h, WM_KEYDOWN, v, key_lp(v))
    end = time.time() + sec
    while time.time() < end:
        for v in vks:
            user32.PostMessageW(h, WM_KEYDOWN, v, key_lp(v) | (1 << 30))
        time.sleep(0.05)
    for v in reversed(vks):
        sh[OFF_KEYS + v] = 0
        user32.PostMessageW(h, WM_KEYUP, v, key_lp(v, True))


def load():
    st = json.load(open(STATE))
    h = find_window(st['pid'])
    if not h:
        sys.exit('Ultima IX のウインドウが見つかりません（pid %d、終了している可能性があります）' % st['pid'])
    return st, h


if __name__ == '__main__':
    os.makedirs(TEST, exist_ok=True)
    cmd = sys.argv[1]
    if cmd == 'start':
        si = subprocess.STARTUPINFO()
        si.dwFlags = 1                     # STARTF_USESHOWWINDOW
        si.wShowWindow = 4                 # SW_SHOWNOACTIVATE（前面に出さないよう頼む）
        p = subprocess.Popen([EXE], cwd=GAME, startupinfo=si)
        json.dump({'pid': p.pid, 'start': time.time()}, open(STATE, 'w'))
        h = None
        for _ in range(150):
            time.sleep(0.2)
            h = find_window(p.pid)
            if h:
                break
        print('起動しました pid', p.pid, 'ウインドウ', windows_of(p.pid))
    elif cmd == 'pstart':
        # 調査用 DLL を読み込ませて起動する
        r = subprocess.run([os.path.join(PROBE, 'u9run.exe'), GAME, os.path.join(PROBE, 'u9probe.dll'),
                            os.path.basename(EXE)], capture_output=True, text=True)
        if r.returncode:
            sys.exit('起動に失敗しました: ' + r.stderr)
        pid = int(r.stdout.strip())
        json.dump({'pid': pid, 'start': time.time(), 'probe': True}, open(STATE, 'w'))
        for _ in range(150):
            time.sleep(0.2)
            if find_window(pid):
                break
        print('起動しました（調査用 DLL 入り） pid', pid, 'ウインドウ', windows_of(pid))
    elif cmd == 'pkey':
        # python u9_ctl.py pkey up+shift 3   差し込みキーを3秒押す
        st = json.load(open(STATE))
        probe_hold(st['pid'], sys.argv[2].split('+'), float(sys.argv[3]))
    elif cmd == 'pstat':
        st = json.load(open(STATE))
        print(probe_stat(st['pid']), measure(st['pid']))
    elif cmd == 'dump':
        st = json.load(open(STATE))
        print('書き出しました' if probe_dump(st['pid'], sys.argv[2]) else '書き出しが返ってきません', sys.argv[2])
    elif cmd == 'record':
        # python u9_ctl.py record <名前> <間隔分>   ゲームが終わるまで、間隔ごとに集計とメモリを記録する
        st = json.load(open(STATE)); pid = st['pid']
        name, step = sys.argv[2], float(sys.argv[3]) * 60
        d = os.path.join(TEST, name); os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'mem.csv'), 'a', newline='') as f:
            w = csv.writer(f)
            w.writerow(['番号', '経過秒', 'private', 'working', 'commit', 'reserve', 'used_va', 'largest_free', '記録件数', '記録MB'])
            i = 0
            while True:
                m = measure(pid)
                if m is None:
                    print('ゲームが終了しました'); break
                path = os.path.join(d, 'dump_%03d.txt' % i)
                probe_dump(pid, path)
                s = probe_stat(pid)
                w.writerow([i, round(time.time() - st['start'])] + list(m.values()) + [s['live_count'], s['live_mb']]); f.flush()
                print(time.strftime('%H:%M'), i, m, s['live_mb'], flush=True)
                i += 1
                time.sleep(step)
    elif cmd == 'title':
        st = json.load(open(STATE))
        print('pid', st['pid'], windows_of(st['pid']))
    elif cmd == 'shot':
        st, h = load()
        grab(h, sys.argv[2])
    elif cmd == 'keys':
        st, h = load()
        keys = sys.argv[2].replace('\\r', '\r').replace('\\e', '\x1b')
        wait = float(sys.argv[3]) if len(sys.argv) > 3 else 1.5
        send_keys(h, keys)
        time.sleep(wait)
        if len(sys.argv) > 4:
            grab(h, sys.argv[4])
    elif cmd == 'hold':
        st, h = load()
        ch, sec = sys.argv[2], float(sys.argv[3])
        vk = VK.get(ch) or (user32.VkKeyScanW(ord(ch)) & 0xff)
        end = time.time() + sec
        while time.time() < end:           # 押しっぱなしの自動連打を真似る
            user32.PostMessageW(h, WM_KEYDOWN, vk, key_lp(vk) | (1 << 30))
            time.sleep(0.05)
        user32.PostMessageW(h, WM_KEYUP, vk, key_lp(vk, True))
    elif cmd == 'click':
        st, h = load()
        x, y = int(sys.argv[2]), int(sys.argv[3])
        lp = (y << 16) | (x & 0xFFFF)
        user32.PostMessageW(h, 0x200, 0, lp)
        time.sleep(0.2)
        user32.PostMessageW(h, 0x201, 1, lp)
        time.sleep(0.1)
        user32.PostMessageW(h, 0x202, 0, lp)
        time.sleep(float(sys.argv[4]) if len(sys.argv) > 4 else 1.5)
        if len(sys.argv) > 5:
            grab(h, sys.argv[5])
    elif cmd == 'mem':
        st = json.load(open(STATE))
        print(measure(st['pid']))
    elif cmd == 'watch':
        st = json.load(open(STATE))
        total, step, out = float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
        new = not os.path.exists(out)
        with open(out, 'a', newline='') as f:
            w = csv.writer(f)
            if new:
                w.writerow(['経過秒', 'private', 'working', 'commit', 'reserve', 'used_va', 'largest_free'])
            end = time.time() + total
            while time.time() < end:
                m = measure(st['pid'])
                if m is None:
                    print('プロセスが終了しました'); break
                w.writerow([round(time.time() - st['start'])] + list(m.values())); f.flush()
                time.sleep(step)
        print('記録しました', out)
    elif cmd == 'stop':
        st = json.load(open(STATE))
        subprocess.run(['taskkill', '/PID', str(st['pid']), '/F'], capture_output=True)
        print('終了しました')
