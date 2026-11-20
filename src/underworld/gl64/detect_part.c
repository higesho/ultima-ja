/* ---------------------------------------------------------------- 字を描き直す */
/* 大きい絵の作り方。xs … 元の絵の何画素が 1 画素か（横に 2 倍で出る画面のため）。
 * rd … 字の 1 行が何行で出ているか（400 行の画面では、絵の画面も文字の画面も字が縦 2 倍） */
typedef struct { int lw, lh, xs, k, rd; } LAYOUT;
static LAYOUT g_lay;

static int cols_doubled(void) {
    int x, y;
    /* dosbox-staging は画面の本当の幅を送ってくる（横 2 倍の絵は来ない）。テクスチャを作る時点では絵がまだ空で
     * 「2 倍」と誤って判定し、大きい絵の大きさがテクスチャと食い違って文字の画面が真っ黒になるので、常に 2 倍ではないとする */
    return 0;
    for (y = 0; y < g_h; y += 7)
        for (x = 0; x + 1 < g_w; x += 2)
            if (g_mirror[y * g_mir_w + x] != g_mirror[y * g_mir_w + x + 1]) return 0;
    return 1;
}

static void make_layout(LAYOUT *L) {
    memset(L, 0, sizeof *L);
    L->xs = (g_w >= 640 && g_h <= 400 && cols_doubled()) ? 2 : 1;
    L->lw = g_w / L->xs; L->lh = g_h;
    L->k = (L->lw <= 700 && L->lh <= 700) ? 3 : (L->lw >= 960 ? 1 : 2);
    L->rd = L->lh >= 400 ? 2 : 1;
}

/* ---- 字を探す
 * 画面のどの位置でも、8x8（縦 2 倍なら 8x16）の窓が 2 色だけで、美咲の字の形と同じなら字とみなす。
 * 点の少ない字（ー・、 など）は絵と取り違えやすいので、マスにそろった位置か、すぐ隣に取った字があるときだけ使う。 */
#define WEAK_PIX 10
#define MAXMATCH 6000
typedef struct { short x, y, gi, w; unsigned fg, bg; } MATCH;
static MATCH g_cand[MAXMATCH], g_acc[MAXMATCH];
static int g_ncand, g_nacc;
static unsigned char *g_run;     /* 同じ色が右へ何画素続くか（8 で打ち止め） */
static int g_run_cap;
static unsigned char g_weight[NGLYPH];

#define LP(L, x, y) g_mirror[(size_t)(y) * g_mir_w + (size_t)(x) * (L)->xs]

static int glyph_find(unsigned __int64 key) {
    int lo = 0, hi = NGLYPH - 1;
    while (lo <= hi) {
        int mid = (lo + hi) >> 1;
        if (glyph_tab[mid].key == key) return mid;
        if (glyph_tab[mid].key < key) lo = mid + 1; else hi = mid - 1;
    }
    return -1;
}

static int popcount64(unsigned __int64 v) { int n = 0; while (v) { v &= v - 1; n++; } return n; }

static void make_runs(const LAYOUT *L) {
    int x, y;
    size_t need = (size_t)L->lw * L->lh;
    if (need > (size_t)g_run_cap) {
        free(g_run); g_run = (unsigned char *)malloc(need);
        g_run_cap = g_run ? (int)need : 0;
        if (!g_run) return;
    }
    for (y = 0; y < L->lh; y++) {
        unsigned char *r = g_run + (size_t)y * L->lw;
        if (!g_rowdirty[y]) continue;
        r[L->lw - 1] = 1;
        for (x = L->lw - 2; x >= 0; x--)
            r[x] = (LP(L, x, y) == LP(L, x + 1, y)) ? (unsigned char)(r[x + 1] < 8 ? r[x + 1] + 1 : 8) : 1;
    }
}

