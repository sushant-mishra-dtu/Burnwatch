// -----------------------------------------------------------------------------
// bw_system.v   Integrated BurnWatch tile engine + demo test harness
// Everything on the FPGA except the clock pin, power-on reset and the VIO core
// (those are in bw_top_zed.v). The testbench simulates this module directly.
//
//                     +-------------+      +-------------------+
//   bw_stim_gen ----->|   PART A    |--+-->|                   |
//   (SIMULATED        | pixels ->   |  |   |      PART B       |--> scores, gate,
//    camera frames)   | tile feats  |  |   | tile scorer +     |    baselines,
//                     +-------------+  |   | baseline memory   |    statistics
//   bw_tile_vec_gen -------------------+-->| + frame gate      |
//   (SIMULATED tile vectors)   source mux  +-------------------+
//                                   |
//                                   +--> bw_feat_store (feature RAM + sums)
//   bw_ctrl + bw_test_rom: start/busy/done/error, frame sequencing
//
// part 0: stimulus -> Part A            (Part B idle, its state untouched)
// part 1: vectors  -> Part B            (Part A idle)
// part 2: stimulus -> Part A -> Part B  (the real detector data path)
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps
module bw_system #(
    parameter IMG_W     = 1280,
    parameter IMG_H     = 720,
    parameter TILES_X   = 80,
    parameter TILES_Y   = 45,
    parameter SMOKE_X0  = 480, parameter SMOKE_X1 = 800,
    parameter SMOKE_Y0  = 240, parameter SMOKE_Y1 = 480,
    parameter CLOTH_X0  = 160, parameter CLOTH_X1 = 320,
    parameter CLOTH_Y0  = 96,  parameter CLOTH_Y1 = 224,
    parameter PATCH_TX0 = 30,  parameter PATCH_TX1 = 50,
    parameter PATCH_TY0 = 15,  parameter PATCH_TY1 = 30,
    parameter [31:0] FRAME_TIMEOUT = 32'd2000000
) (
    input  wire        clk,
    input  wire        rst,
    // control
    input  wire        start,
    input  wire [1:0]  part_sel,
    input  wire [2:0]  test_sel,
    input  wire [11:0] tile_sel,
    input  wire        stim_pause,    // test hook (0 on the board)
    // tile-engine registers (docs/contracts.md section 7)
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
    // status
    output wire        busy,
    output wire        done,
    output wire        result_valid,
    output wire        error,
    output wire [3:0]  err_code,
    output wire [7:0]  run_id,
    output wire [3:0]  frames_run,
    output wire [7:0]  gate_hist,
    output wire [31:0] cycles,
    // Part B results (last frame)
    output wire        gate,
    output wire [11:0] changed,
    output wire [11:0] flagged,
    output wire [19:0] score_sum,
    output wire [7:0]  max_score,
    output wire [11:0] max_idx,
    output wire [15:0] frame_count,
    // Part A / tile-feature results (last frame)
    output wire [19:0] sum_e,
    output wire [19:0] sum_y,
    output wire [19:0] sum_s,
    // read-back of tile tile_sel
    output wire        rd_err,
    output wire [7:0]  rd_me,
    output wire [7:0]  rd_my,
    output wire [7:0]  rd_ms,
    output wire [7:0]  rd_score,
    output wire [15:0] rd_be,
    output wire [15:0] rd_by,
    output wire [15:0] rd_bs
);

    localparam N_TILES = TILES_X * TILES_Y;

    // ---------------- controller and test table ----------------
    wire [1:0]  run_part;
    wire [2:0]  run_test, fidx;
    wire        run_clear, frame_start;
    wire        rom_test_ok, rom_reset, rom_update, rom_lights, rom_cloth;
    wire [3:0]  rom_n_frames;
    wire [2:0]  rom_smoke;
    wire        frame_done;
    wire        b_frame_done, a_frame_done;

    bw_test_rom u_rom (
        .part(run_part), .test(run_test), .fidx(fidx),
        .test_ok(rom_test_ok), .n_frames(rom_n_frames),
        .f_reset(rom_reset), .f_update(rom_update),
        .f_smoke(rom_smoke), .f_lights(rom_lights), .f_cloth(rom_cloth)
    );

    bw_ctrl #(.FRAME_TIMEOUT(FRAME_TIMEOUT)) u_ctrl (
        .clk(clk), .rst(rst),
        .start(start), .part_sel(part_sel), .test_sel(test_sel),
        .rom_test_ok(rom_test_ok), .rom_n_frames(rom_n_frames),
        .frame_done(frame_done), .frame_gate(gate),
        .run_part(run_part), .run_test(run_test), .fidx(fidx),
        .run_clear(run_clear), .frame_start(frame_start),
        .busy(busy), .done(done), .error(error), .err_code(err_code),
        .run_id(run_id), .frames_run(frames_run), .gate_hist(gate_hist),
        .cycles(cycles)
    );

    assign result_valid = done && !error;

    // ---------------- part selection: who gets the frame_start ----------------
    reg  fs_a, fs_vec, fs_b;          // frame_start for each block
    reg  use_b;                       // Part B takes part in this test

    always @(*) begin
        fs_a   = frame_start && ((run_part == 2'd0) || (run_part == 2'd2));
        fs_vec = frame_start &&  (run_part == 2'd1);
        fs_b   = frame_start && ((run_part == 2'd1) || (run_part == 2'd2));
        use_b  = (run_part == 2'd1) || (run_part == 2'd2);
    end

    // ---------------- SIMULATED INPUT: camera frames ----------------
    wire        px_valid, px_ready;
    wire [23:0] px_rgb;

    bw_stim_gen #(
        .IMG_W(IMG_W), .IMG_H(IMG_H),
        .SMOKE_X0(SMOKE_X0), .SMOKE_X1(SMOKE_X1), .SMOKE_Y0(SMOKE_Y0), .SMOKE_Y1(SMOKE_Y1),
        .CLOTH_X0(CLOTH_X0), .CLOTH_X1(CLOTH_X1), .CLOTH_Y0(CLOTH_Y0), .CLOTH_Y1(CLOTH_Y1)
    ) u_stim (
        .clk(clk), .rst(rst), .frame_start(fs_a),
        .scene_smoke(rom_smoke), .scene_lights(rom_lights), .scene_cloth(rom_cloth),
        .pause(stim_pause),
        .m_valid(px_valid), .m_ready(px_ready), .m_rgb(px_rgb)
    );

    // ---------------- PART A ----------------
    wire        a_valid, a_last;
    wire [11:0] a_idx;
    wire [7:0]  a_me, a_my, a_ms;

    bw_part_a #(.IMG_W(IMG_W), .IMG_H(IMG_H), .TILES_X(TILES_X), .TILES_Y(TILES_Y)) u_part_a (
        .clk(clk), .rst(rst), .frame_start(fs_a),
        .s_valid(px_valid), .s_ready(px_ready), .s_rgb(px_rgb),
        .t_valid(a_valid), .t_idx(a_idx), .t_last(a_last),
        .t_me(a_me), .t_my(a_my), .t_ms(a_ms),
        .frame_done(a_frame_done)
    );

    // ---------------- SIMULATED INPUT: tile vectors for Part B ----------------
    wire        v_valid, v_last;
    wire [11:0] v_idx;
    wire [7:0]  v_me, v_my, v_ms;

    bw_tile_vec_gen #(
        .TILES_X(TILES_X), .TILES_Y(TILES_Y),
        .PATCH_TX0(PATCH_TX0), .PATCH_TX1(PATCH_TX1),
        .PATCH_TY0(PATCH_TY0), .PATCH_TY1(PATCH_TY1)
    ) u_vec (
        .clk(clk), .rst(rst), .frame_start(fs_vec),
        .cfg_case(run_test[1:0]), .cfg_fidx(fidx),
        .t_valid(v_valid), .t_idx(v_idx), .t_last(v_last),
        .t_me(v_me), .t_my(v_my), .t_ms(v_ms)
    );

    // ---------------- tile source mux ----------------
    reg         m_valid, m_last;
    reg  [11:0] m_idx;
    reg  [7:0]  m_me, m_my, m_ms;

    always @(*) begin
        if (run_part == 2'd1) begin
            m_valid = v_valid;  m_idx = v_idx;  m_last = v_last;
            m_me    = v_me;     m_my  = v_my;   m_ms   = v_ms;
        end else begin
            m_valid = a_valid;  m_idx = a_idx;  m_last = a_last;
            m_me    = a_me;     m_my  = a_my;   m_ms   = a_ms;
        end
    end

    // ---------------- PART B ----------------
    wire        b_t_valid = m_valid && use_b;   // Part B only sees tiles in parts 1 and 2
    wire [11:0] rd_idx_safe;                    // read-back address (see below)
    wire [7:0]  rd_score_raw, rd_me_raw, rd_my_raw, rd_ms_raw;
    wire [15:0] rd_be_raw, rd_by_raw, rd_bs_raw;

    bw_part_b #(.TILES_X(TILES_X), .TILES_Y(TILES_Y)) u_part_b (
        .clk(clk), .rst(rst), .run_clear(run_clear),
        .frame_start(fs_b), .cfg_reset(rom_reset), .cfg_update(rom_update),
        .k_slow(k_slow), .k_fast(k_fast), .w_edge(w_edge), .w_grey(w_grey),
        .score_shift(score_shift), .t_flag(t_flag), .sat_max(sat_max),
        .sat_tol(sat_tol), .t_global(t_global), .gate_tiles(gate_tiles),
        .t_valid(b_t_valid), .t_idx(m_idx), .t_last(m_last),
        .t_me(m_me), .t_my(m_my), .t_ms(m_ms),
        .frame_done(b_frame_done), .gate(gate),
        .frame_count(frame_count), .changed(changed), .flagged(flagged),
        .score_sum(score_sum), .max_score(max_score), .max_idx(max_idx),
        .rd_idx(rd_idx_safe), .rd_score(rd_score_raw),
        .rd_be(rd_be_raw), .rd_by(rd_by_raw), .rd_bs(rd_bs_raw)
    );

    // which block ends a frame
    assign frame_done = (run_part == 2'd0) ? a_frame_done : b_frame_done;

    // ---------------- tile-feature monitor ----------------
    bw_feat_store u_feat (
        .clk(clk), .rst(rst), .run_clear(run_clear), .frame_start(frame_start),
        .t_valid(m_valid), .t_idx(m_idx), .t_me(m_me), .t_my(m_my), .t_ms(m_ms),
        .sum_e(sum_e), .sum_y(sum_y), .sum_s(sum_s),
        .rd_idx(rd_idx_safe), .rd_me(rd_me_raw), .rd_my(rd_my_raw), .rd_ms(rd_ms_raw)
    );

    // ---------------- read-back of tile tile_sel ----------------
    reg         rd_bad;               // tile_sel out of range (registered: RAM latency)

    assign rd_idx_safe = (tile_sel < N_TILES) ? tile_sel : 12'd0;

    always @(posedge clk) begin
        if (rst)
            rd_bad <= 1'b0;
        else
            rd_bad <= (tile_sel >= N_TILES);
    end

    assign rd_err   = rd_bad;
    assign rd_score = rd_bad ? 8'd0  : rd_score_raw;
    assign rd_me    = rd_bad ? 8'd0  : rd_me_raw;
    assign rd_my    = rd_bad ? 8'd0  : rd_my_raw;
    assign rd_ms    = rd_bad ? 8'd0  : rd_ms_raw;
    assign rd_be    = rd_bad ? 16'd0 : rd_be_raw;
    assign rd_by    = rd_bad ? 16'd0 : rd_by_raw;
    assign rd_bs    = rd_bad ? 16'd0 : rd_bs_raw;

endmodule
