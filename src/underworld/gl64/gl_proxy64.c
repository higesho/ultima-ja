/*
 * opengl32.dll の代わり（64 ビット、GOG 版 Ultima Underworld に付いている dosbox-staging 0.82 用）
 *   美咲フォント 8x8 で描かれた日本語の字を見つけて、東雲フォント 12px で描き直す（font=shinonome）
 * dosbox-staging は画面の絵と同じ大きさのテクスチャを作り（glTexImage2D）、変わった行を glTexSubImage2D で送り、
 * シェーダーで窓に広げる（glDrawArrays、大きさは uniform の rubyTextureSize と rubyInputSize）。
 * そこで絵を受け取り、3 倍（文字の画面は 2 倍）の大きい絵を作ってテクスチャにし、シェーダーにはその大きさを渡す。
 * 字を探して描き直す部分は Ultima 1/jp_work/gl/gl_proxy.c と同じ（detect_part.c）。
 * それ以外の関数は、すべて本物の opengl32.dll へそのままつなぐ（stubs.asm）。
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
#define GL_CURRENT_PROGRAM 0x8B8D
#define GL_PIXEL_UNPACK_BUFFER_BINDING 0x88EF

void *g_real[512];
#include "exports.h"

typedef struct { unsigned __int64 key; unsigned short shn[12]; unsigned short ucs; } GLYPH;
#include "glyphs.h"

#define REAL(name, ret, args) ((ret (WINAPI *) args) g_real[IX_##name])

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
static int g_active;                /* dosbox-staging の画面のテクスチャを見つけたか */
static int g_w, g_h;                /* 画面の絵の大きさ */
static unsigned *g_mirror;          /* 受け取った絵（BGRA） */
static int g_mir_w, g_mir_cap;
static unsigned char g_rowdirty[4096];
static int g_alldirty = 1;
static unsigned *g_canvas;
static int g_cw, g_ch, g_canvas_cap, g_canvas_new;

#include "detect_part.c"

/* ---------------------------------------------------------------- GL */
typedef void (WINAPI *PGetIntegerv)(GLenum, GLint *);
typedef void (WINAPI *PPixelStorei)(GLenum, GLint);
typedef PROC (WINAPI *PGetProc)(LPCSTR);
typedef GLint (WINAPI *PGetUniformLocation)(GLuint, const GLchar *);
typedef void (WINAPI *PUniform2f)(GLint, GLfloat, GLfloat);
typedef void (WINAPI *PTexImage2D)(GLenum, GLint, GLint, GLsizei, GLsizei, GLint, GLenum, GLenum, const void *);
typedef void (WINAPI *PTexSubImage2D)(GLenum, GLint, GLint, GLint, GLsizei, GLsizei, GLenum, GLenum, const void *);

static PGetUniformLocation p_GetUniformLocation;
static PUniform2f p_Uniform2f;

static GLint get_int(GLenum e) { GLint v = 0; REAL(glGetIntegerv, void, (GLenum, GLint *))(e, &v); return v; }
static void pixel_store(GLenum e, GLint v) { REAL(glPixelStorei, void, (GLenum, GLint))(e, v); }

/* 大きい絵の y0〜y1 行をテクスチャに送る（送り方の設定は一時的に、詰めた並びに） */
static void upload(GLenum type, int y0, int y1) {
    GLint rl = get_int(GL_UNPACK_ROW_LENGTH), sr = get_int(GL_UNPACK_SKIP_ROWS), sp = get_int(GL_UNPACK_SKIP_PIXELS);
    GLint al = get_int(GL_UNPACK_ALIGNMENT);
    if (y1 <= y0) return;
    pixel_store(GL_UNPACK_ROW_LENGTH, g_cw); pixel_store(GL_UNPACK_SKIP_ROWS, 0);
    pixel_store(GL_UNPACK_SKIP_PIXELS, 0); pixel_store(GL_UNPACK_ALIGNMENT, 4);
    REAL(glTexSubImage2D, void, (GLenum, GLint, GLint, GLint, GLsizei, GLsizei, GLenum, GLenum, const void *))
        (GL_TEXTURE_2D, 0, 0, y0, g_cw, y1 - y0, GL_BGRA, type, g_canvas + (size_t)y0 * g_cw);
    pixel_store(GL_UNPACK_ROW_LENGTH, rl); pixel_store(GL_UNPACK_SKIP_ROWS, sr);
    pixel_store(GL_UNPACK_SKIP_PIXELS, sp); pixel_store(GL_UNPACK_ALIGNMENT, al);
}

/* 受け取った w×h の絵（行の長さ pitch 画素）を写しの (x, y) に写す */
static void take(int x, int y, int w, int h, const unsigned char *px, int pitch) {
    int r;
    for (r = 0; r < h; r++) {
        if (y + r < 0 || y + r >= g_h) continue;
        memcpy(g_mirror + (size_t)(y + r) * g_mir_w + x, px + (size_t)r * pitch * 4, (size_t)w * 4);
        g_rowdirty[y + r] = 1;
    }
}

