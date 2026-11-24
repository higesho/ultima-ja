/*
 * opengl32.dll の代わり（GOG 版ウルティマ I・II に付いている DOSBox 0.74 用）
 *   ※ u2\ のものは、ウルティマIIの配布物に入れている、前の形の DLL のソース。
 *      字の表 glyphs.h は、その配布物の DLL から取り出したもの（gen.py では作らない）。
 *   - 窓の大きさを、ふちをドラッグして変えられるようにする
 *   - 美咲フォント 8x8 で描かれた日本語の字を見つけて、東雲フォント 12px で描き直す（font=shinonome）
 * DOSBox は output=opengl のとき、1 枚の絵を glTexSubImage2D で送り、glCallList で描く。
 * そこで絵を受け取り、3 倍の大きさの絵を自分で作って、窓いっぱいに描く。
 * それ以外の関数は、すべて本物の opengl32.dll へそのままつなぐ。
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef unsigned int GLenum; typedef int GLint; typedef int GLsizei; typedef unsigned int GLuint;
typedef float GLfloat; typedef unsigned char GLubyte; typedef unsigned int GLbitfield; typedef float GLclampf;

#define GL_EXTENSIONS 0x1F03
#define GL_TEXTURE_2D 0x0DE1
#define GL_BGRA 0x80E1
#define GL_UNSIGNED_BYTE 0x1401
#define GL_RGBA8 0x8058
#define GL_COMPILE 0x1300
#define GL_QUADS 0x0007
#define GL_PROJECTION 0x1701
#define GL_MODELVIEW 0x1700
#define GL_TEXTURE 0x1702
#define GL_ALL_ATTRIB_BITS 0x000FFFFF
#define GL_CLIENT_ALL_ATTRIB_BITS 0xFFFFFFFF
#define GL_COLOR_BUFFER_BIT 0x4000
#define GL_TEXTURE_MIN_FILTER 0x2801
#define GL_TEXTURE_MAG_FILTER 0x2800
#define GL_TEXTURE_WRAP_S 0x2802
#define GL_TEXTURE_WRAP_T 0x2803
#define GL_NEAREST 0x2600
#define GL_LINEAR 0x2601
#define GL_CLAMP 0x2900
#define GL_TEXTURE_ENV 0x2300
#define GL_TEXTURE_ENV_MODE 0x2200
#define GL_REPLACE 0x1E01
#define GL_BLEND 0x0BE2
#define GL_DEPTH_TEST 0x0B71
#define GL_SCISSOR_TEST 0x0C11
#define GL_LIGHTING 0x0B50
#define GL_CULL_FACE 0x0B44
#define GL_ALPHA_TEST 0x0BC0
#define GL_UNPACK_ROW_LENGTH 0x0CF2
#define GL_UNPACK_ALIGNMENT 0x0CF5
#define GL_UNPACK_SKIP_ROWS 0x0CF3
#define GL_UNPACK_SKIP_PIXELS 0x0CF4

FARPROC g_real[512];
#include "exports.h"

typedef struct { unsigned __int64 key; unsigned short shn[12]; } GLYPH;
#include "glyphs.h"

#define REAL(name, ret, args) ((ret (WINAPI *) args) g_real[IX_##name])

/* ---------------------------------------------------------------- 設定と記録 */
static char g_dir[MAX_PATH], g_ini[MAX_PATH];
static int cfg_font = 1;        /* 1 = 東雲、0 = 美咲（描き直さない） */
static int cfg_aspect = 1;      /* 1 = 4:3 を保つ */
static int cfg_linear = 1;      /* 1 = なめらかに広げる */
#ifdef UJ_TEST  /* 試験版だけ: dump=1 で、受け取った絵を BMP に保存する */
static int cfg_w = 960, cfg_h = 720, cfg_remember = 1, cfg_log = 0, cfg_dump = 0, cfg_enabled = 1;
#else
static int cfg_w = 960, cfg_h = 720, cfg_remember = 1, cfg_log = 0, cfg_enabled = 1;
#endif
static FILE *g_log;

