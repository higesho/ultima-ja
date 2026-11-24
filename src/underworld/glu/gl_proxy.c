/*
 * opengl32.dll の代わり（32 ビット・64 ビット共通。DOSBox の版を問わない）
 *   美咲フォント 8x8 で描かれた日本語の字を見つけて、東雲フォント 12px で描き直す（font=shinonome）
 *
 * DOSBox が画面を描く方法は版によって 2 通りある。どちらかを、呼ばれる関数から見分ける。
 *   ・0.72〜0.74-3、daum など: 2 のべき乗の大きさのテクスチャ（512x512 など）の左上に画面を置き、
 *     表示リスト（glNewList〜glEndList）に入れた四角形で描く。四角形の glTexCoord2f の値
 *     （画面の幅 / テクスチャの幅）から、画面の大きさがわかる。
 *     → テクスチャを k 倍の大きさで作り直し、左上に k 倍の絵を置く。割合は変わらないので、表示リストはそのまま使える。
 *   ・dosbox-staging: 画面と同じ大きさのテクスチャを作り、シェーダーで窓に広げる（大きさは uniform で渡す）。
 *     → テクスチャを k 倍の大きさで作り、描く前（glDrawArrays）にシェーダーへ大きい絵の大きさを渡す。
 * どちらも、変わった行は glTexSubImage2D で送られてくるので、受け取って写しを作り、描き直した大きい絵を送る。
 * 字を探して描き直す部分は ../gl64/detect_part.c。ほかの関数は本物の opengl32.dll へそのままつなぐ（gen_fwd.py）。
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef unsigned int GLenum; typedef int GLint; typedef int GLsizei; typedef unsigned int GLuint;
typedef float GLfloat; typedef char GLchar;

#define GL_TEXTURE_2D 0x0DE1
#define GL_BGRA 0x80E1
#define GL_UNPACK_ROW_LENGTH 0x0CF2
#define GL_UNPACK_SKIP_ROWS 0x0CF3
#define GL_UNPACK_SKIP_PIXELS 0x0CF4
#define GL_UNPACK_ALIGNMENT 0x0CF5
#define GL_MAX_TEXTURE_SIZE 0x0D33
#define GL_TEXTURE_BINDING_2D 0x8069
#define GL_CURRENT_PROGRAM 0x8B8D
#define GL_PIXEL_UNPACK_BUFFER_BINDING 0x88EF

FARPROC g_real[512];
#include "fwd_names.h"
#ifndef _WIN64
#include "fwd32.h"
#endif

typedef struct { unsigned __int64 key; unsigned short shn[12]; unsigned short ucs; } GLYPH;
#include "../gl64/glyphs.h"

#define REAL(name, ret, args) ((ret (WINAPI *) args) g_real[IX_##name])
typedef void (WINAPI *PTexImage2D)(GLenum, GLint, GLint, GLsizei, GLsizei, GLint, GLenum, GLenum, const void *);
typedef void (WINAPI *PTexSubImage2D)(GLenum, GLint, GLint, GLint, GLsizei, GLsizei, GLenum, GLenum, const void *);
#define R_TexImage2D REAL(glTexImage2D, void, (GLenum, GLint, GLint, GLsizei, GLsizei, GLint, GLenum, GLenum, const void *))
#define R_TexSubImage2D REAL(glTexSubImage2D, void, (GLenum, GLint, GLint, GLint, GLsizei, GLsizei, GLenum, GLenum, const void *))
#define R_BindTexture REAL(glBindTexture, void, (GLenum, GLuint))

/* ---------------------------------------------------------------- 設定と記録 */
static char g_dir[MAX_PATH], g_ini[MAX_PATH];
static int cfg_font = 1;        /* 1 = 東雲、0 = 美咲（描き直さない） */
static int cfg_log = 0;
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
    cfg_log = GetPrivateProfileIntA("view", "log", 0, g_ini);
}

