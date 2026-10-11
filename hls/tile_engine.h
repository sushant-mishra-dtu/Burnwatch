// BurnWatch PL tile engine (Vitis HLS). Spec: detector/golden.py, FULL mode. Interface: docs/contracts.md section 7.
#ifndef BURNWATCH_TILE_ENGINE_H
#define BURNWATCH_TILE_ENGINE_H

#include <ap_int.h>

#include "config.h"

void tile_engine(
    const ap_uint<32> *frame,      // m_axi gmem0: 921600 words, R | G<<8 | B<<16, row-major
    ap_uint<8>        *scores,     // m_axi gmem1: 3600 bytes, row-major 45x80
    ap_uint<1>  reset,             // s_axilite control, register order = Params order
    ap_uint<1>  update_this_frame,
    ap_uint<4>  k_slow,      ap_uint<4>  k_fast,
    ap_uint<8>  w_edge,      ap_uint<8>  w_grey,
    ap_uint<5>  score_shift, ap_uint<8>  t_flag,
    ap_uint<8>  sat_max,     ap_uint<16> sat_tol,
    ap_uint<16> t_global,    ap_uint<12> gate_tiles,
    ap_uint<1>  *gate_out,
    ap_uint<12> *changed_out,
    ap_uint<32> *frame_count);

#endif  // BURNWATCH_TILE_ENGINE_H