void WINAPI hk_glTexImage2D(GLenum target, GLint level, GLint ifmt, GLsizei w, GLsizei h, GLint border,
                            GLenum fmt, GLenum type, const void *px) {
    if (target == GL_TEXTURE_2D && level == 0 && fmt == GL_BGRA && w >= 200 && w <= 1024 && h >= 150 && h <= 1024 &&
        get_int(GL_PIXEL_UNPACK_BUFFER_BINDING) == 0) {
        LAYOUT L;
        int need = w * h;
        if (need > g_mir_cap) {
            unsigned *n = (unsigned *)calloc(need, 4);
            if (!n) goto pass;
            free(g_mirror); g_mirror = n; g_mir_cap = need;
        }
        g_w = w; g_h = h; g_mir_w = w;
        if (px) { int rl = get_int(GL_UNPACK_ROW_LENGTH); take(0, 0, w, h, (const unsigned char *)px, rl ? rl : w); }
        else memset(g_mirror, 0, (size_t)w * h * 4);
        g_alldirty = 1;
        memset(g_rowdirty, 1, sizeof g_rowdirty);
        make_layout(&L);
        g_cw = L.lw * L.k; g_ch = L.lh * L.k;
        REAL(glTexImage2D, void, (GLenum, GLint, GLint, GLsizei, GLsizei, GLint, GLenum, GLenum, const void *))
            (target, level, ifmt, g_cw, g_ch, border, fmt, type, NULL);
        g_active = 1;
        compose();
        upload(type, 0, g_ch);
        plog("画面のテクスチャ: %dx%d → %dx%d", w, h, g_cw, g_ch);
        return;
    }
pass:
    REAL(glTexImage2D, void, (GLenum, GLint, GLint, GLsizei, GLsizei, GLint, GLenum, GLenum, const void *))
        (target, level, ifmt, w, h, border, fmt, type, px);
}

void WINAPI hk_glTexSubImage2D(GLenum target, GLint level, GLint x, GLint y, GLsizei w, GLsizei h,
                               GLenum fmt, GLenum type, const void *px) {
    if (g_active && target == GL_TEXTURE_2D && level == 0 && fmt == GL_BGRA && px &&
        get_int(GL_PIXEL_UNPACK_BUFFER_BINDING) == 0 && x >= 0 && y >= 0 && x + w <= g_w && y + h <= g_h) {
        int rl = get_int(GL_UNPACK_ROW_LENGTH);
        const unsigned char *p = (const unsigned char *)px;
        int pitch = rl ? rl : w;
        p += ((size_t)get_int(GL_UNPACK_SKIP_ROWS) * pitch + get_int(GL_UNPACK_SKIP_PIXELS)) * 4;
        take(x, y, w, h, p, pitch);
        compose();
        if (g_canvas_new) { upload(type, g_up_y0, g_up_y1); g_canvas_new = 0; }
        return;
    }
    REAL(glTexSubImage2D, void, (GLenum, GLint, GLint, GLint, GLsizei, GLsizei, GLenum, GLenum, const void *))
        (target, level, x, y, w, h, fmt, type, px);
}

/* 描く前に、シェーダーへ大きい絵の大きさを渡す */
static void set_size(const char *name) {
    GLint prog = get_int(GL_CURRENT_PROGRAM), loc;
    if (!prog || !p_GetUniformLocation || !p_Uniform2f) return;
    loc = p_GetUniformLocation((GLuint)prog, name);
    if (loc >= 0) p_Uniform2f(loc, (GLfloat)g_cw, (GLfloat)g_ch);
}

void WINAPI hk_glDrawArrays(GLenum mode, GLint first, GLsizei n) {
    if (g_active) {
        if (!p_GetUniformLocation) {
            PGetProc gp = (PGetProc)g_real[IX_wglGetProcAddress];
            p_GetUniformLocation = (PGetUniformLocation)gp("glGetUniformLocation");
            p_Uniform2f = (PUniform2f)gp("glUniform2f");
        }
        set_size("rubyTextureSize");
        set_size("rubyInputSize");
    }
    REAL(glDrawArrays, void, (GLenum, GLint, GLsizei))(mode, first, n);
}

void WINAPI hk_glViewport(GLint x, GLint y, GLsizei w, GLsizei h) {
    REAL(glViewport, void, (GLint, GLint, GLsizei, GLsizei))(x, y, w, h);
}

PROC WINAPI hk_wglGetProcAddress(LPCSTR name) {
    return ((PGetProc)g_real[IX_wglGetProcAddress])(name);
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID res) {
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
        plog("本物 %s = %p、字の形 %d", sys, real, NGLYPH);
        for (i = 0; i < NREAL; i++) g_real[i] = (void *)GetProcAddress(real, real_names[i]);
    }
    return TRUE;
}
