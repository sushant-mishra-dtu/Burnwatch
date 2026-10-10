// -----------------------------------------------------------------------------
// bw_ctrl.v   Test controller (FSM)
// Runs one test: start-edge detect, check the selection, then send each frame
// of the test (frame_start pulse), wait for the frame to finish, record its
// gate, and stop with done = 1. Results and status stay latched until the
// next accepted start or a reset.
//
// Start rule: a test starts only on a 0 -> 1 edge of `start` while the
// controller is idle or done. Holding start high does not start again, and
// edges while busy are ignored. After a reset the edge detector reads as if
// start were already 1, so a start held high through a reset does not launch.
//
//   IDLE --start edge--> LOAD --bad part/test--> DONE (error)
//                         |
//                         v
//                      FSTART --> FWAIT --frame done, more frames--> FSTART
//                                   |  \--frame done, last frame--> DONE
//                                   \----timeout------------------> DONE (error)
//   DONE --start edge--> LOAD
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps
module bw_ctrl #(
    parameter [31:0] FRAME_TIMEOUT = 32'd2000000   // clocks allowed per frame
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        start,         // from VIO (level)
    input  wire [1:0]  part_sel,      // from VIO, sampled at the start edge
    input  wire [2:0]  test_sel,
    // test table (bw_test_rom, addressed by run_part, run_test, fidx)
    input  wire        rom_test_ok,
    input  wire [3:0]  rom_n_frames,
    // datapath
    input  wire        frame_done,    // the current frame is finished
    input  wire        frame_gate,    // its gate (valid with frame_done)
    // control outputs
    output reg  [1:0]  run_part,      // latched selection
    output reg  [2:0]  run_test,
    output reg  [2:0]  fidx,          // frame number inside the test
    output wire        run_clear,     // 1-cycle: clear old results (in LOAD)
    output wire        frame_start,   // 1-cycle: start frame fidx (in FSTART)
    // status
    output wire        busy,
    output wire        done,
    output reg         error,
    output reg  [3:0]  err_code,      // 0 ok, 1 bad part_sel, 2 bad test_sel, 3 timeout
    output reg  [7:0]  run_id,        // +1 on every accepted start
    output reg  [3:0]  frames_run,    // frames finished in this test
    output reg  [7:0]  gate_hist,     // bit i = gate of frame i
    output reg  [31:0] cycles         // clocks from start to done
);

    localparam [2:0] S_IDLE   = 3'd0,
                     S_LOAD   = 3'd1,
                     S_FSTART = 3'd2,
                     S_FWAIT  = 3'd3,
                     S_DONE   = 3'd4;

    // ---------------- start edge detector ----------------
    reg  start_q1, start_q2;
    wire start_edge = start_q1 && !start_q2;

    always @(posedge clk) begin
        if (rst) begin
            start_q1 <= 1'b1;          // "already high": no edge right after reset
            start_q2 <= 1'b1;
        end else begin
            start_q1 <= start;
            start_q2 <= start_q1;
        end
    end

    // ---------------- FSM registers ----------------
    reg  [2:0]  state;
    reg  [31:0] tcount;               // clocks spent on the current frame

    reg  [2:0]  state_next;
    reg  [1:0]  run_part_next;
    reg  [2:0]  run_test_next;
    reg  [2:0]  fidx_next;
    reg         error_next;
    reg  [3:0]  err_code_next;
    reg  [7:0]  run_id_next;
    reg  [3:0]  frames_run_next;
    reg  [7:0]  gate_hist_next;
    reg  [31:0] cycles_next;
    reg  [31:0] tcount_next;

    assign busy        = (state == S_LOAD) || (state == S_FSTART) || (state == S_FWAIT);
    assign done        = (state == S_DONE);
    assign run_clear   = (state == S_LOAD);
    assign frame_start = (state == S_FSTART);

    // Next state and next outputs
    always @(*) begin
        state_next      = state;
        run_part_next   = run_part;
        run_test_next   = run_test;
        fidx_next       = fidx;
        error_next      = error;
        err_code_next   = err_code;
        run_id_next     = run_id;
        frames_run_next = frames_run;
        gate_hist_next  = gate_hist;
        cycles_next     = busy ? cycles + 32'd1 : cycles;
        tcount_next     = tcount;
        case (state)
            S_IDLE, S_DONE: begin
                if (start_edge) begin
                    state_next      = S_LOAD;
                    run_part_next   = part_sel;
                    run_test_next   = test_sel;
                    fidx_next       = 3'd0;
                    error_next      = 1'b0;
                    err_code_next   = 4'd0;
                    run_id_next     = run_id + 8'd1;
                    frames_run_next = 4'd0;
                    gate_hist_next  = 8'd0;
                    cycles_next     = 32'd0;
                end
            end
            S_LOAD: begin
                if (run_part == 2'd3) begin
                    state_next    = S_DONE;
                    error_next    = 1'b1;
                    err_code_next = 4'd1;
                end else if (!rom_test_ok) begin
                    state_next    = S_DONE;
                    error_next    = 1'b1;
                    err_code_next = 4'd2;
                end else begin
                    state_next = S_FSTART;
                end
            end
            S_FSTART: begin
                tcount_next = 32'd0;
                state_next  = S_FWAIT;
            end
            S_FWAIT: begin
                tcount_next = tcount + 32'd1;
                if (frame_done) begin
                    frames_run_next      = frames_run + 4'd1;
                    gate_hist_next[fidx] = frame_gate;
                    if ({1'b0, fidx} == rom_n_frames - 4'd1) begin
                        state_next = S_DONE;
                    end else begin
                        fidx_next  = fidx + 3'd1;
                        state_next = S_FSTART;
                    end
                end else if (tcount >= FRAME_TIMEOUT) begin
                    state_next    = S_DONE;
                    error_next    = 1'b1;
                    err_code_next = 4'd3;
                end
            end
            default: state_next = S_IDLE;
        endcase
    end

    // State registers
    always @(posedge clk) begin
        if (rst) begin
            state      <= S_IDLE;
            run_part   <= 2'd0;
            run_test   <= 3'd0;
            fidx       <= 3'd0;
            error      <= 1'b0;
            err_code   <= 4'd0;
            run_id     <= 8'd0;
            frames_run <= 4'd0;
            gate_hist  <= 8'd0;
            cycles     <= 32'd0;
            tcount     <= 32'd0;
        end else begin
            state      <= state_next;
            run_part   <= run_part_next;
            run_test   <= run_test_next;
            fidx       <= fidx_next;
            error      <= error_next;
            err_code   <= err_code_next;
            run_id     <= run_id_next;
            frames_run <= frames_run_next;
            gate_hist  <= gate_hist_next;
            cycles     <= cycles_next;
            tcount     <= tcount_next;
        end
    end

endmodule
