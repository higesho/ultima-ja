/*
 * u9probe.dll — Ultima IX のメモリリーク調査用 DLL（32ビット）
 *
 * 1. C ランタイムの _nh_malloc / free / realloc / calloc の入口を横取りし、
 *    解放されずに残っている確保を「呼び出し元（ゲーム側の3段）」ごとに数える。
 *    VirtualAlloc / VirtualFree（u9.exe の輸入表）も同じく数える。
 * 2. 前面でなくなったという通知を握りつぶし、裏でも動かし続ける。
 * 3. ゲームが前面でない間は、本物のキーボード・マウスをゲームに見せない。
 *    キーは共有メモリから差し込んだものだけを見せる。カーソルの移動・閉じ込めもしない。
 *
 * 外からの操作は共有メモリ "Local\U9PROBE_<pid>" で行う（u9_ctl.py が書く）。
 * 対象の番地は英語版 Steam/GOG の u9.exe（SHA1 be4ade04...）専用。
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <intrin.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ---- 対象の番地（英語版 u9.exe） ---- */
#define A_NH_MALLOC 0x00714E80  /* void* _nh_malloc(size_t, int)  先頭5バイト */
#define A_FREE      0x00711590  /* void free(void*)               先頭6バイト */
#define A_REALLOC   0x007163D0  /* void* realloc(void*, size_t)   先頭5バイト */
#define A_CALLOC    0x00716DE0  /* void* calloc(size_t, size_t)   先頭5バイト */
#define TEXT_LO     0x00401000
#define TEXT_HI     0x0073F000
#define CRT_LO      0x00710000  /* これより上は C ランタイム。呼び出し元としては数えない */

/* ---- 共有メモリ ---- */
typedef struct {
    volatile LONG cmd;          /* 1 = 集計を書き出す */
    volatile LONG done;         /* 書き出し回数 */
    char  path[260];            /* 書き出し先 */
    volatile LONG keep_active;  /* 1 = 裏でも動かす */
    volatile LONG hwnd;         /* 見つけたゲームのウインドウ */
    BYTE  keys[256];            /* 差し込むキー（0x80 = 押している） */
    volatile LONG mouse_x, mouse_y; /* 背後にいるときに見せるカーソル位置（スクリーン座標） */
    volatile LONG live_count, live_bytes, total_allocs, sites;
} SHARED;
static SHARED *g_sh;

/* ---- 呼び出し元の表 ---- */
#define NSITE (1 << 16)
#define DEPTH 3
typedef struct { DWORD a[DEPTH]; LONG live_count; LONG long_bytes_dummy; LONGLONG live_bytes; LONG total; LONG kind; } SITE;
static SITE *g_sites;       /* 0 番は「不明」 */
static LONG  g_nsites = 1;

/* ---- 生きている確保の表（線形探索、後ろ詰め削除） ---- */
#define NLIVE_BITS 22
#define NLIVE (1u << NLIVE_BITS)
typedef struct { DWORD ptr; DWORD size; DWORD site; } LIVE;
static LIVE *g_live;
static LONG  g_live_count; static LONGLONG g_live_bytes; static LONG g_total;
static CRITICAL_SECTION g_cs;
static __declspec(thread) int t_depth;

static DWORD hptr(DWORD p) { return (p >> 4) * 2654435761u >> (32 - NLIVE_BITS); }

static int is_call_ret(DWORD r)
{
    const BYTE *b = (const BYTE *)r;
    if (r < TEXT_LO + 8 || r >= TEXT_HI) return 0;
    if (b[-5] == 0xE8) return 1;                                  /* call rel32 */
    if (b[-6] == 0xFF && (b[-5] & 0x38) == 0x10) return 1;        /* call [disp32] など */
    if (b[-2] == 0xFF && (b[-1] & 0xF8) == 0xD0) return 1;        /* call reg */
    if (b[-3] == 0xFF && (b[-2] & 0x38) == 0x10) return 1;        /* call [reg+disp8] */
    return 0;
}