/* ---------------------------------------------------------------- 受け取った絵と大きい絵 */
static int g_active;                /* 画面のテクスチャを見つけて、描き直しを始めたか */
static int g_w, g_h;                /* 画面の絵の大きさ */
static unsigned *g_mirror;          /* 受け取った絵（BGRA） */
static int g_mir_w, g_mir_cap;
static unsigned char g_rowdirty[4096];
static int g_alldirty = 1;
static unsigned *g_canvas;
static int g_cw, g_ch, g_canvas_cap, g_canvas_new;

#include "../gl64/detect_part.c"

/* 画面のテクスチャ */
enum { M_NONE, M_WAIT_LIST, M_LIST, M_SHADER };
static int g_mode;
static GLuint g_tex;                /* テクスチャの番号 */
static int g_tw, g_th;              /* DOSBox が作ったテクスチャの大きさ */
static GLint g_ifmt; static GLenum g_type;
static int g_k;                     /* テクスチャを何倍で作り直したか */
static int g_in_list;               /* 表示リストを作っている途中か */
static float g_ts, g_tt;            /* その間の glTexCoord2f の一番大きい値 */

static GLint get_int(GLenum e) { GLint v = 0; REAL(glGetIntegerv, void, (GLenum, GLint *))(e, &v); return v; }
static void pixel_store(GLenum e, GLint v) { REAL(glPixelStorei, void, (GLenum, GLint))(e, v); }

/* PBO（0.74-2 以降は、絵をいったん GPU 側のバッファに書き、そこからテクスチャに送る） */
#define GL_PIXEL_UNPACK_BUFFER 0x88EC
#define GL_READ_ONLY 0x88B8
typedef PROC (WINAPI *PGetProc)(LPCSTR);
typedef void (WINAPI *PBindBuffer)(GLenum, GLuint);
typedef void *(WINAPI *PMapBuffer)(GLenum, GLenum);
typedef unsigned char (WINAPI *PUnmapBuffer)(GLenum);
static PBindBuffer p_BindBuffer; static PMapBuffer p_MapBuffer; static PUnmapBuffer p_UnmapBuffer;
static int g_pbo_ready;
static PROC proc2(const char *a, const char *b) {
    PGetProc gp = (PGetProc)g_real[IX_wglGetProcAddress];
    PROC f = gp(a);
    return f ? f : gp(b);
}
static int pbo_funcs(void) {
    if (!g_pbo_ready) {
        p_BindBuffer = (PBindBuffer)proc2("glBindBuffer", "glBindBufferARB");
        p_MapBuffer = (PMapBuffer)proc2("glMapBuffer", "glMapBufferARB");
        p_UnmapBuffer = (PUnmapBuffer)proc2("glUnmapBuffer", "glUnmapBufferARB");
        g_pbo_ready = 1;
    }
    return p_BindBuffer && p_MapBuffer && p_UnmapBuffer;
}

/* 大きい絵の y0〜y1 行をテクスチャの左上に送る（送り方の設定は一時的に、詰めた並びに） */
static void upload(int y0, int y1) {
    GLint rl, sr, sp, al, pbo;
    if (y1 <= y0) return;
    rl = get_int(GL_UNPACK_ROW_LENGTH); sr = get_int(GL_UNPACK_SKIP_ROWS);
    sp = get_int(GL_UNPACK_SKIP_PIXELS); al = get_int(GL_UNPACK_ALIGNMENT);
    pbo = get_int(GL_PIXEL_UNPACK_BUFFER_BINDING);
    if (pbo) { if (!pbo_funcs()) return; p_BindBuffer(GL_PIXEL_UNPACK_BUFFER, 0); }
    pixel_store(GL_UNPACK_ROW_LENGTH, g_cw); pixel_store(GL_UNPACK_SKIP_ROWS, 0);
    pixel_store(GL_UNPACK_SKIP_PIXELS, 0); pixel_store(GL_UNPACK_ALIGNMENT, 4);
    R_TexSubImage2D(GL_TEXTURE_2D, 0, 0, y0, g_cw, y1 - y0, GL_BGRA, g_type, g_canvas + (size_t)y0 * g_cw);
    pixel_store(GL_UNPACK_ROW_LENGTH, rl); pixel_store(GL_UNPACK_SKIP_ROWS, sr);
    pixel_store(GL_UNPACK_SKIP_PIXELS, sp); pixel_store(GL_UNPACK_ALIGNMENT, al);
    if (pbo) p_BindBuffer(GL_PIXEL_UNPACK_BUFFER, (GLuint)pbo);
}

