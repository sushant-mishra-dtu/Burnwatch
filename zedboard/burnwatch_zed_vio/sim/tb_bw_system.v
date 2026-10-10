// -----------------------------------------------------------------------------
// tb_bw_system.v   Self-checking system testbench for bw_system
// (everything on the FPGA except the clock pin, power-on reset and the VIO).
//
// Default: the real 1280x720 geometry (~32 M clocks, the same tests the
// board runs). Define QUICK for a 320x192 geometry with the same tests
// (seconds instead of minutes); it has its own expected files.
//
// Checks
//   T0  reset state; Start held high through reset does not launch
//   T1  all 14 demo tests: every status/result probe, then every tile's
//       features, score and baselines through the VIO read-back port, against
//       golden.py (sim/expected/*.mem from model/bw_model.py)
//   T2  repeat a test: identical results, run_id + 1
//   T3  Start held high: exactly one run; a new 0->1 edge runs again
//   T4  Start edges while busy are ignored
//   T5  part_sel = 3 -> error, err_code 1
//   T6  unknown test_sel -> error, err_code 2
//   T7  tile_sel out of range -> rd_err, read-back forced to 0
//   T8  reset in the middle of a run, then a correct run
//   T9  input stream stalls -> frame timeout, err_code 3, then recovery
// Expected-data files are read from the simulation directory (Vivado copies
// the .mem files of the sim fileset there).
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps

module tb_bw_system;

`ifdef QUICK
    localparam IMG_W = 320, IMG_H = 192, TX = 20, TY = 12;
    localparam SX0 = 96,  SX1 = 224, SY0 = 48, SY1 = 144;
    localparam CX0 = 16,  CX1 = 80,  CY0 = 16, CY1 = 48;
    localparam PX0 = 6,   PX1 = 14,  PY0 = 3,  PY1 = 9;
    localparam [11:0] GATE_TILES = 12'd96;
    localparam [31:0] TIMEOUT    = 32'd200000;
    `define BW_SUMMARY "quick_summary.mem"
    `define BW_TILES   "quick_tiles.mem"
`else
    localparam IMG_W = 1280, IMG_H = 720, TX = 80, TY = 45;
    localparam SX0 = 480, SX1 = 800, SY0 = 240, SY1 = 480;
    localparam CX0 = 160, CX1 = 320, CY0 = 96,  CY1 = 224;
    localparam PX0 = 30,  PX1 = 50,  PY0 = 15,  PY1 = 30;
    localparam [11:0] GATE_TILES = 12'd1440;
    localparam [31:0] TIMEOUT    = 32'd2000000;
    `define BW_SUMMARY "full_summary.mem"
    `define BW_TILES   "full_tiles.mem"
