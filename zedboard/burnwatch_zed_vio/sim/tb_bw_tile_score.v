// -----------------------------------------------------------------------------
// tb_bw_tile_score.v   Unit test of the Part B datapath (bw_tile_score)
// 4,000 random single-tile vectors from model/bw_model.py, each with its own
// random register values (all ten registers over their full ranges, plus
// corner baselines 0 / 255 / 32767 / 32768 / 65280), reset / update /
// prev_gate flags. Expected values come from golden.score_tiles() and
// golden.update_baseline(). Prints PASS or FAIL and the first mismatches.
// The register inputs are frame constants in the real design, so every
// vector is held for the whole pipeline (5 clocks) before it is checked.
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps

module tb_bw_tile_score;

    localparam NVEC = 4000;

    reg          clk = 1'b0;
    reg          rst = 1'b1;
    reg  [227:0] vec [0:NVEC-1];
    reg  [227:0] v;

    // inputs
    reg          reset_frame, update_frame, prev_gate, in_valid;
    reg  [3:0]   k_slow, k_fast;
    reg  [7:0]   w_edge, w_grey, t_flag, sat_max, in_me, in_my, in_ms;
    reg  [4:0]   score_shift;
    reg  [15:0]  sat_tol, t_global, in_be, in_by, in_bs;
    // outputs
    wire         out_valid, out_last, out_flag, out_chg;
    wire [11:0]  out_idx;
    wire [7:0]   out_score;
    wire [15:0]  out_be, out_by, out_bs;

    integer i, errors;

    always #5 clk = ~clk;

    bw_tile_score dut (
        .clk(clk), .rst(rst),
        .reset_frame(reset_frame), .update_frame(update_frame), .prev_gate(prev_gate),
        .k_slow(k_slow), .k_fast(k_fast), .w_edge(w_edge), .w_grey(w_grey),
        .score_shift(score_shift), .t_flag(t_flag), .sat_max(sat_max),
        .sat_tol(sat_tol), .t_global(t_global),
        .in_valid(in_valid), .in_idx(12'd0), .in_last(1'b0),
        .in_me(in_me), .in_my(in_my), .in_ms(in_ms),
        .in_be(in_be), .in_by(in_by), .in_bs(in_bs),
        .out_valid(out_valid), .out_idx(out_idx), .out_last(out_last),
        .out_score(out_score), .out_flag(out_flag), .out_chg(out_chg),
        .out_be(out_be), .out_by(out_by), .out_bs(out_bs)
    );

    initial begin
        $readmemh("score_unit.mem", vec);
        errors   = 0;
        in_valid = 1'b0;
        repeat (3) @(posedge clk);
        rst = 1'b0;
        for (i = 0; i < NVEC; i = i + 1) begin
            v = vec[i];
            @(negedge clk);
            k_slow       = v[227:224];
            k_fast       = v[223:220];
            w_edge       = v[219:212];
            w_grey       = v[211:204];
            score_shift  = v[200:196];
            t_flag       = v[195:188];
            sat_max      = v[187:180];
            sat_tol      = v[179:164];
            t_global     = v[163:148];
            reset_frame  = v[144];
            update_frame = v[140];
            prev_gate    = v[136];
            in_me        = v[135:128];
            in_my        = v[127:120];
            in_ms        = v[119:112];
            in_be        = v[111:96];
            in_by        = v[95:80];
            in_bs        = v[79:64];
            in_valid     = 1'b1;
            @(negedge clk);
            in_valid     = 1'b0;
            repeat (2) @(negedge clk);          // Q1 -> Q2 -> Q3
            if (!out_valid || out_score !== v[63:56] || out_flag !== v[52] || out_chg !== v[48] ||
                out_be !== v[47:32] || out_by !== v[31:16] || out_bs !== v[15:0]) begin
                errors = errors + 1;
                if (errors <= 10)
                    $display("MISMATCH vec %0d: got score=%0d flag=%0d chg=%0d b=%0d,%0d,%0d  exp score=%0d flag=%0d chg=%0d b=%0d,%0d,%0d",
                             i, out_score, out_flag, out_chg, out_be, out_by, out_bs,
                             v[63:56], v[52], v[48], v[47:32], v[31:16], v[15:0]);
            end
        end
        if (errors == 0)
            $display("TB_TILE_SCORE PASS: %0d vectors bit-exact", NVEC);
        else
            $display("TB_TILE_SCORE FAIL: %0d of %0d vectors wrong", errors, NVEC);
        $finish;
    end

endmodule