/* 受け取った w×h の絵（行の長さ pitch 画素）を写しの (x, y) に写す */
static void take(int x, int y, int w, int h, const unsigned char *px, int pitch) {
    int r;
    for (r = 0; r < h; r++) {
        if (y + r < 0 || y + r >= g_h) continue;
        unsigned *d = g_mirror + (size_t)(y + r) * g_mir_w + x;
        const unsigned char *s = px + (size_t)r * pitch * 4;
        /* 毎回画面全体を送ってくる版もあるので、本当に変わった行だけを「変わった」とする */
        if (memcmp(d, s, (size_t)w * 4)) { memcpy(d, s, (size_t)w * 4); g_rowdirty[y + r] = 1; }
    }
}

/* 画面が w×h とわかったので、写しを用意して描き直しを始める。大きい絵の倍率 k を返す（0 なら始めない） */
static int start(int w, int h) {
    LAYOUT L;
    int need = w * h;
    if (w < 8 || h < 8 || w > 4096 || h > 4096) return 0;
    if (need > g_mir_cap) {
        unsigned *n = (unsigned *)calloc(need, 4);
        if (!n) return 0;
        free(g_mirror); g_mirror = n; g_mir_cap = need;
    }
    g_w = w; g_h = h; g_mir_w = w;
    memset(g_mirror, 0, (size_t)need * 4);
    g_alldirty = 1;
    memset(g_rowdirty, 1, sizeof g_rowdirty);
    make_layout(&L);
    return L.k;
}

static int bound_tex(void) { return get_int(GL_TEXTURE_BINDING_2D); }

static int pow2(int v) { return v > 0 && (v & (v - 1)) == 0; }

void WINAPI hk_glTexImage2D(GLenum target, GLint level, GLint ifmt, GLsizei w, GLsizei h, GLint border,
                            GLenum fmt, GLenum type, const void *px) {
    if (cfg_log >= 2) plog("glTexImage2D %x lv=%d ifmt=%x %dx%d fmt=%x 番号 %d リスト中 %d", target, level, ifmt, w, h, fmt, bound_tex(), g_in_list);
    if (target == GL_TEXTURE_2D && level == 0 && !g_in_list) {
        GLuint t = (GLuint)bound_tex();
        if (fmt == GL_BGRA && w >= 200 && w <= 2048 && h >= 150 && h <= 2048 &&
            get_int(GL_PIXEL_UNPACK_BUFFER_BINDING) == 0) {
            g_tex = t; g_tw = w; g_th = h; g_ifmt = ifmt; g_type = type; g_active = 0;
            if (pow2(w) && pow2(h)) {
                /* 0.74 などの作り方。画面の大きさは、このあと作る表示リストでわかる */
                g_mode = M_WAIT_LIST;
                plog("テクスチャ %dx%d（番号 %u）: 表示リストを待つ", w, h, t);
            } else {
                /* staging の作り方。テクスチャがそのまま画面の大きさ */
                int k = start(w, h);
                if (k) {
                    LAYOUT L;
                    make_layout(&L);
                    g_cw = L.lw * L.k; g_ch = L.lh * L.k;
                    R_TexImage2D(target, level, ifmt, g_cw, g_ch, border, fmt, type, NULL);
                    if (px) { int rl = get_int(GL_UNPACK_ROW_LENGTH); take(0, 0, w, h, (const unsigned char *)px, rl ? rl : w); }
                    g_mode = M_SHADER; g_k = k; g_active = 1;
                    compose();
                    upload(0, g_ch);
                    plog("テクスチャ %dx%d（番号 %u）: シェーダーで描く画面 → %dx%d", w, h, t, g_cw, g_ch);
                    return;
                }
                g_mode = M_NONE;
            }
        } else if (g_mode != M_NONE && t == g_tex) {
            /* 画面のテクスチャが別の使い方で作り直された */
            g_mode = M_NONE; g_active = 0;
        }
    }
    R_TexImage2D(target, level, ifmt, w, h, border, fmt, type, px);
}