/* (x, y) の窓を調べる。字なら候補に足す */
static void try_window(const LAYOUT *L, int x, int y) {
    unsigned a = LP(L, x, y), b = 0, c;
    unsigned __int64 ma = 0;
    int hb = 0, r, i, gi, rd = L->rd;
    for (r = 0; r < 8; r++) {
        int yy = y + r * rd;
        const unsigned char *run = g_run + (size_t)yy * L->lw + x;
        if (rd == 2) {
            /* 縦 2 倍の字: 2 行が同じでないといけない */
            if (run[0] >= 8 && g_run[(size_t)(yy + 1) * L->lw + x] >= 8) {
                if (LP(L, x, yy) != LP(L, x, yy + 1)) return;
            } else {
                for (i = 0; i < 8; i++) if (LP(L, x + i, yy) != LP(L, x + i, yy + 1)) return;
            }
        }
        if (run[0] >= 8) {
            c = LP(L, x, yy);
            if (c == a) ma |= 0xFFULL << (56 - r * 8);
            else if (!hb) { b = c; hb = 1; }
            else if (c != b) return;
        } else {
            for (i = 0; i < 8; i++) {
                c = LP(L, x + i, yy);
                if (c == a) ma |= 1ULL << (63 - (r * 8 + i));
                else if (!hb) { b = c; hb = 1; }
                else if (c != b) return;
            }
        }
    }
    if (!hb) return;
    {
        MATCH *m;
        unsigned fg, bg;
        if ((gi = glyph_find(~ma)) >= 0) { fg = b; bg = a; }
        else if ((gi = glyph_find(ma)) >= 0) { fg = a; bg = b; }
        else return;
        if (g_ncand >= MAXMATCH) return;
        m = &g_cand[g_ncand++];
        m->x = (short)x; m->y = (short)y; m->gi = (short)gi; m->w = g_weight[gi]; m->fg = fg; m->bg = bg;
    }
}

static int overlaps(const MATCH *m, int gh) {
    int i;
    for (i = 0; i < g_nacc; i++) {
        int dx = g_acc[i].x - m->x, dy = g_acc[i].y - m->y;
        if (dx < 8 && dx > -8 && dy < gh && dy > -gh) return 1;
    }
    return 0;
}

/* 点の少ない字は、8 ドットのマスにそろった位置にあるか、
 * すぐ隣（同じ行で 8 か 9 画素横）にもう取った字があるときだけ使う */
static int weak_ok(const MATCH *m) {
    int i;
    if (m->x % 8 == 0 && m->y % (8 * g_lay.rd) == 0) return 1;
    for (i = 0; i < g_nacc; i++) {
        int dx = g_acc[i].x - m->x;
        if (g_acc[i].y != m->y) continue;
        if (dx < 0) dx = -dx;
        if (dx == 8 || dx == 9) return 1;
    }
    return 0;
}

static int cmp_weight(const void *p, const void *q) {
    const MATCH *a = (const MATCH *)p, *b = (const MATCH *)q;
    if (a->w != b->w) return b->w - a->w;
    if (a->y != b->y) return a->y - b->y;
    return a->x - b->x;
}

static int same_match(const MATCH *a, const MATCH *b) {
    return a->x == b->x && a->y == b->y && a->gi == b->gi && a->fg == b->fg && a->bg == b->bg;
}

static int in_list(const MATCH *m, const MATCH *list, int n) {
    int i;
    for (i = 0; i < n; i++) if (same_match(m, &list[i])) return 1;
    return 0;
}

/* 窓（y から gh 行）が、変わった行にかかっているか */
static int g_dsum[4097];
static int window_dirty(int y, int gh) { return g_dsum[y + gh] - g_dsum[y] > 0; }