static void plog(const char *fmt, ...) {
    va_list ap;
    if (!g_log) return;
    va_start(ap, fmt); vfprintf(g_log, fmt, ap); va_end(ap);
    fputc('\n', g_log); fflush(g_log);
}

static void load_cfg(void) {
    char s[64];
    GetPrivateProfileStringA("view", "font", "shinonome", s, sizeof s, g_ini);
    cfg_font = _stricmp(s, "misaki") != 0;
    GetPrivateProfileStringA("view", "filter", "linear", s, sizeof s, g_ini);
    cfg_linear = _stricmp(s, "nearest") != 0;
    cfg_aspect = GetPrivateProfileIntA("view", "aspect", 1, g_ini);
    cfg_w = GetPrivateProfileIntA("view", "width", 960, g_ini);
    cfg_h = GetPrivateProfileIntA("view", "height", 720, g_ini);
    cfg_remember = GetPrivateProfileIntA("view", "remember", 1, g_ini);
    cfg_log = GetPrivateProfileIntA("view", "log", 0, g_ini);
#ifdef UJ_TEST
    cfg_dump = GetPrivateProfileIntA("view", "dump", 0, g_ini);
#endif
    cfg_enabled = GetPrivateProfileIntA("view", "enabled", 1, g_ini);
    if (cfg_w < 320) cfg_w = 320;
    if (cfg_h < 200) cfg_h = 200;
    if (cfg_log) {
        char p[MAX_PATH];
        sprintf(p, "%sultima_ja.log", g_dir);
        g_log = fopen(p, "w");
    }
    plog("設定: font=%s aspect=%d filter=%s size=%dx%d remember=%d enabled=%d",
         cfg_font ? "shinonome" : "misaki", cfg_aspect, cfg_linear ? "linear" : "nearest",
         cfg_w, cfg_h, cfg_remember, cfg_enabled);
}

/* ---------------------------------------------------------------- DOSBox から受け取る絵 */
static int g_texsize;               /* DOSBox のテクスチャの一辺 */
static GLuint g_list, g_rec_list;   /* DOSBox が絵を描くリスト */
static int g_rec;
static float g_rec_s, g_rec_t;
static int g_w, g_h;                /* DOSBox の絵の大きさ */
static unsigned *g_mirror;          /* 受け取った絵（BGRA） */
static int g_mir_w, g_mir_cap;
static int g_dirty;

/* 自分で作る大きい絵 */
static unsigned *g_canvas;
static int g_cw, g_ch, g_canvas_cap, g_canvas_new;
static GLuint g_tex;
static int g_tw, g_th, g_tex_linear = -1;
static char g_ext[16384];

static int pow2(int v) { int p = 64; while (p < v) p <<= 1; return p; }

const GLubyte * WINAPI hk_glGetString(GLenum name) {
    const GLubyte *r = REAL(glGetString, const GLubyte *, (GLenum))(name);
    if (name == GL_EXTENSIONS && r && cfg_enabled) {
        /* ピクセルバッファを使わせない（絵を glTexSubImage2D で、ふつうのメモリから送らせる） */
        char *p;
        strncpy(g_ext, (const char *)r, sizeof g_ext - 1);
        while ((p = strstr(g_ext, "_pixel_buffer_object")) != NULL) p[1] = 'P';
        return (const GLubyte *)g_ext;
    }
    return r;
}

void WINAPI hk_glTexImage2D(GLenum target, GLint level, GLint ifmt, GLsizei w, GLsizei h, GLint border,
                            GLenum fmt, GLenum type, const void *px) {
    if (target == GL_TEXTURE_2D && level == 0 && px == NULL && w == h) {
        g_texsize = w;
        plog("DOSBox のテクスチャ: %d", w);
    }
    REAL(glTexImage2D, void, (GLenum, GLint, GLint, GLsizei, GLsizei, GLint, GLenum, GLenum, const void *))
        (target, level, ifmt, w, h, border, fmt, type, px);
}