/* スタックを上へたどって、ゲーム側（C ランタイムより下）の戻り先を DEPTH 個集める */
static void capture(DWORD *out, void *start)
{
    DWORD *sp = (DWORD *)start, *end = sp + 400;
    int n = 0;
    NT_TIB *tib = (NT_TIB *)NtCurrentTeb();
    if ((void *)end > tib->StackBase) end = (DWORD *)tib->StackBase;
    for (; sp < end && n < DEPTH; sp++) {
        DWORD v = *sp;
        if (v >= TEXT_LO && v < CRT_LO && is_call_ret(v)) out[n++] = v;
    }
    while (n < DEPTH) out[n++] = 0;
}

static DWORD site_of(const DWORD *a, LONG kind)
{
    DWORD h = (a[0] * 31 + a[1] * 17 + a[2] * 7 + kind) * 2654435761u >> 16, i;
    for (i = 0; i < NSITE; i++, h = (h + 1) & (NSITE - 1)) {
        SITE *s = &g_sites[h];
        if (h == 0) continue;
        if (s->total == 0 && s->a[0] == 0 && s->a[1] == 0 && s->a[2] == 0 && s->kind == 0) {
            memcpy(s->a, a, sizeof(DWORD) * DEPTH); s->kind = kind; g_nsites++;
            return h;
        }
        if (!memcmp(s->a, a, sizeof(DWORD) * DEPTH) && s->kind == kind) return h;
    }
    return 0;
}

static void live_add(DWORD p, DWORD size, DWORD site)
{
    DWORD i = hptr(p);
    while (g_live[i].ptr) {
        if (g_live[i].ptr == p) break;       /* 同じ番地が残っていたら上書き */
        i = (i + 1) & (NLIVE - 1);
    }
    if (g_live[i].ptr == p) {                /* 古いものを差し引く */
        SITE *o = &g_sites[g_live[i].site]; o->live_count--; o->live_bytes -= g_live[i].size;
        g_live_count--; g_live_bytes -= g_live[i].size;
    }
    g_live[i].ptr = p; g_live[i].size = size; g_live[i].site = site;
    g_sites[site].live_count++; g_sites[site].live_bytes += size; g_sites[site].total++;
    g_live_count++; g_live_bytes += size; g_total++;
}

static void live_del(DWORD p)
{
    DWORD i = hptr(p), j, k;
    while (g_live[i].ptr && g_live[i].ptr != p) i = (i + 1) & (NLIVE - 1);
    if (!g_live[i].ptr) return;             /* 記録前の確保 */
    g_sites[g_live[i].site].live_count--; g_sites[g_live[i].site].live_bytes -= g_live[i].size;
    g_live_count--; g_live_bytes -= g_live[i].size;
    /* 後ろ詰め削除 */
    j = i;
    for (;;) {
        j = (j + 1) & (NLIVE - 1);
        if (!g_live[j].ptr) break;
        k = hptr(g_live[j].ptr);
        if ((i <= j) ? (i < k && k <= j) : (i < k || k <= j)) continue;
        g_live[i] = g_live[j]; i = j;
    }
    g_live[i].ptr = 0;
}

static void record_alloc(void *p, DWORD size, void *stack, LONG kind)
{
    DWORD a[DEPTH];
    if (!p) return;
    capture(a, stack);
    EnterCriticalSection(&g_cs);
    live_add((DWORD)p, size, site_of(a, kind));
    LeaveCriticalSection(&g_cs);
}

static void record_free(void *p)
{
    if (!p) return;
    EnterCriticalSection(&g_cs);
    live_del((DWORD)p);
    LeaveCriticalSection(&g_cs);
}

/* ---- 入口の横取り ---- */
typedef void *(__cdecl *PF_NHMALLOC)(size_t, int);
typedef void  (__cdecl *PF_FREE)(void *);
typedef void *(__cdecl *PF_REALLOC)(void *, size_t);
typedef void *(__cdecl *PF_CALLOC)(size_t, size_t);
static PF_NHMALLOC o_nh_malloc; static PF_FREE o_free; static PF_REALLOC o_realloc; static PF_CALLOC o_calloc;

