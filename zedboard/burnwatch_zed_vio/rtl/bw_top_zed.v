// -----------------------------------------------------------------------------
// bw_top_zed.v   ZedBoard top level (xc7z020clg484-1)
//   GCLK : 100 MHz on-board oscillator, pin Y9 (LVCMOS33, bank 13)
//   LD7..LD0 : status mirror (optional; everything is also on the VIO)
// The design runs directly on GCLK (10 ns), so no Clocking Wizard / MMCM is
// needed. Reset = 16-clock power-on reset OR the VIO reset probe.
// The VIO core (vio_0) is created by scripts/create_project.tcl.
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps
module bw_top_zed (
    input  wire       GCLK,
    output wire [7:0] LD
);

    wire clk = GCLK;                  // Vivado inserts IBUF + BUFG

    // ---------------- tile-engine register defaults (detector/config.py) -------
    localparam [3:0]  K_SLOW      = 4'd6;
    localparam [3:0]  K_FAST      = 4'd0;
    localparam [7:0]  W_EDGE      = 8'd4;
    localparam [7:0]  W_GREY      = 8'd4;
    localparam [4:0]  SCORE_SHIFT = 5'd8;
    localparam [7:0]  SAT_MAX     = 8'd40;
    localparam [15:0] SAT_TOL     = 16'd1024;    // 4 << 8
    localparam [15:0] T_GLOBAL    = 16'd6144;    // 24 << 8
    localparam [11:0] GATE_TILES  = 12'd1440;
    // T_FLAG comes from the VIO (initial value 40)

    // ---------------- VIO probe nets ----------------
    // keep: these net names become the probe names in the .ltx file
    (* keep = "true" *) wire        vio_rst;
    (* keep = "true" *) wire        vio_start;
    (* keep = "true" *) wire [1:0]  vio_part_sel;
    (* keep = "true" *) wire [2:0]  vio_test_sel;
    (* keep = "true" *) wire [11:0] vio_tile_sel;
    (* keep = "true" *) wire [7:0]  vio_t_flag;

    (* keep = "true" *) wire        busy, done, result_valid, error, gate, rd_err, heartbeat;
    (* keep = "true" *) wire [3:0]  err_code, frames_run;
    (* keep = "true" *) wire [7:0]  run_id, gate_hist, max_score, rd_me, rd_my, rd_ms, rd_score;
    (* keep = "true" *) wire [11:0] changed, flagged, max_idx;
    (* keep = "true" *) wire [15:0] frame_count, rd_be, rd_by, rd_bs;
    (* keep = "true" *) wire [19:0] score_sum, sum_e, sum_y, sum_s;
    (* keep = "true" *) wire [31:0] cycles;

    // ---------------- power-on reset + VIO reset ----------------
    reg  [15:0] por_sr = 16'hFFFF;    // all ones after configuration
    reg         rst    = 1'b1;
    reg  [26:0] hb_cnt = 27'd0;       // heartbeat counter (~1.34 s period)

    always @(posedge clk) begin
        por_sr <= {por_sr[14:0], 1'b0};
        rst    <= por_sr[15] | vio_rst;
    end

    // Heartbeat: shows on the VIO / LD0 that the clock is running
    always @(posedge clk) begin
        hb_cnt <= hb_cnt + 27'd1;
    end

    assign heartbeat = hb_cnt[26];

    // ---------------- BurnWatch tile engine + demo harness ----------------
    bw_system u_sys (
        .clk(clk), .rst(rst),
        .start(vio_start), .part_sel(vio_part_sel), .test_sel(vio_test_sel),
        .tile_sel(vio_tile_sel), .stim_pause(1'b0),
        .k_slow(K_SLOW), .k_fast(K_FAST), .w_edge(W_EDGE), .w_grey(W_GREY),
        .score_shift(SCORE_SHIFT), .t_flag(vio_t_flag), .sat_max(SAT_MAX),
        .sat_tol(SAT_TOL), .t_global(T_GLOBAL), .gate_tiles(GATE_TILES),
        .busy(busy), .done(done), .result_valid(result_valid),
        .error(error), .err_code(err_code), .run_id(run_id),
        .frames_run(frames_run), .gate_hist(gate_hist), .cycles(cycles),
        .gate(gate), .changed(changed), .flagged(flagged), .score_sum(score_sum),
        .max_score(max_score), .max_idx(max_idx), .frame_count(frame_count),
        .sum_e(sum_e), .sum_y(sum_y), .sum_s(sum_s),
        .rd_err(rd_err), .rd_me(rd_me), .rd_my(rd_my), .rd_ms(rd_ms),
        .rd_score(rd_score), .rd_be(rd_be), .rd_by(rd_by), .rd_bs(rd_bs)
    );

    // ---------------- VIO core ----------------
    vio_0 u_vio (
        .clk        (clk),
        .probe_in0  (busy),
        .probe_in1  (done),
        .probe_in2  (result_valid),
        .probe_in3  (error),
        .probe_in4  (err_code),
        .probe_in5  (run_id),
        .probe_in6  (frames_run),
        .probe_in7  (gate_hist),
        .probe_in8  (gate),
        .probe_in9  (changed),
        .probe_in10 (flagged),
        .probe_in11 (score_sum),
        .probe_in12 (max_score),
        .probe_in13 (max_idx),
        .probe_in14 (frame_count),
        .probe_in15 (sum_e),
        .probe_in16 (sum_y),
        .probe_in17 (sum_s),
        .probe_in18 (rd_err),
        .probe_in19 (rd_me),
        .probe_in20 (rd_my),
        .probe_in21 (rd_ms),
        .probe_in22 (rd_score),
        .probe_in23 (rd_be),
        .probe_in24 (rd_by),
        .probe_in25 (rd_bs),
        .probe_in26 (cycles),
        .probe_in27 (heartbeat),
        .probe_out0 (vio_rst),
        .probe_out1 (vio_start),
        .probe_out2 (vio_part_sel),
        .probe_out3 (vio_test_sel),
        .probe_out4 (vio_tile_sel),
        .probe_out5 (vio_t_flag)
    );

    // ---------------- LEDs ----------------
    assign LD[0] = heartbeat;
    assign LD[1] = busy;
    assign LD[2] = done;
    assign LD[3] = result_valid;
    assign LD[4] = error;
    assign LD[5] = gate;
    assign LD[6] = (flagged != 12'd0);
    assign LD[7] = rd_err;

endmodule