void WINAPI hk_glTexSubImage2D(GLenum target, GLint level, GLint x, GLint y, GLsizei w, GLsizei h,
                               GLenum fmt, GLenum type, const void *px) {
    if (target == GL_TEXTURE_2D && level == 0 && fmt == GL_BGRA && px && x == 0 && w > 0 && h > 0 &&
        w <= 4096 && y >= 0 && y + h <= 4096) {
        int need = w * (y + h > 1200 ? y + h : 1200);
        if (w != g_mir_w || need > g_mir_cap) {
            unsigned *n = (unsigned *)calloc(need, 4);
            if (n) { free(g_mirror); g_mirror = n; g_mir_cap = need; g_mir_w = w; }
        }
        if (g_mirror && w == g_mir_w) {
            memcpy(g_mirror + (size_t)y * w, px, (size_t)w * h * 4);
            g_dirty = 1;
        }
    }
    REAL(glTexSubImage2D, void, (GLenum, GLint, GLint, GLint, GLsizei, GLsizei, GLenum, GLenum, const void *))
        (target, level, x, y, w, h, fmt, type, px);
}

void WINAPI hk_glNewList(GLuint list, GLenum mode) {
    if (mode == GL_COMPILE) { g_rec = 1; g_rec_list = list; g_rec_s = g_rec_t = 0; }
    REAL(glNewList, void, (GLuint, GLenum))(list, mode);
}

void WINAPI hk_glTexCoord2f(GLfloat s, GLfloat t) {
    if (g_rec) { if (s > g_rec_s) g_rec_s = s; if (t > g_rec_t) g_rec_t = t; }
    REAL(glTexCoord2f, void, (GLfloat, GLfloat))(s, t);
}

void WINAPI hk_glEndList(void) {
    if (g_rec && g_rec_s > 0 && g_rec_t > 0 && g_texsize > 0) {
        g_list = g_rec_list;
        g_w = (int)(g_rec_s * g_texsize + 0.5f);
        g_h = (int)(g_rec_t * g_texsize + 0.5f);
        g_dirty = 1;
        plog("画面の大きさ: %dx%d", g_w, g_h);
    }
    g_rec = 0;
    REAL(glEndList, void, (void))();
}

/* ---------------------------------------------------------------- 字を描き直す */
static int glyph_find(unsigned __int64 key) {
    int lo = 0, hi = NGLYPH - 1;
    while (lo <= hi) {
        int mid = (lo + hi) >> 1;
        if (glyph_tab[mid].key == key) return mid;
        if (glyph_tab[mid].key < key) lo = mid + 1; else hi = mid - 1;
    }
    return -1;
}

/* 大きい絵の作り方。xs/ys … 元の絵の何画素が 1 マス分の 1 画素か（横に 2 倍で出る画面のため） */
typedef struct { int lw, lh, xs, ys, k, cellw, cellh, rowdbl, cols, rows; } LAYOUT;
static LAYOUT g_lay;

static int cols_doubled(void) {
    int x, y;
    for (y = 0; y < g_h; y += 7)
        for (x = 0; x + 1 < g_w; x += 2)
            if (g_mirror[y * g_mir_w + x] != g_mirror[y * g_mir_w + x + 1]) return 0;
    return 1;
}

static void make_layout(LAYOUT *L) {
    memset(L, 0, sizeof *L);
    L->xs = (g_w >= 640 && g_h <= 400 && cols_doubled()) ? 2 : 1;
    /* 縦は間引かない（400 行の画面では、絵の画面も文字の画面も「8x16 のマスに縦 2 倍の字」として見る） */
    L->ys = 1;
    L->lw = g_w / L->xs; L->lh = g_h / L->ys;
    if (L->lw <= 400 && L->lh <= 240) {               /* 320x200 などの絵の画面 */
        L->k = 3; L->cellw = 8; L->cellh = 8; L->rowdbl = 1;
    } else if (L->lw <= 400 && L->lh == 400) {        /* 40 桁の文字の画面（字は縦に 2 倍） */
        L->k = 3; L->cellw = (L->lw % 9 == 0) ? 9 : 8; L->cellh = 16; L->rowdbl = 2;
    } else {
        L->k = L->lw >= 960 ? 1 : (L->lw >= 480 ? 2 : 3);
    }
    if (L->cellw) { L->cols = L->lw / L->cellw; L->rows = L->lh / L->cellh; }
}

