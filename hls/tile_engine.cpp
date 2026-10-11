// BurnWatch PL tile engine. Spec: detector/golden.py (spec v1), FULL mode, bit for bit.
//
// One pass over the frame, one pixel per clock:
//   - Y and S of pixel (r, c) go to the tile of (r, c) at once.
//   - E needs the 3x3 neighbourhood, so it is computed when pixel (r, c) arrives for the centre (r-1, c-1) and goes
//     to the tile of the centre. Only interior centres are computed; border E = 0 adds nothing to a tile sum.
//   - A tile row ty is complete when its E is (end of input row 16*ty + 16, or the last row for ty = 44). Then a
//     short loop over its 80 tiles does means, score, changed count and the baseline update, and writes 80 scores.
// Y/S and E of two neighbouring tile rows overlap in time, so the tile accumulators have two slots (ty & 1).
#include "tile_engine.h"

typedef ap_uint<8> u8;
typedef ap_uint<12> u12;  // sum of 16 pixels of one row (<= 4080), or a tile count
typedef ap_uint<16> u16;  // sum of a 16x16 tile (<= 65280), or a Q8 value

static const int MID_GREY_Q8 = 128 << 8;

// Persistent state (contracts.md section 7): Q8 baselines and the previous frame's gate.
static u16 bE[N_TILES], bY[N_TILES], bS[N_TILES];
static bool prev_gate = false;
static ap_uint<32> calls = 0;

static ap_uint<17> absdiff(u16 a, u16 b) {
    return a > b ? ap_uint<17>(a - b) : ap_uint<17>(b - a);
}

// b += (x - b + ((1 << k) >> 1)) >> k, with an arithmetic shift. k = 0 snaps b = x (contracts.md F7).
static u16 update(u16 b, u16 x, ap_uint<4> k) {
    const ap_int<19> half = (ap_int<19>(1) << k) >> 1;
    const ap_int<19> delta = (ap_int<19>(x) - ap_int<19>(b) + half) >> k;
    return u16(ap_int<19>(b) + delta);
}

static void finish_tile_row(int ty, u16 accE[2][TILES_X], u16 accY[2][TILES_X], u16 accS[2][TILES_X],
                            ap_uint<8> *scores, bool rst, bool upd, bool pg, ap_uint<4> k,
                            ap_uint<8> w_edge, ap_uint<8> w_grey, ap_uint<5> score_shift, ap_uint<8> t_flag,
                            ap_uint<8> sat_max, ap_uint<16> sat_tol, ap_uint<16> t_global, u12 &changed) {
    const int slot = ty & 1;
TILES:
    for (int tx = 0; tx < TILES_X; tx++) {
#pragma HLS PIPELINE II = 1
#pragma HLS DEPENDENCE variable = bE inter false
#pragma HLS DEPENDENCE variable = bY inter false
#pragma HLS DEPENDENCE variable = bS inter false
        const int i = ty * TILES_X + tx;
        const u8 mE = accE[slot][tx] >> 8, mY = accY[slot][tx] >> 8, mS = accS[slot][tx] >> 8;
        accE[slot][tx] = 0;
        accY[slot][tx] = 0;
        accS[slot][tx] = 0;
        const u16 xE = u16(mE) << 8, xY = u16(mY) << 8, xS = u16(mS) << 8;

        // Reset frame (contracts.md F4): b = x before scoring.
        const u16 oE = rst ? xE : bE[i], oY = rst ? xY : bY[i], oS = rst ? xS : bS[i];

        const ap_uint<17> edge_drop = oE > xE ? ap_uint<17>(oE - xE) : ap_uint<17>(0);
        const ap_int<18> grey = ap_int<18>(absdiff(oY, MID_GREY_Q8)) - ap_int<18>(absdiff(xY, MID_GREY_Q8));
        const ap_uint<17> grey_shift = grey > 0 ? ap_uint<17>(grey) : ap_uint<17>(0);
        const bool sat_ok = (mS <= sat_max) && (ap_uint<18>(xS) <= ap_uint<18>(oS) + sat_tol);
        const ap_uint<26> raw = (ap_uint<26>(w_edge) * edge_drop + ap_uint<26>(w_grey) * grey_shift) >> score_shift;
        const u8 score = !sat_ok ? u8(0) : raw > 255 ? u8(255) : u8(raw);
        if (absdiff(xY, oY) > t_global) changed++;
        scores[i] = score;

        // Baseline update with the previous frame's gate; flagged tiles stay frozen unless it was gated.
        const bool move = upd && (pg || score < t_flag);
        bE[i] = move ? update(oE, xE, k) : oE;
        bY[i] = move ? update(oY, xY, k) : oY;
        bS[i] = move ? update(oS, xS, k) : oS;
    }
}