static void find_glyphs(const LAYOUT *L, int full) {
    int x, y, i, n, gh = 8 * L->rd;
    static int ready;
    if (!ready) {
        for (i = 0; i < NGLYPH; i++) g_weight[i] = (unsigned char)popcount64(glyph_tab[i].key);
        ready = 1;
    }
    if (full) g_ncand = 0;
    g_nacc = 0;
    if (L->lw < 8 || L->lh < gh) return;
    make_runs(L);
    if (!g_run) return;
    /* 変わっていない行の候補は、そのまま残す */
    for (i = n = 0; i < g_ncand; i++)
        if (!window_dirty(g_cand[i].y, gh)) g_cand[n++] = g_cand[i];
    g_ncand = n;
    for (y = 0; y + gh <= L->lh; y++) {
        if (!window_dirty(y, gh)) continue;
        for (x = 0; x + 8 <= L->lw; x++) try_window(L, x, y);
    }
    qsort(g_cand, g_ncand, sizeof(MATCH), cmp_weight);
    /* 点の多い字から順に、重ならないものを取る */
    for (i = 0; i < g_ncand; i++) {
        MATCH *m = &g_cand[i];
        if (m->w < WEAK_PIX) break;
        if (!overlaps(m, gh)) g_acc[g_nacc++] = *m;
    }
    /* 点の少ない字は、隣へ隣へとつながる（「キャラクター・」など）まで繰り返す */
    {
        int first = i, changed = 1;
        static unsigned char used[MAXMATCH];
        memset(used, 0, sizeof used);
        while (changed) {
            changed = 0;
            for (i = first; i < g_ncand; i++) {
                MATCH *m = &g_cand[i];
                if (used[i] || overlaps(m, gh) || !weak_ok(m)) continue;
                g_acc[g_nacc++] = *m;
                used[i] = 1;
                changed = 1;
            }
        }
    }
}

static void paint_glyph(const LAYOUT *L, const MATCH *m) {
    int gw = 8 * L->k, gh = 8 * L->k * L->rd;
    int sx = gw / 12, sy = gh / 12, x, y;
    int px0 = m->x * L->k, py0 = m->y * L->k;
    const unsigned short *s = glyph_tab[m->gi].shn;
    if (sx * 12 != gw || sy * 12 != gh) return;
    for (y = 0; y < gh; y++) {
        unsigned *row = g_canvas + (size_t)(py0 + y) * g_cw + px0;
        unsigned short bits = s[y / sy];
        for (x = 0; x < gw; x++) row[x] = (bits & (0x800 >> (x / sx))) ? m->fg : m->bg;
    }
}

/* 元の絵の (x0, y0) から w×h を、k 倍にして大きい絵に写す */
static void scale_rect(const LAYOUT *L, int x0, int y0, int w, int h) {
    int x, y, j;
    for (y = y0; y < y0 + h; y++) {
        unsigned *dst = g_canvas + (size_t)y * L->k * g_cw + (size_t)x0 * L->k;
        const unsigned *src = g_mirror + (size_t)y * g_mir_w;
        for (x = x0; x < x0 + w; x++) {
            unsigned c = src[x * L->xs];
            for (j = 0; j < L->k; j++) *dst++ = c;
        }
        dst = g_canvas + (size_t)y * L->k * g_cw + (size_t)x0 * L->k;
        for (j = 1; j < L->k; j++) memcpy(dst + (size_t)j * g_cw, dst, (size_t)w * L->k * 4);
    }
}

static int g_up_y0, g_up_y1;     /* 大きい絵のうち、送り直す行の範囲 */
static MATCH g_prev[MAXMATCH];
static int g_nprev;

static void band(int y0, int y1) {
    if (y0 < g_up_y0) g_up_y0 = y0;
    if (y1 > g_up_y1) g_up_y1 = y1;
}