#define PIX(x, y) g_mirror[(size_t)((y) * L->ys) * g_mir_w + (x) * L->xs]

static void replace_cell(const LAYOUT *L, int cx, int cy) {
    int x0 = cx * L->cellw, y0 = cy * L->cellh, x, y, r, i;
    unsigned a = PIX(x0, y0), b = a, fg, bg;
    unsigned __int64 ma = 0;
    int have_b = 0, gi;
    /* 字のところ（8x8）の色は 2 色だけ */
    for (r = 0; r < 8; r++) {
        for (x = 0; x < 8; x++) {
            unsigned c = PIX(x0 + x, y0 + r * L->rowdbl);
            if (L->rowdbl == 2 && c != PIX(x0 + x, y0 + r * 2 + 1)) return;
            if (c == a) ma |= 1ULL << (63 - (r * 8 + x));
            else if (!have_b) { b = c; have_b = 1; }
            else if (c != b) return;
        }
    }
    if (!have_b) return;
    /* 9 画素目の列（文字の画面）は背景のまま */
    if (L->cellw == 9)
        for (y = 0; y < 16; y++) if (PIX(x0 + 8, y0 + y) != a && PIX(x0 + 8, y0 + y) != b) return;
    if ((gi = glyph_find(~ma)) >= 0) { fg = b; bg = a; }
    else if ((gi = glyph_find(ma)) >= 0) { fg = a; bg = b; }
    else return;
    if (L->cellw == 9) for (y = 0; y < 16; y++) if (PIX(x0 + 8, y0 + y) != bg) return;
    {
        /* 字のところ（8x8 の k 倍）を、東雲の 12x12 で塗り直す */
        int gw = 8 * L->k, gh = 8 * L->k * L->rowdbl;
        int sx = gw / 12, sy = gh / 12;
        int px0 = x0 * L->k, py0 = y0 * L->k;
        const unsigned short *s = glyph_tab[gi].shn;
        for (y = 0; y < gh; y++) {
            unsigned *row = g_canvas + (size_t)(py0 + y) * g_cw + px0;
            unsigned short bits = (y / sy < 12) ? s[y / sy] : 0;
            for (i = 0; i < gw; i++) {
                int c = i / sx;
                row[i] = (c < 12 && (bits & (0x800 >> c))) ? fg : bg;
            }
        }
    }
}

static void compose(void) {
    LAYOUT L;
    int x, y, cw, ch;
    make_layout(&L);
    cw = L.lw * L.k; ch = L.lh * L.k;
    if (memcmp(&L, &g_lay, sizeof L)) {
        plog("並べ方: 元 %dx%d → %dx%d（横 %d、縦 %d 画素ずつ）、%d 倍、マス %dx%d、%d 桁 %d 行",
             g_w, g_h, L.lw, L.lh, L.xs, L.ys, L.k, L.cellw, L.cellh, L.cols, L.rows);
        g_lay = L;
    }
    if ((size_t)cw * ch > (size_t)g_canvas_cap) {
        free(g_canvas);
        g_canvas = (unsigned *)malloc((size_t)cw * ch * 4);
        g_canvas_cap = g_canvas ? cw * ch : 0;
        if (!g_canvas) return;
    }
    g_cw = cw; g_ch = ch;
    /* まず、そのまま k 倍に広げる */
    for (y = 0; y < L.lh; y++) {
        unsigned *dst = g_canvas + (size_t)y * L.k * cw;
        const unsigned *src = g_mirror + (size_t)y * L.ys * g_mir_w;
        int j;
        for (x = 0; x < L.lw; x++) {
            unsigned c = src[x * L.xs];
            for (j = 0; j < L.k; j++) dst[x * L.k + j] = c;
        }
        for (j = 1; j < L.k; j++) memcpy(dst + (size_t)j * cw, dst, (size_t)cw * 4);
    }
    /* 次に、美咲の字のマスを東雲で描き直す */
    if (cfg_font && L.cellw)
        for (y = 0; y < L.rows; y++)
            for (x = 0; x < L.cols; x++) replace_cell(&L, x, y);
    g_canvas_new = 1;
}

