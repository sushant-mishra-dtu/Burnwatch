// -----------------------------------------------------------------------------
// bw_test_rom.v   (combinational table)
// The demo tests: for (part, test, frame number) it gives the number of
// frames in the test and the settings of that frame.
//
// part 0 = Part A only     (1 frame from the stimulus generator, features only)
//   A0 background   A1 smoke a=2   A2 lights +40   A3 red cloth
// part 1 = Part B only     (tile vectors from bw_tile_vec_gen)
//   B0 smoke patch (3 frames)        B1 saturation reject (2 frames)
//   B2 lights -> gate -> snap (4)    B3 random stress, update/reset mix (6)
// part 2 = Integrated A->B (frames from the stimulus generator)
//   I0 smoke grows a=0,1,2,3 (4)     I1 lights on at frame 1 (4)
//   I2 red cloth at frame 1 (3)      I3 static scene (3)
//   I4 smoke with update_this_frame = 0 frames and a second reset frame (5)
// Every Part B / integrated test starts with a reset frame, so a test gives
// the same result whatever ran before it.
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps
module bw_test_rom (
    input  wire [1:0] part,
    input  wire [2:0] test,
    input  wire [2:0] fidx,
    output reg        test_ok,        // (part, test) exists
    output reg  [3:0] n_frames,       // frames in this test
    output reg        f_reset,        // reset frame
    output reg        f_update,       // update_this_frame
    output reg  [2:0] f_smoke,        // stimulus: smoke strength
    output reg        f_lights,       // stimulus: +40 lighting
    output reg        f_cloth         // stimulus: red cloth
);

    always @(*) begin
        // defaults: invalid test, frame 0 is a reset frame, update on
        test_ok  = 1'b0;
        n_frames = 4'd0;
        f_reset  = (fidx == 3'd0);
        f_update = 1'b1;
        f_smoke  = 3'd0;
        f_lights = 1'b0;
        f_cloth  = 1'b0;
        case (part)
            // ---------------- Part A only ----------------
            2'd0: begin
                n_frames = 4'd1;
                case (test)
                    3'd0: test_ok = 1'b1;
                    3'd1: begin test_ok = 1'b1; f_smoke  = 3'd2; end
                    3'd2: begin test_ok = 1'b1; f_lights = 1'b1; end
                    3'd3: begin test_ok = 1'b1; f_cloth  = 1'b1; end
                    default: n_frames = 4'd0;
                endcase
            end
            // ---------------- Part B only ----------------
            2'd1: begin
                case (test)
                    3'd0: begin test_ok = 1'b1; n_frames = 4'd3; end
                    3'd1: begin test_ok = 1'b1; n_frames = 4'd2; end
                    3'd2: begin test_ok = 1'b1; n_frames = 4'd4; end
                    3'd3: begin
                        test_ok  = 1'b1;
                        n_frames = 4'd6;
                        // (reset, update) per frame: 11 01 00 01 11 01
                        f_reset  = (fidx == 3'd0) || (fidx == 3'd4);
                        f_update = (fidx != 3'd2);
                    end
                    default: n_frames = 4'd0;
                endcase
            end
            // ---------------- Integrated A -> B ----------------
            2'd2: begin
                case (test)
                    3'd0: begin test_ok = 1'b1; n_frames = 4'd4; f_smoke = fidx; end
                    3'd1: begin test_ok = 1'b1; n_frames = 4'd4; f_lights = (fidx != 3'd0); end
                    3'd2: begin test_ok = 1'b1; n_frames = 4'd3; f_cloth  = (fidx != 3'd0); end
                    3'd3: begin test_ok = 1'b1; n_frames = 4'd3; end
                    3'd4: begin
                        test_ok  = 1'b1;
                        n_frames = 4'd5;
                        // frame:  0     1     2     3     4
                        // smoke:  0     1     2     2     3
                        // reset:  1     0     0     1     0
                        // update: 1     0     1     1     1
                        f_reset  = (fidx == 3'd0) || (fidx == 3'd3);
                        f_update = (fidx != 3'd1);
                        if (fidx == 3'd0)      f_smoke = 3'd0;
                        else if (fidx == 3'd1) f_smoke = 3'd1;
                        else if (fidx == 3'd4) f_smoke = 3'd3;
                        else                   f_smoke = 3'd2;
                    end
                    default: n_frames = 4'd0;
                endcase
            end
            // ---------------- part 3: not used ----------------
            default: begin
                test_ok  = 1'b0;
                n_frames = 4'd0;
            end
        endcase
    end

endmodule