static void *__cdecl h_nh_malloc(size_t n, int mode)
{
    void *p;
    t_depth++; p = o_nh_malloc(n, mode); t_depth--;
    if (!t_depth) record_alloc(p, (DWORD)n, _AddressOfReturnAddress(), 0);
    return p;
}
static void __cdecl h_free(void *p)
{
    if (!t_depth) record_free(p);
    t_depth++; o_free(p); t_depth--;
}
static void *__cdecl h_realloc(void *p, size_t n)
{
    void *q;
    t_depth++; q = o_realloc(p, n); t_depth--;
    if (!t_depth) {
        if (p && (q || n == 0)) record_free(p);
        if (q) record_alloc(q, (DWORD)n, _AddressOfReturnAddress(), 0);
    }
    return q;
}
static void *__cdecl h_calloc(size_t a, size_t b)
{
    void *p;
    t_depth++; p = o_calloc(a, b); t_depth--;
    if (!t_depth) record_alloc(p, (DWORD)(a * b), _AddressOfReturnAddress(), 0);
    return p;
}

/* 先頭 n バイト（命令の切れ目）を写した踏み台を作り、入口を jmp に書き換える */
static void *inline_hook(DWORD target, void *hook, int n)
{
    BYTE *tr = (BYTE *)VirtualAlloc(NULL, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    DWORD old; int i;
    memcpy(tr, (void *)target, n);
    tr[n] = 0xE9; *(DWORD *)(tr + n + 1) = (target + n) - ((DWORD)tr + n + 5);
    VirtualProtect((void *)target, n, PAGE_EXECUTE_READWRITE, &old);
    ((BYTE *)target)[0] = 0xE9;
    *(DWORD *)(target + 1) = (DWORD)hook - (target + 5);
    for (i = 5; i < n; i++) ((BYTE *)target)[i] = 0x90;
    VirtualProtect((void *)target, n, old, &old);
    FlushInstructionCache(GetCurrentProcess(), (void *)target, n);
    return tr;
}

/* ---- 輸入表の書き換え ---- */
static void *iat_hook(const char *dll, const char *name, void *hook)
{
    BYTE *base = (BYTE *)GetModuleHandleA(NULL);
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    IMAGE_IMPORT_DESCRIPTOR *d = (IMAGE_IMPORT_DESCRIPTOR *)(base + nt->OptionalHeader.DataDirectory[1].VirtualAddress);
    for (; d->Name; d++) {
        IMAGE_THUNK_DATA *on, *ft;
        if (_stricmp((char *)(base + d->Name), dll)) continue;
        on = (IMAGE_THUNK_DATA *)(base + d->OriginalFirstThunk);
        ft = (IMAGE_THUNK_DATA *)(base + d->FirstThunk);
        for (; on->u1.AddressOfData; on++, ft++) {
            if (on->u1.Ordinal & IMAGE_ORDINAL_FLAG) continue;
            if (!strcmp((char *)((IMAGE_IMPORT_BY_NAME *)(base + on->u1.AddressOfData))->Name, name)) {
                DWORD old; void *orig = (void *)ft->u1.Function;
                VirtualProtect(&ft->u1.Function, 4, PAGE_READWRITE, &old);
                ft->u1.Function = (DWORD)hook;
                VirtualProtect(&ft->u1.Function, 4, old, &old);
                return orig;
            }
        }
    }
    return NULL;
}

/* VirtualAlloc / VirtualFree */
typedef LPVOID (WINAPI *PF_VA)(LPVOID, SIZE_T, DWORD, DWORD);
typedef BOOL   (WINAPI *PF_VF)(LPVOID, SIZE_T, DWORD);
static PF_VA o_va; static PF_VF o_vf;
static LPVOID WINAPI h_va(LPVOID a, SIZE_T s, DWORD t, DWORD p)
{
    LPVOID r = o_va(a, s, t, p);
    if (r && !a && (t & MEM_RESERVE)) record_alloc(r, (DWORD)s, _AddressOfReturnAddress(), 1);
    return r;
}
static BOOL WINAPI h_vf(LPVOID a, SIZE_T s, DWORD t)
{
    if (t & MEM_RELEASE) record_free(a);
    return o_vf(a, s, t);
}

/* ---- 裏で動かすための仕掛け ---- */
static HWND g_hwnd; static WNDPROC g_oldproc;
static int game_is_front(void) { return g_hwnd && GetForegroundWindow() == g_hwnd; }

static LRESULT CALLBACK h_wndproc(HWND h, UINT m, WPARAM w, LPARAM l)
{
    if (g_sh && g_sh->keep_active) {
        if (m == WM_ACTIVATEAPP && !w) return 0;
        if (m == WM_ACTIVATE && LOWORD(w) == WA_INACTIVE) return 0;
        if (m == WM_KILLFOCUS) return 0;
        if (m == WM_SYSCOMMAND && (w & 0xFFF0) == SC_MINIMIZE) return 0;
    }
    return CallWindowProcA(g_oldproc, h, m, w, l);
}

typedef SHORT (WINAPI *PF_GAKS)(int);
typedef BOOL  (WINAPI *PF_GKBS)(PBYTE);
typedef BOOL  (WINAPI *PF_GCP)(LPPOINT);
typedef BOOL  (WINAPI *PF_SCP)(int, int);
typedef BOOL  (WINAPI *PF_CC)(const RECT *);
static PF_GAKS o_gaks, o_gks; static PF_GKBS o_gkbs; static PF_GCP o_gcp; static PF_SCP o_scp; static PF_CC o_cc;

static SHORT WINAPI h_gaks(int vk)
{
    SHORT r = game_is_front() ? o_gaks(vk) : 0;
    if (g_sh && (vk & 0xFF) < 256 && (g_sh->keys[vk & 0xFF] & 0x80)) r |= (SHORT)0x8000;
    return r;
}
static SHORT WINAPI h_gks(int vk)
{
    SHORT r = game_is_front() ? o_gks(vk) : 0;
    if (g_sh && (g_sh->keys[vk & 0xFF] & 0x80)) r |= (SHORT)0x8000;
    return r;
}
static BOOL WINAPI h_gkbs(PBYTE k)
{
    BOOL r = o_gkbs(k); int i;
    if (!game_is_front()) memset(k, 0, 256);
    if (g_sh) for (i = 0; i < 256; i++) k[i] |= g_sh->keys[i] & 0x80;
    return r;
}
static BOOL WINAPI h_gcp(LPPOINT p)
{
    if (!g_sh) return o_gcp(p);
    if (game_is_front()) {           /* 前面のときの本物の位置を覚えておく */
        BOOL r = o_gcp(p);
        if (r) { g_sh->mouse_x = p->x; g_sh->mouse_y = p->y; }
        return r;
    }
    p->x = g_sh->mouse_x; p->y = g_sh->mouse_y; return TRUE;
}
static BOOL WINAPI h_scp(int x, int y)
{
    if (game_is_front()) return o_scp(x, y);
    if (g_sh) { g_sh->mouse_x = x; g_sh->mouse_y = y; }
    return TRUE;
}
static BOOL WINAPI h_cc(const RECT *r)
{
    if (game_is_front() || !r) return o_cc(r);
    return TRUE;                     /* 背後にいる間はカーソルを閉じ込めない */
}

/* ---- 書き出し ---- */
static int cmp_site(const void *a, const void *b)
{
    LONGLONG x = g_sites[*(const DWORD *)a].live_bytes, y = g_sites[*(const DWORD *)b].live_bytes;
    return x < y ? 1 : x > y ? -1 : 0;
}
static void dump(const char *path)
{
    static DWORD idx[NSITE];
    DWORD n = 0, i; FILE *f;
    EnterCriticalSection(&g_cs);
    for (i = 0; i < NSITE; i++) if (g_sites[i].total) idx[n++] = i;
    qsort(idx, n, sizeof(DWORD), cmp_site);
    f = fopen(path, "w");
    if (f) {
        fprintf(f, "# live_count %ld live_bytes %lld total %ld sites %lu\n", g_live_count, g_live_bytes, g_total, n);
        fprintf(f, "# site kind live_count live_bytes total a0 a1 a2\n");
        for (i = 0; i < n; i++) {
            SITE *s = &g_sites[idx[i]];
            fprintf(f, "%lu %ld %ld %lld %ld %08lx %08lx %08lx\n", idx[i], s->kind, s->live_count, s->live_bytes, s->total, s->a[0], s->a[1], s->a[2]);
        }
        fclose(f);
    }
    LeaveCriticalSection(&g_cs);
}

static BOOL CALLBACK find_cb(HWND h, LPARAM l)
{
    DWORD pid; char t[64];
    GetWindowThreadProcessId(h, &pid);
    if (pid == GetCurrentProcessId() && IsWindowVisible(h) && GetWindowTextA(h, t, sizeof t) && strstr(t, "Ultima")) {
        *(HWND *)l = h; return FALSE;
    }
    return TRUE;
}

static DWORD WINAPI worker(LPVOID unused)
{
    for (;;) {
        Sleep(100);
        if (!g_hwnd) {
            HWND h = NULL;
            EnumWindows(find_cb, (LPARAM)&h);
            if (h) {
                RECT rc; POINT c;
                GetClientRect(h, &rc); c.x = rc.right / 2; c.y = rc.bottom / 2;
                ClientToScreen(h, &c);
                g_sh->mouse_x = c.x; g_sh->mouse_y = c.y;   /* 最初はウインドウの真ん中 */
                g_hwnd = h; g_sh->hwnd = (LONG)h;
                g_oldproc = (WNDPROC)SetWindowLongA(h, GWL_WNDPROC, (LONG)h_wndproc);
            }
        }
        g_sh->live_count = g_live_count; g_sh->live_bytes = (LONG)(g_live_bytes >> 10); /* KB */
        g_sh->total_allocs = g_total; g_sh->sites = g_nsites;
        if (g_sh->cmd == 1) { dump(g_sh->path); g_sh->cmd = 0; InterlockedIncrement(&g_sh->done); }
    }
    return 0;
}

static void install(void)
{
    char name[64]; HANDLE m;
    InitializeCriticalSection(&g_cs);
    g_sites = (SITE *)VirtualAlloc(NULL, sizeof(SITE) * NSITE, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    g_live = (LIVE *)VirtualAlloc(NULL, sizeof(LIVE) * NLIVE, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    sprintf(name, "Local\\U9PROBE_%lu", GetCurrentProcessId());
    m = CreateFileMappingA(INVALID_HANDLE_VALUE, NULL, PAGE_READWRITE, 0, sizeof(SHARED), name);
    g_sh = (SHARED *)MapViewOfFile(m, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(SHARED));
    g_sh->keep_active = 1;
    /* 先頭の命令が想定どおりか確かめてから書き換える */
    if (!memcmp((void *)A_NH_MALLOC, "\x56\x8b\x74\x24\x08", 5) && !memcmp((void *)A_FREE, "\x51\x56\x8b\x74\x24\x0c", 6) &&
        !memcmp((void *)A_REALLOC, "\x83\xec\x08\x53\x55", 5) && !memcmp((void *)A_CALLOC, "\x53\x8b\x5c\x24\x0c", 5)) {
        o_nh_malloc = (PF_NHMALLOC)inline_hook(A_NH_MALLOC, h_nh_malloc, 5);
        o_free = (PF_FREE)inline_hook(A_FREE, h_free, 6);
        o_realloc = (PF_REALLOC)inline_hook(A_REALLOC, h_realloc, 5);
        o_calloc = (PF_CALLOC)inline_hook(A_CALLOC, h_calloc, 5);
    } else {
        OutputDebugStringA("u9probe: u9.exe が想定と違うので確保の記録はしません\n");
    }
    o_va = (PF_VA)iat_hook("KERNEL32.dll", "VirtualAlloc", h_va);
    o_vf = (PF_VF)iat_hook("KERNEL32.dll", "VirtualFree", h_vf);
    o_gaks = (PF_GAKS)iat_hook("USER32.dll", "GetAsyncKeyState", h_gaks);
    o_gks = (PF_GAKS)iat_hook("USER32.dll", "GetKeyState", h_gks);
    o_gkbs = (PF_GKBS)iat_hook("USER32.dll", "GetKeyboardState", h_gkbs);
    o_gcp = (PF_GCP)iat_hook("USER32.dll", "GetCursorPos", h_gcp);
    o_scp = (PF_SCP)iat_hook("USER32.dll", "SetCursorPos", h_scp);
    o_cc = (PF_CC)iat_hook("USER32.dll", "ClipCursor", h_cc);
    CreateThread(NULL, 0, worker, NULL, 0, NULL);
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD r, LPVOID p)
{
    if (r == DLL_PROCESS_ATTACH) { DisableThreadLibraryCalls(h); install(); }
    return TRUE;
}