#ifdef UJ_TEST  /* 試験版だけ */
static void dump_bmp(void) {
    static DWORD last;
    static int n;
    char p[MAX_PATH];
    FILE *f;
    BITMAPFILEHEADER fh; BITMAPINFOHEADER ih;
    int y;
    if (!cfg_dump || n >= 40 || GetTickCount() - last < 3000) return;
    last = GetTickCount();
    sprintf(p, "%sdump_%02d_%dx%d.bmp", g_dir, n++, g_w, g_h);
    if (!(f = fopen(p, "wb"))) return;
    memset(&fh, 0, sizeof fh); memset(&ih, 0, sizeof ih);
    fh.bfType = 0x4D42; fh.bfOffBits = sizeof fh + sizeof ih;
    fh.bfSize = fh.bfOffBits + g_w * g_h * 4;
    ih.biSize = sizeof ih; ih.biWidth = g_w; ih.biHeight = -g_h; ih.biPlanes = 1; ih.biBitCount = 32;
    fwrite(&fh, sizeof fh, 1, f); fwrite(&ih, sizeof ih, 1, f);
    for (y = 0; y < g_h; y++) fwrite(g_mirror + (size_t)y * g_mir_w, 4, g_w, f);
    fclose(f);
    plog("絵を保存: %s", p);
}
#endif

/* ---------------------------------------------------------------- 窓 */
static HWND g_wnd;
static WNDPROC g_oldproc;
static int g_sizing;              /* 人がふちを動かしている、または最大化・元に戻すの最中 */
static int g_user_w, g_user_h;    /* 人が選んだ、窓の中の大きさ */
static int g_in_draw;

static int windowed(HWND h) { return (GetWindowLongA(h, GWL_STYLE) & WS_CAPTION) == WS_CAPTION; }

static void set_client_size(HWND h, int w, int ht) {
    RECT r = { 0, 0, w, ht };
    AdjustWindowRectEx(&r, (DWORD)GetWindowLongA(h, GWL_STYLE), FALSE, (DWORD)GetWindowLongA(h, GWL_EXSTYLE));
    g_sizing++;
    SetWindowPos(h, NULL, 0, 0, r.right - r.left, r.bottom - r.top,
                 SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED);
    g_sizing--;
}

static void remember_size(HWND h) {
    RECT r;
    if (!windowed(h) || IsZoomed(h) || IsIconic(h)) return;
    GetClientRect(h, &r);
    if (r.right < 100 || r.bottom < 100) return;
    g_user_w = r.right; g_user_h = r.bottom;
}

static void save_size(void) {
    char s[32];
    if (!cfg_remember || g_user_w <= 0) return;
    sprintf(s, "%d", g_user_w); WritePrivateProfileStringA("view", "width", s, g_ini);
    sprintf(s, "%d", g_user_h); WritePrivateProfileStringA("view", "height", s, g_ini);
}

static void draw_frame(void);

static void redraw_now(void) {
    HDC dc;
    if (g_in_draw || !g_list || !REAL(wglGetCurrentContext, HGLRC, (void))()) return;
    dc = REAL(wglGetCurrentDC, HDC, (void))();
    if (!dc) return;
    draw_frame();
    SwapBuffers(dc);
}

