// -----------------------------------------------------------------------------
// bw_tile_score.v   (Part B datapath, 3 pipeline stages, one tile per clock)
// Per-tile score and baseline update, as golden.score_tiles(),
// golden.update_baseline() and the reset rule of golden.TileEngine.step().
//
// Q8 = value << 8. x = tile mean << 8, b = baseline (Q8, 0..65280).
//   reset frame : b_eff = x (so score = 0, changed = 0), new baseline = x
//   otherwise   : b_eff = b
//   edge_drop  = max(0, bE - xE)
//   grey_shift = max(0, |bY - 128<<8| - |xY - 128<<8|)
//   sat_ok     = (mS <= SAT_MAX) and (xS <= bS + SAT_TOL)
//   raw        = (W_EDGE*edge_drop + W_GREY*grey_shift) >> SCORE_SHIFT
//   score      = sat_ok ? min(raw, 255) : 0
//   changed    = |xY - bY| > T_GLOBAL
//   flagged    = score >= T_FLAG
//   update (not reset, update_frame = 1, and (prev_gate or not flagged)):
//       k = prev_gate ? K_FAST : K_SLOW
//       b = b + ((x - b + ((1 << k) >> 1)) >>> k)        (arithmetic shift)
//
//   stage Q1 : differences, saturation test, changed test, new baselines
//   stage Q2 : weighted sum (two multipliers)
//   stage Q3 : shift, clamp, flag, choose the baseline to write back
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps
module bw_tile_score (
    input  wire        clk,
    input  wire        rst,
    // frame constants
    input  wire        reset_frame,   // this frame is a reset frame
    input  wire        update_frame,  // update_this_frame
    input  wire        prev_gate,     // previous frame's gate
    // registers (docs/contracts.md section 7)
    input  wire [3:0]  k_slow,
    input  wire [3:0]  k_fast,
    input  wire [7:0]  w_edge,
    input  wire [7:0]  w_grey,
    input  wire [4:0]  score_shift,
    input  wire [7:0]  t_flag,
    input  wire [7:0]  sat_max,
    input  wire [15:0] sat_tol,
    input  wire [15:0] t_global,
    // one tile in
    input  wire        in_valid,
    input  wire [11:0] in_idx,
    input  wire        in_last,
    input  wire [7:0]  in_me,         // tile means (0..255)
    input  wire [7:0]  in_my,
    input  wire [7:0]  in_ms,
    input  wire [15:0] in_be,         // stored baselines (Q8)
    input  wire [15:0] in_by,
    input  wire [15:0] in_bs,
    // one tile out
    output reg         out_valid,
    output reg  [11:0] out_idx,
    output reg         out_last,
    output reg  [7:0]  out_score,
    output reg         out_flag,      // score >= T_FLAG
    output reg         out_chg,       // tile counts as changed
    output reg  [15:0] out_be,        // baseline to write back
    output reg  [15:0] out_by,
    output reg  [15:0] out_bs
);

    localparam [15:0] MID_GREY = 16'd32768;   // 128 << 8

    // ======================= stage Q1 =======================
    reg  [15:0] xe, xy, xs;               // x = mean << 8
    reg  [15:0] be, by, bs;               // effective baselines
    reg  [15:0] edge_drop;
    reg  [15:0] dist_b, dist_x;           // |b - 128<<8|, |x - 128<<8|
    reg  [15:0] grey_shift;
    reg  [16:0] s_limit;                  // bS + SAT_TOL (17 bits)
    reg         sat_ok;
    reg  [15:0] dy;                       // |xY - bY|
    reg         chg;
    reg  [3:0]  k;
    reg  [18:0] rnd;                      // (1 << k) >> 1
    reg  signed [18:0] de, dyy, ds;       // x - b + rnd
    reg  signed [18:0] sh_e, sh_y, sh_s;  // >>> k
    reg  signed [18:0] nb_e, nb_y, nb_s;  // b + delta

    // Q1 arithmetic: effective baseline and features
    always @(*) begin
        xe = {in_me, 8'd0};
        xy = {in_my, 8'd0};
        xs = {in_ms, 8'd0};
        if (reset_frame) begin
            be = xe;  by = xy;  bs = xs;
        end else begin
            be = in_be;  by = in_by;  bs = in_bs;
        end
    end

    // Q1 arithmetic: edge drop, grey shift, saturation and change tests
    always @(*) begin
        edge_drop  = (be > xe) ? (be - xe) : 16'd0;
        dist_b     = (by >= MID_GREY) ? (by - MID_GREY) : (MID_GREY - by);
        dist_x     = (xy >= MID_GREY) ? (xy - MID_GREY) : (MID_GREY - xy);
        grey_shift = (dist_b > dist_x) ? (dist_b - dist_x) : 16'd0;
        s_limit    = {1'b0, bs} + {1'b0, sat_tol};
        sat_ok     = (in_ms <= sat_max) && ({1'b0, xs} <= s_limit);
        dy         = (xy >= by) ? (xy - by) : (by - xy);
        chg        = (dy > t_global);
    end

    // Q1 arithmetic: baseline update candidate b + ((x - b + rnd) >>> k)
    always @(*) begin
        k    = prev_gate ? k_fast : k_slow;
        rnd  = (19'd1 << k) >> 1;
        de   = $signed({3'b000, xe}) - $signed({3'b000, be}) + $signed(rnd);
        dyy  = $signed({3'b000, xy}) - $signed({3'b000, by}) + $signed(rnd);
        ds   = $signed({3'b000, xs}) - $signed({3'b000, bs}) + $signed(rnd);
        sh_e = de  >>> k;
        sh_y = dyy >>> k;
        sh_s = ds  >>> k;
        nb_e = $signed({3'b000, be}) + sh_e;
        nb_y = $signed({3'b000, by}) + sh_y;
        nb_s = $signed({3'b000, bs}) + sh_s;
    end

    // Q1 registers
    reg         q1_valid, q1_last, q1_sat_ok, q1_chg, q1_reset;
    reg  [11:0] q1_idx;
    reg  [15:0] q1_edge, q1_grey;
    reg  [15:0] q1_be, q1_by, q1_bs;      // baseline kept if no update
    reg  [15:0] q1_ue, q1_uy, q1_us;      // baseline if updated
    reg  [15:0] q1_xe, q1_xy, q1_xs;      // x, written on a reset frame
    always @(posedge clk) begin
        if (rst)
            q1_valid <= 1'b0;
        else
            q1_valid <= in_valid;
        q1_idx    <= in_idx;
        q1_last   <= in_last;
        q1_edge   <= edge_drop;
        q1_grey   <= grey_shift;
        q1_sat_ok <= sat_ok;
        q1_chg    <= chg;
        q1_reset  <= reset_frame;
        q1_be     <= be;
        q1_by     <= by;
        q1_bs     <= bs;
        q1_ue     <= nb_e[15:0];
        q1_uy     <= nb_y[15:0];
        q1_us     <= nb_s[15:0];
        q1_xe     <= xe;
        q1_xy     <= xy;
        q1_xs     <= xs;
    end

    // ======================= stage Q2 =======================
    reg  [24:0] wsum;                     // <= 255*65280 + 255*32768 < 2^25
    always @(*) begin
        wsum = w_edge * q1_edge + w_grey * q1_grey;
    end

    reg         q2_valid, q2_last, q2_sat_ok, q2_chg, q2_reset;
    reg  [11:0] q2_idx;
    reg  [24:0] q2_wsum;
    reg  [15:0] q2_be, q2_by, q2_bs, q2_ue, q2_uy, q2_us, q2_xe, q2_xy, q2_xs;
    always @(posedge clk) begin
        if (rst)
            q2_valid <= 1'b0;
        else
            q2_valid <= q1_valid;
        q2_idx    <= q1_idx;
        q2_last   <= q1_last;
        q2_wsum   <= wsum;
        q2_sat_ok <= q1_sat_ok;
        q2_chg    <= q1_chg;
        q2_reset  <= q1_reset;
        q2_be <= q1_be;  q2_by <= q1_by;  q2_bs <= q1_bs;
        q2_ue <= q1_ue;  q2_uy <= q1_uy;  q2_us <= q1_us;
        q2_xe <= q1_xe;  q2_xy <= q1_xy;  q2_xs <= q1_xs;
    end

    // ======================= stage Q3 =======================
    reg  [24:0] raw;
    reg  [7:0]  score;
    reg         flag;
    reg         do_update;
    reg  [15:0] wb_e, wb_y, wb_s;

    // Q3 arithmetic: shift, clamp to 255, saturation gate, flag
    always @(*) begin
        raw = q2_wsum >> score_shift;
        if (!q2_sat_ok)
            score = 8'd0;
        else if (raw > 25'd255)
            score = 8'd255;
        else
            score = raw[7:0];
        flag = (score >= t_flag);
    end

    // Q3 arithmetic: which baseline is written back
    always @(*) begin
        do_update = update_frame && (prev_gate || !flag);
        if (q2_reset) begin
            wb_e = q2_xe;  wb_y = q2_xy;  wb_s = q2_xs;      // reset frame: b = x
        end else if (do_update) begin
            wb_e = q2_ue;  wb_y = q2_uy;  wb_s = q2_us;      // learn the background
        end else begin
            wb_e = q2_be;  wb_y = q2_by;  wb_s = q2_bs;      // frozen (flagged or no update)
        end
    end

    // Q3 registers (module outputs)
    always @(posedge clk) begin
        if (rst)
            out_valid <= 1'b0;
        else
            out_valid <= q2_valid;
        out_idx   <= q2_idx;
        out_last  <= q2_last;
        out_score <= score;
        out_flag  <= flag;
        out_chg   <= q2_chg;
        out_be    <= wb_e;
        out_by    <= wb_y;
        out_bs    <= wb_s;
    end

endmodule