`endif

    localparam N      = TX * TY;                     // tiles per frame
    localparam NTEST  = 14;                          // lines in the summary file
    localparam SLOTS  = (IMG_H + 1) * (IMG_W + 1);   // clocks per Part A frame
    localparam [31:0] WAIT_LIMIT = 8 * SLOTS + 2 * TIMEOUT;

    // ---------------- DUT signals ----------------
    reg         clk = 1'b0;
    reg         rst;
    reg         start;
    reg  [1:0]  part_sel;
    reg  [2:0]  test_sel;
    reg  [11:0] tile_sel;
    reg         stim_pause;
    reg  [7:0]  t_flag;

    wire        busy, done, result_valid, error, gate, rd_err;
    wire [3:0]  err_code, frames_run;
    wire [7:0]  run_id, gate_hist, max_score, rd_me, rd_my, rd_ms, rd_score;
    wire [11:0] changed, flagged, max_idx;
    wire [15:0] frame_count, rd_be, rd_by, rd_bs;
    wire [19:0] score_sum, sum_e, sum_y, sum_s;
    wire [31:0] cycles;

    // ---------------- expected data ----------------
    reg  [511:0] summ  [0:NTEST-1];                  // 16 x 32-bit fields per test
    reg  [79:0]  tiles [0:NTEST*N-1];                // {score, mE, mY, mS, bE, bY, bS}

    integer errors;                                  // total mismatches
    integer test_errors;                             // mismatches in the current check
    integer exp_run_id;
    integer k, t, n, ok;
    reg  [7:0]   rid_before;                         // run_id before the last Start
    reg  [511:0] line;
    reg  [79:0]  tl;

    always #5 clk = ~clk;                            // 100 MHz

    bw_system #(
        .IMG_W(IMG_W), .IMG_H(IMG_H), .TILES_X(TX), .TILES_Y(TY),
        .SMOKE_X0(SX0), .SMOKE_X1(SX1), .SMOKE_Y0(SY0), .SMOKE_Y1(SY1),
        .CLOTH_X0(CX0), .CLOTH_X1(CX1), .CLOTH_Y0(CY0), .CLOTH_Y1(CY1),
        .PATCH_TX0(PX0), .PATCH_TX1(PX1), .PATCH_TY0(PY0), .PATCH_TY1(PY1),
        .FRAME_TIMEOUT(TIMEOUT)
    ) dut (
        .clk(clk), .rst(rst),
        .start(start), .part_sel(part_sel), .test_sel(test_sel),
        .tile_sel(tile_sel), .stim_pause(stim_pause),
        .k_slow(4'd6), .k_fast(4'd0), .w_edge(8'd4), .w_grey(8'd4),
        .score_shift(5'd8), .t_flag(t_flag), .sat_max(8'd40),
        .sat_tol(16'd1024), .t_global(16'd6144), .gate_tiles(GATE_TILES),
        .busy(busy), .done(done), .result_valid(result_valid),
        .error(error), .err_code(err_code), .run_id(run_id),
        .frames_run(frames_run), .gate_hist(gate_hist), .cycles(cycles),
        .gate(gate), .changed(changed), .flagged(flagged), .score_sum(score_sum),
        .max_score(max_score), .max_idx(max_idx), .frame_count(frame_count),
        .sum_e(sum_e), .sum_y(sum_y), .sum_s(sum_s),
        .rd_err(rd_err), .rd_me(rd_me), .rd_my(rd_my), .rd_ms(rd_ms),
        .rd_score(rd_score), .rd_be(rd_be), .rd_by(rd_by), .rd_bs(rd_bs)
    );

    // ---------------- helpers ----------------
    function [31:0] fld;                             // field i of a summary line
        input [511:0] l;
        input integer i;
        begin
            fld = l[i*32 +: 32];
        end
    endfunction

    task expect_eq;
        input [8*16-1:0] what;
        input [31:0]     got;
        input [31:0]     exp;
        begin
            if (got !== exp) begin
                errors      = errors + 1;
                test_errors = test_errors + 1;
                $display("    MISMATCH %0s: got %0d, expected %0d", what, got, exp);
            end
        end
    endtask

    // Pulse Start 0 -> 1 -> 0 (as from the VIO GUI)
    task pulse_start;
        input [1:0] p;
        input [2:0] tt;
        input [7:0] tf;
        begin
            @(negedge clk);
            rid_before = run_id;
            part_sel = p;
            test_sel = tt;
            t_flag   = tf;
            start    = 1'b1;
            repeat (3) @(negedge clk);
            start    = 1'b0;
        end
    endtask

    // Wait until the Start was accepted (run_id changed; at most 50 clocks),
    // then for done (ok = 0 on time-out of the testbench itself)
    task wait_done;
        output integer okk;
        integer c;
        begin
            c = 0;
            while (run_id == rid_before && c < 50) begin
                @(negedge clk);
                c = c + 1;
            end
            c = 0;
            while (!done && c < WAIT_LIMIT) begin
                @(negedge clk);
                c = c + 1;
            end
            okk = done;
            if (!done) begin
                errors = errors + 1;
                $display("    TB TIMEOUT waiting for done");
            end
            @(negedge clk);
        end
    endtask

    // Compare every status / result probe with summary line kk
    task check_summary;
        input integer kk;
        begin
            line = summ[kk];
            expect_eq("busy",         busy,         0);
            expect_eq("done",         done,         1);
            expect_eq("result_valid", result_valid, 1);
            expect_eq("error",        error,        0);
            expect_eq("err_code",     err_code,     0);
            expect_eq("frames_run",   frames_run,   fld(line, 2));
            expect_eq("gate_hist",    gate_hist,    fld(line, 3));
            expect_eq("sum_e",        sum_e,        fld(line, 11));
            expect_eq("sum_y",        sum_y,        fld(line, 12));
            expect_eq("sum_s",        sum_s,        fld(line, 13));
            if (fld(line, 15) != 0) begin            // Part B ran
                expect_eq("gate",        gate,        fld(line, 4));
                expect_eq("changed",     changed,     fld(line, 5));
                expect_eq("flagged",     flagged,     fld(line, 6));
                expect_eq("score_sum",   score_sum,   fld(line, 7));
                expect_eq("max_score",   max_score,   fld(line, 8));
                expect_eq("max_idx",     max_idx,     fld(line, 9));
                expect_eq("frame_count", frame_count, fld(line, 10));
            end else begin                           // Part A only: B results cleared
                expect_eq("gate",        gate,        0);
                expect_eq("changed",     changed,     0);
                expect_eq("flagged",     flagged,     0);
                expect_eq("score_sum",   score_sum,   0);
                expect_eq("max_score",   max_score,   0);
                expect_eq("max_idx",     max_idx,     0);
            end
        end
    endtask

    // Read every tile back through tile_sel and compare with the golden tiles
    task check_tiles;
        input integer kk;
        input         part_b;
        integer tt, bad;
        begin
            bad = 0;
            for (tt = 0; tt < N; tt = tt + 1) begin
                tile_sel = tt;
                repeat (3) @(negedge clk);
                tl = tiles[kk*N + tt];
                if (rd_err !== 1'b0 || rd_me !== tl[71:64] || rd_my !== tl[63:56] || rd_ms !== tl[55:48] ||
                    (part_b && (rd_score !== tl[79:72] || rd_be !== tl[47:32] ||
                                rd_by !== tl[31:16] || rd_bs !== tl[15:0]))) begin
                    bad = bad + 1;
                    if (bad <= 10)
                        $display("    TILE MISMATCH %0d (row %0d col %0d): got f=%0d,%0d,%0d s=%0d b=%0d,%0d,%0d  exp f=%0d,%0d,%0d s=%0d b=%0d,%0d,%0d",
                                 tt, tt / TX, tt % TX, rd_me, rd_my, rd_ms, rd_score, rd_be, rd_by, rd_bs,
                                 tl[71:64], tl[63:56], tl[55:48], tl[79:72], tl[47:32], tl[31:16], tl[15:0]);
                end
            end
            errors      = errors + bad;
            test_errors = test_errors + bad;
        end
    endtask

    // Run demo test kk from the summary file and check everything
    task run_and_check;
        input integer kk;
        begin
            line = summ[kk];
            test_errors = 0;
            pulse_start(fld(line, 0), fld(line, 1), fld(line, 14));
            wait_done(ok);
            exp_run_id = (exp_run_id + 1) % 256;
            expect_eq("run_id", run_id, exp_run_id);
            check_summary(kk);
            check_tiles(kk, fld(line, 15) != 0);
            $display("  test %2d part=%0d test=%0d T_FLAG=%0d: %0s  cycles=%0d  gate_hist=%b changed=%0d flagged=%0d score_sum=%0d max=%0d@%0d sums=%0d,%0d,%0d",
                     kk, fld(line, 0), fld(line, 1), fld(line, 14), (test_errors == 0) ? "PASS" : "FAIL",
                     cycles, gate_hist, changed, flagged, score_sum, max_score, max_idx, sum_e, sum_y, sum_s);
        end
    endtask

    // Expect an error result
    task check_error;
        input [3:0] code;
        begin
            expect_eq("done",         done,         1);
            expect_eq("busy",         busy,         0);
            expect_eq("error",        error,        1);
            expect_eq("err_code",     err_code,     code);
            expect_eq("result_valid", result_valid, 0);
        end
    endtask

    // ---------------- test sequence ----------------
    initial begin
        $readmemh(`BW_SUMMARY, summ);
        $readmemh(`BW_TILES, tiles);
        errors     = 0;
        exp_run_id = 0;
        rst        = 1'b1;
        start      = 1'b1;                           // held high through reset (T0)
        part_sel   = 2'd0;
        test_sel   = 3'd0;
        tile_sel   = 12'd0;
        stim_pause = 1'b0;
        t_flag     = 8'd40;
        if (summ[0] === {512{1'bx}}) begin
            $display("ERROR: cannot read %0s (run from the folder with the .mem files)", `BW_SUMMARY);
            $finish;
        end
        $display("BurnWatch tb_bw_system: %0dx%0d, %0d tiles", IMG_W, IMG_H, N);

        // ---- T0: reset ----
        repeat (10) @(negedge clk);
        rst = 1'b0;
        repeat (50) @(negedge clk);
        test_errors = 0;
        expect_eq("busy",   busy,   0);
        expect_eq("done",   done,   0);
        expect_eq("error",  error,  0);
        expect_eq("run_id", run_id, 0);
        expect_eq("cycles", cycles, 0);
        start = 1'b0;
        repeat (10) @(negedge clk);
        expect_eq("busy",   busy,   0);
        $display("T0 reset state, Start held through reset: %0s", (test_errors == 0) ? "PASS" : "FAIL");

        // ---- T1: the demo tests ----
        $display("T1 demo tests (all probes + every tile read back):");
        for (k = 0; k < NTEST; k = k + 1)
            run_and_check(k);

        // ---- T2: repeat a test ----
        $display("T2 repeat B0:");
        run_and_check(4);

        // ---- T3: Start held high ----
        test_errors = 0;
        @(negedge clk);
        rid_before = run_id;
        part_sel = 2'd1;  test_sel = 3'd1;  t_flag = 8'd40;
        start    = 1'b1;                             // and keep it high
        wait_done(ok);
        exp_run_id = (exp_run_id + 1) % 256;
        repeat (3000) @(negedge clk);
        expect_eq("run_id", run_id, exp_run_id);     // exactly one run
        check_summary(5);
        start = 1'b0;
        repeat (5) @(negedge clk);
        expect_eq("run_id", run_id, exp_run_id);
        $display("T3 Start held high -> one run only: %0s", (test_errors == 0) ? "PASS" : "FAIL");
        run_and_check(5);                            // a new 0->1 edge runs again

        // ---- T4: Start edges while busy ----
        test_errors = 0;
        line = summ[7];
        pulse_start(fld(line, 0), fld(line, 1), fld(line, 14));
        repeat (200) @(negedge clk);
        expect_eq("busy", busy, 1);
        pulse_start(2'd2, 3'd3, 8'd40);              // ignored: busy
        repeat (100) @(negedge clk);
        pulse_start(2'd0, 3'd0, 8'd40);              // ignored: busy
        part_sel = 2'd1;  test_sel = 3'd3;
        wait_done(ok);
        exp_run_id = (exp_run_id + 1) % 256;
        expect_eq("run_id", run_id, exp_run_id);
        check_summary(7);
        check_tiles(7, 1'b1);
        $display("T4 Start while busy ignored: %0s", (test_errors == 0) ? "PASS" : "FAIL");

        // ---- T5: invalid part_sel ----
        test_errors = 0;
        pulse_start(2'd3, 3'd0, 8'd40);
        wait_done(ok);
        exp_run_id = (exp_run_id + 1) % 256;
        check_error(4'd1);
        expect_eq("frames_run", frames_run, 0);
        $display("T5 part_sel=3 -> err_code 1: %0s", (test_errors == 0) ? "PASS" : "FAIL");

        // ---- T6: invalid test_sel ----
        test_errors = 0;
        pulse_start(2'd0, 3'd4, 8'd40);  wait_done(ok);  check_error(4'd2);
        pulse_start(2'd1, 3'd7, 8'd40);  wait_done(ok);  check_error(4'd2);
        pulse_start(2'd2, 3'd5, 8'd40);  wait_done(ok);  check_error(4'd2);
        exp_run_id = (exp_run_id + 3) % 256;
        expect_eq("run_id", run_id, exp_run_id);
        $display("T6 bad test_sel -> err_code 2: %0s", (test_errors == 0) ? "PASS" : "FAIL");

        // ---- T7: tile_sel out of range ----
        test_errors = 0;
        tile_sel = N;
        repeat (3) @(negedge clk);
        expect_eq("rd_err",   rd_err,   1);
        expect_eq("rd_me",    rd_me,    0);
        expect_eq("rd_score", rd_score, 0);
        expect_eq("rd_be",    rd_be,    0);
        tile_sel = 12'd4095;
        repeat (3) @(negedge clk);
        expect_eq("rd_err",   rd_err,   1);
        tile_sel = N - 1;
        repeat (3) @(negedge clk);
        expect_eq("rd_err",   rd_err,   0);
        $display("T7 tile_sel out of range -> rd_err: %0s", (test_errors == 0) ? "PASS" : "FAIL");

        // ---- T8: reset during a run ----
        test_errors = 0;
        pulse_start(2'd2, 3'd0, 8'd40);
        repeat (5000) @(negedge clk);
        expect_eq("busy", busy, 1);
        rst = 1'b1;
        repeat (4) @(negedge clk);
        rst = 1'b0;
        repeat (5) @(negedge clk);
        expect_eq("busy",       busy,       0);
        expect_eq("done",       done,       0);
        expect_eq("error",      error,      0);
        expect_eq("run_id",     run_id,     0);
        expect_eq("cycles",     cycles,     0);
        expect_eq("frames_run", frames_run, 0);
        exp_run_id = 0;
        $display("T8 reset during a run -> idle: %0s", (test_errors == 0) ? "PASS" : "FAIL");
        run_and_check(11);                           // engine works again after the reset

        // ---- T9: stalled input -> timeout, then recovery ----
        test_errors = 0;
        stim_pause = 1'b1;
        pulse_start(2'd0, 3'd0, 8'd40);
        wait_done(ok);
        exp_run_id = (exp_run_id + 1) % 256;
        check_error(4'd3);
        expect_eq("frames_run", frames_run, 0);
        stim_pause = 1'b0;
        $display("T9 stalled input -> err_code 3: %0s  (cycles=%0d)", (test_errors == 0) ? "PASS" : "FAIL", cycles);
        run_and_check(0);                            // next run is correct without a reset

        // ---- summary ----
        if (errors == 0)
            $display("TB_BW_SYSTEM PASS: all checks passed");
        else
            $display("TB_BW_SYSTEM FAIL: %0d mismatches", errors);
        $finish;
    end

endmodule