static LRESULT CALLBACK my_proc(HWND h, UINT m, WPARAM w, LPARAM l) {
    LRESULT r;
    switch (m) {
    case WM_GETMINMAXINFO: {
        /* SDL は窓の大きさを固定してしまうので、ここでは SDL に渡さない */
        MINMAXINFO *mi = (MINMAXINFO *)l;
        DefWindowProcA(h, m, w, l);
        mi->ptMinTrackSize.x = 240; mi->ptMinTrackSize.y = 180;
        return 0;
    }
    case WM_ENTERSIZEMOVE: g_sizing++; break;
    case WM_EXITSIZEMOVE:
        if (g_sizing > 0) g_sizing--;
        remember_size(h); save_size();
        break;
    case WM_SYSCOMMAND: {
        UINT c = (UINT)(w & 0xFFF0);
        if (c == SC_MAXIMIZE || c == SC_RESTORE) {
            g_sizing++;
            r = CallWindowProcA(g_oldproc, h, m, w, l);
            g_sizing--;
            remember_size(h);
            redraw_now();
            return r;
        }
        break;
    }
    case WM_WINDOWPOSCHANGING: {
        /* SDL が窓を元の大きさに戻そうとしたら、人が選んだ大きさのままにする */
        WINDOWPOS *wp = (WINDOWPOS *)l;
        if (!g_sizing && !(wp->flags & SWP_NOSIZE) && g_user_w > 0 && windowed(h) && !IsZoomed(h)) {
            RECT rc = { 0, 0, g_user_w, g_user_h };
            AdjustWindowRectEx(&rc, (DWORD)GetWindowLongA(h, GWL_STYLE), FALSE, (DWORD)GetWindowLongA(h, GWL_EXSTYLE));
            wp->cx = rc.right - rc.left; wp->cy = rc.bottom - rc.top;
        }
        break;
    }
    case WM_SIZE:
        r = CallWindowProcA(g_oldproc, h, m, w, l);
        if (w != SIZE_MINIMIZED) {
            if (g_sizing && w != SIZE_MAXIMIZED) remember_size(h);
            redraw_now();
        }
        return r;
    case WM_KEYDOWN:
    case WM_SYSKEYDOWN:
        /* F11 で字の形（東雲・美咲）を切り替える。このキーはゲームには渡さない */
        if (w == VK_F11 && cfg_enabled) {
            if (!(l & (1 << 30))) {
                cfg_font = !cfg_font;
                WritePrivateProfileStringA("view", "font", cfg_font ? "shinonome" : "misaki", g_ini);
                plog("F11: font=%s", cfg_font ? "shinonome" : "misaki");
                g_dirty = 1;
                redraw_now();
            }
            return 0;
        }
        break;
    case WM_KEYUP:
    case WM_SYSKEYUP:
        if (w == VK_F11 && cfg_enabled) return 0;
        break;
    case WM_PAINT:
        r = CallWindowProcA(g_oldproc, h, m, w, l);
        redraw_now();
        return r;
    }
    return CallWindowProcA(g_oldproc, h, m, w, l);
}

static void hook_window(HWND h) {
    LONG st;
    if (!h) return;
    if (h != g_wnd) {
        g_wnd = h;
        g_oldproc = (WNDPROC)SetWindowLongPtrA(h, GWLP_WNDPROC, (LONG_PTR)my_proc);
        plog("窓をつかまえた: %p", (void *)h);
        if (g_user_w <= 0) { g_user_w = cfg_w; g_user_h = cfg_h; }
    }
    st = GetWindowLongA(h, GWL_STYLE);
    if ((st & WS_CAPTION) == WS_CAPTION && (st & (WS_THICKFRAME | WS_MAXIMIZEBOX)) != (WS_THICKFRAME | WS_MAXIMIZEBOX)) {
        SetWindowLongA(h, GWL_STYLE, st | WS_THICKFRAME | WS_MAXIMIZEBOX);
        if (!IsZoomed(h)) set_client_size(h, g_user_w, g_user_h);
        plog("窓のふちを変えられるようにした（%dx%d）", g_user_w, g_user_h);
    }
}