void tile_engine(const ap_uint<32> *frame, ap_uint<8> *scores, ap_uint<1> reset, ap_uint<1> update_this_frame,
                 ap_uint<4> k_slow, ap_uint<4> k_fast, ap_uint<8> w_edge, ap_uint<8> w_grey,
                 ap_uint<5> score_shift, ap_uint<8> t_flag, ap_uint<8> sat_max, ap_uint<16> sat_tol,
                 ap_uint<16> t_global, ap_uint<12> gate_tiles, ap_uint<1> *gate_out, ap_uint<12> *changed_out,
                 ap_uint<32> *frame_count) {
#pragma HLS INTERFACE m_axi port = frame bundle = gmem0 offset = slave depth = 921600 max_read_burst_length = 256
#pragma HLS INTERFACE m_axi port = scores bundle = gmem1 offset = slave depth = 3600
#pragma HLS INTERFACE s_axilite port = frame bundle = control
#pragma HLS INTERFACE s_axilite port = scores bundle = control
#pragma HLS INTERFACE s_axilite port = reset bundle = control
#pragma HLS INTERFACE s_axilite port = update_this_frame bundle = control
#pragma HLS INTERFACE s_axilite port = k_slow bundle = control
#pragma HLS INTERFACE s_axilite port = k_fast bundle = control
#pragma HLS INTERFACE s_axilite port = w_edge bundle = control
#pragma HLS INTERFACE s_axilite port = w_grey bundle = control
#pragma HLS INTERFACE s_axilite port = score_shift bundle = control
#pragma HLS INTERFACE s_axilite port = t_flag bundle = control
#pragma HLS INTERFACE s_axilite port = sat_max bundle = control
#pragma HLS INTERFACE s_axilite port = sat_tol bundle = control
#pragma HLS INTERFACE s_axilite port = t_global bundle = control
#pragma HLS INTERFACE s_axilite port = gate_tiles bundle = control
#pragma HLS INTERFACE s_axilite port = gate_out bundle = control
#pragma HLS INTERFACE s_axilite port = changed_out bundle = control
#pragma HLS INTERFACE s_axilite port = frame_count bundle = control
#pragma HLS INTERFACE s_axilite port = return bundle = control

    const bool rst = reset;
    const bool upd = !rst && update_this_frame;
    const bool pg = prev_gate;
    const ap_uint<4> k = pg ? k_fast : k_slow;
    u12 changed = 0;

    u8 lb1[IMG_W], lb2[IMG_W];  // Y of input rows r-1 and r-2
    u16 accE[2][TILES_X], accY[2][TILES_X], accS[2][TILES_X];
#pragma HLS ARRAY_PARTITION variable = accE complete dim = 1
#pragma HLS ARRAY_PARTITION variable = accY complete dim = 1
#pragma HLS ARRAY_PARTITION variable = accS complete dim = 1

CLEAR:
    for (int tx = 0; tx < TILES_X; tx++) {
#pragma HLS PIPELINE II = 1
        for (int s = 0; s < 2; s++) accE[s][tx] = accY[s][tx] = accS[s][tx] = 0;
    }

ROWS:
    for (int r = 0; r < IMG_H; r++) {
        u8 w[3][3];  // Y window: rows r-2, r-1, r; columns c-2, c-1, c
#pragma HLS ARRAY_PARTITION variable = w complete dim = 0
        u12 sumY = 0, sumS = 0, sumE = 0;
    COLS:
        for (int c = 0; c < IMG_W; c++) {
#pragma HLS PIPELINE II = 1
#pragma HLS DEPENDENCE variable = lb1 inter false
#pragma HLS DEPENDENCE variable = lb2 inter false
#pragma HLS DEPENDENCE variable = accE inter false
#pragma HLS DEPENDENCE variable = accY inter false
#pragma HLS DEPENDENCE variable = accS inter false
            const ap_uint<32> px = frame[r * IMG_W + c];
            const u8 R = px(7, 0), G = px(15, 8), B = px(23, 16);
            const u8 y = (ap_uint<16>(77) * R + ap_uint<16>(150) * G + ap_uint<16>(29) * B) >> 8;
            const u8 mx = R > G ? (R > B ? R : B) : (G > B ? G : B);
            const u8 mn = R < G ? (R < B ? R : B) : (G < B ? G : B);

            const u8 above2 = lb2[c], above1 = lb1[c];
            lb2[c] = above1;
            lb1[c] = y;
            for (int i = 0; i < 3; i++) {
                w[i][0] = w[i][1];
                w[i][1] = w[i][2];
            }
            w[0][2] = above2;
            w[1][2] = above1;
            w[2][2] = y;

            sumY += y;
            sumS += u8(mx - mn);
            if ((c & 15) == 15) {
                const int slot = (r >> 4) & 1;
                accY[slot][c >> 4] += sumY;
                accS[slot][c >> 4] += sumS;
                sumY = 0;
                sumS = 0;
            }

            if (r >= 2) {
                if (c >= 2) {  // interior centre (r-1, c-1)
                    const ap_int<12> gx = (ap_int<12>(w[0][2]) + 2 * ap_int<12>(w[1][2]) + ap_int<12>(w[2][2])) -
                                          (ap_int<12>(w[0][0]) + 2 * ap_int<12>(w[1][0]) + ap_int<12>(w[2][0]));
                    const ap_int<12> gy = (ap_int<12>(w[2][0]) + 2 * ap_int<12>(w[2][1]) + ap_int<12>(w[2][2])) -
                                          (ap_int<12>(w[0][0]) + 2 * ap_int<12>(w[0][1]) + ap_int<12>(w[0][2]));
                    const ap_uint<12> ax = gx < 0 ? ap_uint<12>(-gx) : ap_uint<12>(gx);
                    const ap_uint<12> ay = gy < 0 ? ap_uint<12>(-gy) : ap_uint<12>(gy);
                    sumE += u8((ax + ay) >> 3);
                }
                // Centre column c-1 closes a tile at c % 16 == 0; tile 79 closes at the last column.
                if ((c >= TILE && (c & 15) == 0) || c == IMG_W - 1) {
                    const int slot = ((r - 1) >> 4) & 1;
                    accE[slot][(c - 1) >> 4] += sumE;
                    sumE = 0;
                }
            }
        }
        if (r >= TILE && (r & 15) == 0)
            finish_tile_row((r >> 4) - 1, accE, accY, accS, scores, rst, upd, pg, k, w_edge, w_grey, score_shift,
                            t_flag, sat_max, sat_tol, t_global, changed);
    }
    finish_tile_row(TILES_Y - 1, accE, accY, accS, scores, rst, upd, pg, k, w_edge, w_grey, score_shift, t_flag,
                    sat_max, sat_tol, t_global, changed);

    const bool gate = changed > gate_tiles;
    prev_gate = gate;
    calls = rst ? ap_uint<32>(1) : ap_uint<32>(calls + 1);
    *gate_out = gate;
    *changed_out = changed;
    *frame_count = calls;
}