void WINAPI hk_glNewList(GLuint list, GLenum mode) {
    g_in_list = 1; g_ts = g_tt = 0;
    REAL(glNewList, void, (GLuint, GLenum))(list, mode);
}

void WINAPI hk_glTexCoord2f(GLfloat s, GLfloat t) {
    if (g_in_list) { if (s > g_ts) g_ts = s; if (t > g_tt) g_tt = t; }
    REAL(glTexCoord2f, void, (GLfloat, GLfloat))(s, t);
}

void WINAPI hk_glEndList(void) {
    REAL(glEndList, void, (void))();
    g_in_list = 0;
    if (g_mode == M_WAIT_LIST && g_ts > 0 && g_tt > 0 && g_ts <= 1.0f && g_tt <= 1.0f) {
        int w = (int)(g_ts * g_tw + 0.5f), h = (int)(g_tt * g_th + 0.5f);
        int k = start(w, h), maxt = get_int(GL_MAX_TEXTURE_SIZE);
        if (k && maxt > 0) {
            GLint was = bound_tex();
            LAYOUT L;
            /* 大きすぎるテクスチャは作れないので、倍率を下げる（下げると東雲は描けず、美咲のまま） */
            while (k > 1 && (g_tw * k > maxt || g_th * k > maxt)) k--;
            make_layout(&L);
            if (k != L.k) { plog("テクスチャが大きすぎるので描き直さない（%d 倍が作れない）", L.k); g_mode = M_NONE; return; }
            g_cw = L.lw * L.k; g_ch = L.lh * L.k;
            if ((GLuint)was != g_tex) R_BindTexture(GL_TEXTURE_2D, g_tex);
            R_TexImage2D(GL_TEXTURE_2D, 0, g_ifmt, g_tw * k, g_th * k, 0, GL_BGRA, g_type, NULL);
            g_mode = M_LIST; g_k = k; g_active = 1;
            compose();
            upload(0, g_ch);
            if ((GLuint)was != g_tex) R_BindTexture(GL_TEXTURE_2D, (GLuint)was);
            plog("表示リスト: 画面 %dx%d（%.4f, %.4f）→ テクスチャ %dx%d、絵 %dx%d",
                 w, h, g_ts, g_tt, g_tw * k, g_th * k, g_cw, g_ch);
        } else {
            g_mode = M_NONE;
        }
    }
}

void WINAPI hk_glTexSubImage2D(GLenum target, GLint level, GLint x, GLint y, GLsizei w, GLsizei h,
                               GLenum fmt, GLenum type, const void *px) {
    GLint pbo;
    if (g_active && target == GL_TEXTURE_2D && level == 0 && fmt == GL_BGRA && !g_in_list &&
        x >= 0 && y >= 0 && (GLuint)bound_tex() == g_tex &&
        ((pbo = get_int(GL_PIXEL_UNPACK_BUFFER_BINDING)) != 0 ? pbo_funcs() : px != NULL)) {
        int rl = get_int(GL_UNPACK_ROW_LENGTH);
        const unsigned char *p, *base = NULL;
        int pitch = rl ? rl : w, cw = w, ch = h;
        if (pbo) {
            /* バッファの中身を読む（px はバッファの中の位置） */
            base = (const unsigned char *)p_MapBuffer(GL_PIXEL_UNPACK_BUFFER, GL_READ_ONLY);
            if (!base) goto pass;
            p = base + (size_t)px;
        } else {
            p = (const unsigned char *)px;
        }
        p += ((size_t)get_int(GL_UNPACK_SKIP_ROWS) * pitch + get_int(GL_UNPACK_SKIP_PIXELS)) * 4;
        /* 画面の外（テクスチャの余り）に送られた分は捨てる */
        if (x + cw > g_w) cw = g_w - x;
        if (y + ch > g_h) ch = g_h - y;
        if (cw > 0 && ch > 0) take(x, y, cw, ch, p, pitch);
        if (cfg_log >= 2) {
            static int n; int r, d = 0;
            for (r = 0; r < g_h; r++) d += g_rowdirty[r];
            if (n++ < 400) {
                GLint tw = 0; REAL(glGetTexLevelParameteriv, void, (GLenum, GLint, GLenum, GLint *))(GL_TEXTURE_2D, 0, 0x1000, &tw);
                plog("送られた絵 (%d,%d) %dx%d pbo=%d 変わった行 %d 型 %x テクスチャの幅 %d", x, y, w, h, pbo, d, type, tw);
            }
        }
        if (base) p_UnmapBuffer(GL_PIXEL_UNPACK_BUFFER);
        g_type = type;
        compose();
        if (g_canvas_new) { upload(g_up_y0, g_up_y1); g_canvas_new = 0; }
        return;
    }
pass:
    R_TexSubImage2D(target, level, x, y, w, h, fmt, type, px);
}