/* ---------------------------------------------------------------- 描く */
static void draw_frame(void) {
    HDC dc = REAL(wglGetCurrentDC, HDC, (void))();
    RECT rc;
    int vw, vh, vx, vy;
    float u, v, du, dv;
    static HGLRC last_ctx;
    HGLRC ctx = REAL(wglGetCurrentContext, HGLRC, (void))();
    g_in_draw = 1;
    if (ctx != last_ctx) {
        /* DOSBox が画面を切り替えると、作業場（コンテキスト）が作り直される。テクスチャも作り直す */
        last_ctx = ctx; g_tex = 0; g_tw = g_th = 0;
        plog("作業場が変わった: %p", (void *)ctx);
    }
    hook_window(WindowFromDC(dc));
#ifdef UJ_TEST
    if (g_dirty) { compose(); dump_bmp(); g_dirty = 0; }
#else
    if (g_dirty) { compose(); g_dirty = 0; }
#endif
    if (!g_canvas || !g_wnd) { g_in_draw = 0; return; }
    GetClientRect(g_wnd, &rc);
    if (rc.right <= 0 || rc.bottom <= 0) { g_in_draw = 0; return; }
    vw = rc.right; vh = rc.bottom;
    if (cfg_aspect) {
        if (vw * 3 > vh * 4) vw = vh * 4 / 3; else vh = vw * 3 / 4;
    }
    vx = (rc.right - vw) / 2; vy = (rc.bottom - vh) / 2;

    { GLenum e0 = REAL(glGetError, GLenum, (void))(); if (e0) plog("描く前のエラー %#x", e0); }
    REAL(glPushAttrib, void, (GLbitfield))(GL_ALL_ATTRIB_BITS);
    REAL(glPushClientAttrib, void, (GLbitfield))(GL_CLIENT_ALL_ATTRIB_BITS);
    REAL(glMatrixMode, void, (GLenum))(GL_TEXTURE); REAL(glPushMatrix, void, (void))(); REAL(glLoadIdentity, void, (void))();
    REAL(glMatrixMode, void, (GLenum))(GL_PROJECTION); REAL(glPushMatrix, void, (void))(); REAL(glLoadIdentity, void, (void))();
    REAL(glMatrixMode, void, (GLenum))(GL_MODELVIEW); REAL(glPushMatrix, void, (void))(); REAL(glLoadIdentity, void, (void))();
    REAL(glDisable, void, (GLenum))(GL_SCISSOR_TEST);
    REAL(glDisable, void, (GLenum))(GL_BLEND);
    REAL(glDisable, void, (GLenum))(GL_DEPTH_TEST);
    REAL(glDisable, void, (GLenum))(GL_LIGHTING);
    REAL(glDisable, void, (GLenum))(GL_CULL_FACE);
    REAL(glDisable, void, (GLenum))(GL_ALPHA_TEST);
    REAL(glViewport, void, (GLint, GLint, GLsizei, GLsizei))(0, 0, rc.right, rc.bottom);
    REAL(glClearColor, void, (GLclampf, GLclampf, GLclampf, GLclampf))(0, 0, 0, 1);
    REAL(glClear, void, (GLbitfield))(GL_COLOR_BUFFER_BIT);
    REAL(glViewport, void, (GLint, GLint, GLsizei, GLsizei))(vx, vy, vw, vh);
    REAL(glEnable, void, (GLenum))(GL_TEXTURE_2D);
    if (!g_tex) REAL(glGenTextures, void, (GLsizei, GLuint *))(1, &g_tex);
    REAL(glBindTexture, void, (GLenum, GLuint))(GL_TEXTURE_2D, g_tex);
    if (pow2(g_cw) != g_tw || pow2(g_ch) != g_th || g_tex_linear != cfg_linear) {
        g_tw = pow2(g_cw); g_th = pow2(g_ch); g_tex_linear = cfg_linear;
        REAL(glTexImage2D, void, (GLenum, GLint, GLint, GLsizei, GLsizei, GLint, GLenum, GLenum, const void *))
            (GL_TEXTURE_2D, 0, GL_RGBA8, g_tw, g_th, 0, GL_BGRA, GL_UNSIGNED_BYTE, NULL);
        REAL(glTexParameteri, void, (GLenum, GLenum, GLint))(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, cfg_linear ? GL_LINEAR : GL_NEAREST);
        REAL(glTexParameteri, void, (GLenum, GLenum, GLint))(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, cfg_linear ? GL_LINEAR : GL_NEAREST);
        REAL(glTexParameteri, void, (GLenum, GLenum, GLint))(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP);
        REAL(glTexParameteri, void, (GLenum, GLenum, GLint))(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP);
        g_canvas_new = 1;
        plog("自分のテクスチャ: %dx%d（絵 %dx%d）", g_tw, g_th, g_cw, g_ch);
    }
    if (g_canvas_new) {
        REAL(glPixelStorei, void, (GLenum, GLint))(GL_UNPACK_ALIGNMENT, 4);
        REAL(glPixelStorei, void, (GLenum, GLint))(GL_UNPACK_ROW_LENGTH, 0);
        REAL(glPixelStorei, void, (GLenum, GLint))(GL_UNPACK_SKIP_ROWS, 0);
        REAL(glPixelStorei, void, (GLenum, GLint))(GL_UNPACK_SKIP_PIXELS, 0);
        REAL(glTexSubImage2D, void, (GLenum, GLint, GLint, GLint, GLsizei, GLsizei, GLenum, GLenum, const void *))
            (GL_TEXTURE_2D, 0, 0, 0, g_cw, g_ch, GL_BGRA, GL_UNSIGNED_BYTE, g_canvas);
        g_canvas_new = 0;
    }
    REAL(glTexEnvi, void, (GLenum, GLenum, GLint))(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_REPLACE);
    du = 0.5f / g_tw; dv = 0.5f / g_th;
    u = (float)g_cw / g_tw - du; v = (float)g_ch / g_th - dv;
    REAL(glBegin, void, (GLenum))(GL_QUADS);
    REAL(glTexCoord2f, void, (GLfloat, GLfloat))(du, dv); REAL(glVertex2f, void, (GLfloat, GLfloat))(-1, 1);
    REAL(glTexCoord2f, void, (GLfloat, GLfloat))(u, dv);  REAL(glVertex2f, void, (GLfloat, GLfloat))(1, 1);
    REAL(glTexCoord2f, void, (GLfloat, GLfloat))(u, v);   REAL(glVertex2f, void, (GLfloat, GLfloat))(1, -1);
    REAL(glTexCoord2f, void, (GLfloat, GLfloat))(du, v);  REAL(glVertex2f, void, (GLfloat, GLfloat))(-1, -1);
    REAL(glEnd, void, (void))();
    REAL(glMatrixMode, void, (GLenum))(GL_MODELVIEW); REAL(glPopMatrix, void, (void))();
    REAL(glMatrixMode, void, (GLenum))(GL_PROJECTION); REAL(glPopMatrix, void, (void))();
    REAL(glMatrixMode, void, (GLenum))(GL_TEXTURE); REAL(glPopMatrix, void, (void))();
    REAL(glPopClientAttrib, void, (void))();
    REAL(glPopAttrib, void, (void))();
    {
        static int nlog;
        GLenum e = REAL(glGetError, GLenum, (void))();
        if (nlog < 20 && (e || nlog < 3)) { nlog++; plog("描いた: 窓 %dx%d 絵 %dx%d エラー %#x", rc.right, rc.bottom, g_cw, g_ch, e); }
    }
    g_in_draw = 0;
}