static void compose(void) {
    LAYOUT L;
    int y, cw, ch, i, full, gh;
    LARGE_INTEGER t0, t1, fq;
    QueryPerformanceCounter(&t0);
    make_layout(&L);
    cw = L.lw * L.k; ch = L.lh * L.k;
    full = g_alldirty;
    if (memcmp(&L, &g_lay, sizeof L)) {
        plog("並べ方: 元 %dx%d → %dx%d（横 %d 画素ずつ）、%d 倍、字は縦 %d 倍", g_w, g_h, L.lw, L.lh, L.xs, L.k, L.rd);
        g_lay = L; full = 1;
    }
    if ((size_t)cw * ch > (size_t)g_canvas_cap) {
        free(g_canvas);
        g_canvas = (unsigned *)malloc((size_t)cw * ch * 4);
        g_canvas_cap = g_canvas ? cw * ch : 0;
        if (!g_canvas) return;
        full = 1;
    }
    if (cw != g_cw || ch != g_ch) full = 1;
    g_cw = cw; g_ch = ch;
    gh = 8 * L.rd;
    if (full) { memset(g_rowdirty, 1, sizeof g_rowdirty); g_nprev = 0; }
    g_dsum[0] = 0;
    for (y = 0; y < L.lh && y < 4096; y++) g_dsum[y + 1] = g_dsum[y] + g_rowdirty[y];
    for (; y < 4096; y++) g_dsum[y + 1] = g_dsum[y];
    g_up_y0 = ch; g_up_y1 = 0;
    /* 変わった行を、そのまま k 倍に広げる */
    for (y = 0; y < L.lh; y++)
        if (g_rowdirty[y]) { scale_rect(&L, 0, y, L.lw, 1); band(y * L.k, (y + 1) * L.k); }
    /* 美咲の字を探して、東雲で描き直す */
    if (cfg_font) find_glyphs(&L, full); else { g_ncand = g_nacc = 0; }
    /* 描き直しをやめた字の場所は、元の絵に戻す（窓の一部の行だけ変わったときも、古い字を残さない） */
    {
        static MATCH gone[MAXMATCH];
        int ngone = 0, j;
        for (i = 0; i < g_nprev; i++) {
            const MATCH *m = &g_prev[i];
            if (!in_list(m, g_acc, g_nacc)) {
                scale_rect(&L, m->x, m->y, 8, gh);
                band(m->y * L.k, (m->y + gh) * L.k);
                gone[ngone++] = *m;
            }
        }
        /* 変わった行にかかる字、新しい字、戻した場所に重なる字を描く */
        for (i = 0; i < g_nacc; i++) {
            const MATCH *m = &g_acc[i];
            int need = window_dirty(m->y, gh) || !in_list(m, g_prev, g_nprev);
            for (j = 0; !need && j < ngone; j++) {
                int dx = gone[j].x - m->x, dy = gone[j].y - m->y;
                if (dx < 8 && dx > -8 && dy < gh && dy > -gh) need = 1;
            }
            if (need) {
                paint_glyph(&L, m);
                band(m->y * L.k, (m->y + gh) * L.k);
            }
        }
    }
    memcpy(g_prev, g_acc, sizeof(MATCH) * g_nacc);
    g_nprev = g_nacc;
    memset(g_rowdirty, 0, sizeof g_rowdirty);
    g_alldirty = 0;
    if (full) { g_up_y0 = 0; g_up_y1 = ch; }
    if (g_up_y1 > g_up_y0) g_canvas_new = 1;
    QueryPerformanceCounter(&t1); QueryPerformanceFrequency(&fq);
    {
        static int nlog;
        if (cfg_log && nlog < 40 && (g_nacc || full)) {
            nlog++;
            wchar_t w[64]; char u8[256]; int n = 0;
            for (i = 0; i < g_nacc && n < 60; i++) w[n++] = glyph_tab[g_acc[i].gi].ucs;
            w[n] = 0;
            WideCharToMultiByte(CP_UTF8, 0, w, -1, u8, sizeof u8, NULL, NULL);
            plog("字: 候補 %d、描き直し %d、%s、送る行 %d〜%d、%.2f ミリ秒 [%s]", g_ncand, g_nacc, full ? "全部" : "変わった行だけ",
                 g_up_y0, g_up_y1, (double)(t1.QuadPart - t0.QuadPart) * 1000.0 / (double)fq.QuadPart, u8);
        }
    }
}