/* ---------------------------------------------------------------- シェーダーで描く版（staging） */
typedef GLint (WINAPI *PGetUniformLocation)(GLuint, const GLchar *);
typedef void (WINAPI *PUniform2f)(GLint, GLfloat, GLfloat);
static PGetUniformLocation p_GetUniformLocation;
static PUniform2f p_Uniform2f;

static void set_size(GLuint prog, const char *name) {
    GLint loc = p_GetUniformLocation(prog, name);
    if (loc >= 0) p_Uniform2f(loc, (GLfloat)g_cw, (GLfloat)g_ch);
}

void WINAPI hk_glDrawArrays(GLenum mode, GLint first, GLsizei n) {
    if (g_active && g_mode == M_SHADER) {
        GLint prog = get_int(GL_CURRENT_PROGRAM);
        if (!p_GetUniformLocation) {
            PGetProc gp = (PGetProc)g_real[IX_wglGetProcAddress];
            p_GetUniformLocation = (PGetUniformLocation)gp("glGetUniformLocation");
            p_Uniform2f = (PUniform2f)gp("glUniform2f");
        }
        if (prog && p_GetUniformLocation && p_Uniform2f) {
            set_size((GLuint)prog, "rubyTextureSize");
            set_size((GLuint)prog, "rubyInputSize");
        }
    }
    REAL(glDrawArrays, void, (GLenum, GLint, GLsizei))(mode, first, n);
}

/* 本物の 1.1 の関数を wglGetProcAddress で取りに来る版があっても、こちらを通るように */
PROC WINAPI hk_wglGetProcAddress(LPCSTR name) {
    if (name && ((ULONG_PTR)name >> 16)) {
        if (!strcmp(name, "glTexImage2D")) return (PROC)hk_glTexImage2D;
        if (!strcmp(name, "glTexSubImage2D")) return (PROC)hk_glTexSubImage2D;
        if (!strcmp(name, "glNewList")) return (PROC)hk_glNewList;
        if (!strcmp(name, "glEndList")) return (PROC)hk_glEndList;
        if (!strcmp(name, "glTexCoord2f")) return (PROC)hk_glTexCoord2f;
        if (!strcmp(name, "glDrawArrays")) return (PROC)hk_glDrawArrays;
    }
    return ((PGetProc)g_real[IX_wglGetProcAddress])(name);
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID res) {
    (void)res;
    if (reason == DLL_PROCESS_ATTACH) {
        char sys[MAX_PATH], *p;
        HMODULE real;
        int i;
        GetModuleFileNameA(inst, g_dir, MAX_PATH);
        p = strrchr(g_dir, '\\'); if (p) p[1] = 0;
        sprintf(g_ini, "%sultima_ja.ini", g_dir);
        load_cfg();
        if (cfg_log) { char lp[MAX_PATH]; sprintf(lp, "%sultima_ja.log", g_dir); g_log = fopen(lp, "w"); }
        GetSystemDirectoryA(sys, MAX_PATH);
        strcat(sys, "\\opengl32.dll");
        real = LoadLibraryA(sys);
        plog("本物 %s = %p、%d ビット、字の形 %d", sys, real, (int)sizeof(void *) * 8, NGLYPH);
        for (i = 0; i < NREAL; i++) g_real[i] = GetProcAddress(real, real_names[i]);
    }
    return TRUE;
}