void WINAPI hk_glCallList(GLuint list) {
    if (cfg_enabled && list == g_list && g_mirror && g_w > 0 && g_h > 0 && g_w <= g_mir_w) {
        draw_frame();
        return;
    }
    REAL(glCallList, void, (GLuint))(list);
}

/* ---------------------------------------------------------------- 読み込み */
BOOL WINAPI DllMain(HINSTANCE inst, DWORD why, LPVOID rsv) {
    (void)rsv;
    if (why == DLL_PROCESS_ATTACH) {
        char sys[MAX_PATH], *p;
        HMODULE real;
        int i;
        DisableThreadLibraryCalls(inst);
        GetModuleFileNameA(inst, g_dir, sizeof g_dir);
        p = strrchr(g_dir, '\\');
        if (p) p[1] = 0;
        sprintf(g_ini, "%sultima_ja.ini", g_dir);
        GetSystemDirectoryA(sys, sizeof sys);
        strcat(sys, "\\opengl32.dll");
        real = LoadLibraryA(sys);
        if (!real || real == inst) return FALSE;
        for (i = 0; i < NREAL; i++) g_real[i] = GetProcAddress(real, real_names[i]);
        load_cfg();
        plog("本物の opengl32.dll: %s", sys);
    } else if (why == DLL_PROCESS_DETACH) {
        if (g_log) { fclose(g_log); g_log = NULL; }
    }
    return TRUE;
}
