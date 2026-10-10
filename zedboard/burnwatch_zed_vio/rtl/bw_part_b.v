// -----------------------------------------------------------------------------
// bw_part_b.v   PART B: tile scorer with baseline memory and frame gate
// Hardware for golden.TileEngine.step() after the tile features are known:
// score every tile, count changed tiles, decide the frame gate, and keep the
// per-tile background baselines (bE, bY, bS) from frame to frame.
//
//   tiles --> [R] baseline RAM read --> bw_tile_score (Q1..Q3) --> baseline RAM write
//                                                               --> score RAM write
//                                                               --> frame statistics
//   after the last tile: gate = changed > GATE_TILES, prev_gate = gate
//
// Memories (3,600 tiles used):
//   baseline RAM 4096 x 48 = {bE, bY, bS}   (persistent state, Q8)
//   score RAM    4096 x 8                   (scores of the last frame)
// Both read ports are free between frames, so the VIO can read back any tile.
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps
module bw_part_b #(
    parameter TILES_X = 80,
    parameter TILES_Y = 45
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        run_clear,     // new test: clear the displayed results
    input  wire        frame_start,   // 1-cycle pulse: new frame, latch cfg
    input  wire        cfg_reset,     // this frame is a reset frame
    input  wire        cfg_update,    // update_this_frame
    // registers
    input  wire [3:0]  k_slow,
    input  wire [3:0]  k_fast,
    input  wire [7:0]  w_edge,
    input  wire [7:0]  w_grey,
    input  wire [4:0]  score_shift,
    input  wire [7:0]  t_flag,
    input  wire [7:0]  sat_max,
    input  wire [15:0] sat_tol,
    input  wire [15:0] t_global,
    input  wire [11:0] gate_tiles,
    // tile stream in
    input  wire        t_valid,
    input  wire [11:0] t_idx,
    input  wire        t_last,
    input  wire [7:0]  t_me,
    input  wire [7:0]  t_my,
    input  wire [7:0]  t_ms,
    // frame results
    output reg         frame_done,    // 1-cycle pulse, results below are final
    output reg         gate,          // gate of the last frame (display)
    output reg  [15:0] frame_count,   // frames since the last reset frame (reset = 1)
    output reg  [11:0] changed,       // changed tiles in the last frame
    output reg  [11:0] flagged,       // tiles with score >= T_FLAG
    output reg  [19:0] score_sum,     // sum of the 3,600 scores
    output reg  [7:0]  max_score,     // highest score
    output reg  [11:0] max_idx,       // first tile with the highest score
    // read-back of one tile (one clock latency)
    input  wire [11:0] rd_idx,
    output wire [7:0]  rd_score,
    output wire [15:0] rd_be,
    output wire [15:0] rd_by,
    output wire [15:0] rd_bs
);

    // ---------------- frame configuration and engine state ----------------
    reg         f_reset, f_update;
    reg         prev_gate;            // gate of the previous frame (engine state)

    always @(posedge clk) begin
        if (rst) begin
            f_reset  <= 1'b0;
            f_update <= 1'b0;
        end else if (frame_start) begin
            f_reset  <= cfg_reset;
            f_update <= cfg_update;
        end
    end

    // ---------------- stage R: baseline read ----------------
    reg         r_valid, r_last;
    reg  [11:0] r_idx;
    reg  [7:0]  r_me, r_my, r_ms;
    wire [47:0] base_q;
    wire [11:0] base_raddr = t_valid ? t_idx : rd_idx;   // pipeline first, read-back when idle

    always @(posedge clk) begin
        if (rst)
            r_valid <= 1'b0;
        else
            r_valid <= t_valid;
        r_idx  <= t_idx;
        r_last <= t_last;
        r_me   <= t_me;
        r_my   <= t_my;
        r_ms   <= t_ms;
    end

    // ---------------- scorer ----------------
    wire        s_valid, s_last, s_flag, s_chg;
    wire [11:0] s_idx;
    wire [7:0]  s_score;
    wire [15:0] s_be, s_by, s_bs;

    bw_tile_score u_score (
        .clk(clk), .rst(rst),
        .reset_frame(f_reset), .update_frame(f_update), .prev_gate(prev_gate),
        .k_slow(k_slow), .k_fast(k_fast), .w_edge(w_edge), .w_grey(w_grey),
        .score_shift(score_shift), .t_flag(t_flag), .sat_max(sat_max),
        .sat_tol(sat_tol), .t_global(t_global),
        .in_valid(r_valid), .in_idx(r_idx), .in_last(r_last),
        .in_me(r_me), .in_my(r_my), .in_ms(r_ms),
        .in_be(base_q[47:32]), .in_by(base_q[31:16]), .in_bs(base_q[15:0]),
        .out_valid(s_valid), .out_idx(s_idx), .out_last(s_last),
        .out_score(s_score), .out_flag(s_flag), .out_chg(s_chg),
        .out_be(s_be), .out_by(s_by), .out_bs(s_bs)
    );

    // ---------------- memories ----------------
    bw_sdp_ram #(.DW(48), .AW(12)) u_base_ram (
        .clk(clk),
        .we(s_valid), .waddr(s_idx), .wdata({s_be, s_by, s_bs}),
        .re(1'b1), .raddr(base_raddr), .rdata(base_q)
    );

    bw_sdp_ram #(.DW(8), .AW(12)) u_score_ram (
        .clk(clk),
        .we(s_valid), .waddr(s_idx), .wdata(s_score),
        .re(1'b1), .raddr(rd_idx), .rdata(rd_score)
    );

    assign rd_be = base_q[47:32];
    assign rd_by = base_q[31:16];
    assign rd_bs = base_q[15:0];

    // ---------------- frame statistics ----------------
    reg         fin;                       // the last tile was counted last cycle

    always @(posedge clk) begin
        if (rst || run_clear || frame_start) begin
            changed   <= 12'd0;
            flagged   <= 12'd0;
            score_sum <= 20'd0;
            max_score <= 8'd0;
            max_idx   <= 12'd0;
            fin       <= 1'b0;
        end else begin
            fin <= s_valid && s_last;
            if (s_valid) begin
                changed   <= changed + {11'd0, s_chg};
                flagged   <= flagged + {11'd0, s_flag};
                score_sum <= score_sum + {12'd0, s_score};
                if (s_score > max_score) begin
                    max_score <= s_score;
                    max_idx   <= s_idx;
                end
            end
        end
    end

    // ---------------- frame end: gate, prev_gate, frame counter ----------------
    reg         gate_now;

    always @(*) begin
        gate_now = (changed > gate_tiles);
    end

    always @(posedge clk) begin
        if (rst) begin
            frame_done  <= 1'b0;
            gate        <= 1'b0;
            prev_gate   <= 1'b0;
            frame_count <= 16'd0;
        end else begin
            frame_done <= fin;
            if (run_clear)
                gate <= 1'b0;
            if (fin) begin
                gate        <= gate_now;
                prev_gate   <= gate_now;
                frame_count <= f_reset ? 16'd1 : frame_count + 16'd1;
            end
        end
    end

endmodule
