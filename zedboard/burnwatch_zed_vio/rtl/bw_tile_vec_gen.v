// -----------------------------------------------------------------------------
// bw_tile_vec_gen.v   ***  SIMULATED INPUT  ***
// Tile-feature test vectors for testing Part B on its own.
//
// Streams one frame of 3,600 tile features (mE, mY, mS), one tile per clock,
// in the same format and order as Part A's output. Part B processes them
// with exactly the logic it uses in normal operation.
//
// Background tile: (mE, mY, mS) = (60, 70, 8). Patch = tiles with
// PATCH_TX0 <= tx < PATCH_TX1 and PATCH_TY0 <= ty < PATCH_TY1.
//   case 0  smoke patch : frame >= 1, patch tiles = (40, 95, 10)
//   case 1  saturation  : frame >= 1, patch tiles = (40, 95, S) with
//                         S = 60 / 14 / 12 for tx mod 3 = 0 / 1 / 2
//                         (above SAT_MAX / above bS+SAT_TOL / exactly at the limit)
//   case 2  lights      : frame >= 1, every tile = (60, 110, 8) (+40 luma)
//   case 3  random      : two xorshift32 generators per frame
//       a = xorshift(a) (seed 0x2545F491)      base features
//       p = xorshift(p) (seed 0x9E3779B9 ^ fidx) per-frame change
//       base = (a[7:0], a[15:8], a[21:16])
//       big change (p[31:30] = 0): XOR with (p[7:0], p[15:8], p[21:16])
//       small change            : XOR with (p[4:0], p[12:8], p[18:16])
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps
module bw_tile_vec_gen #(
    parameter TILES_X   = 80,
    parameter TILES_Y   = 45,
    parameter PATCH_TX0 = 30, parameter PATCH_TX1 = 50,
    parameter PATCH_TY0 = 15, parameter PATCH_TY1 = 30
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        frame_start,   // 1-cycle pulse: start a frame with this cfg
    input  wire [1:0]  cfg_case,      // test case 0..3
    input  wire [2:0]  cfg_fidx,      // frame number inside the test
    output reg         t_valid,
    output reg  [11:0] t_idx,
    output reg         t_last,
    output reg  [7:0]  t_me,
    output reg  [7:0]  t_my,
    output reg  [7:0]  t_ms
);

    localparam N_TILES = TILES_X * TILES_Y;
    localparam [31:0] SEED_A = 32'h2545F491;
    localparam [31:0] SEED_P = 32'h9E3779B9;

    // ---------------- registers ----------------
    reg         running;
    reg  [1:0]  case_r;
    reg  [2:0]  fidx_r;
    reg  [11:0] idx;                  // tile index
    reg  [6:0]  tx;                   // tile column
    reg  [5:0]  ty;                   // tile row
    reg  [1:0]  tx_mod3;              // tx mod 3
    reg  [31:0] lfsr_a, lfsr_p;

    // ---------------- wires ----------------
    reg  [31:0] a1, a2, a3, p1, p2, p3;   // xorshift steps
    reg         in_patch, later;
    reg  [7:0]  e0, y0, s0;               // random base features
    reg  [7:0]  fe, fy, fs;               // features of this tile

    // xorshift32 step of both generators
    always @(*) begin
        a1 = lfsr_a ^ (lfsr_a << 13);
        a2 = a1 ^ (a1 >> 17);
        a3 = a2 ^ (a2 << 5);
        p1 = lfsr_p ^ (lfsr_p << 13);
        p2 = p1 ^ (p1 >> 17);
        p3 = p2 ^ (p2 << 5);
    end

    // Features of the current tile
    always @(*) begin
        in_patch = (tx >= PATCH_TX0) && (tx < PATCH_TX1) && (ty >= PATCH_TY0) && (ty < PATCH_TY1);
        later    = (fidx_r != 3'd0);
        e0 = a3[7:0];
        y0 = a3[15:8];
        s0 = {2'b00, a3[21:16]};
        fe = 8'd60;  fy = 8'd70;  fs = 8'd8;                  // background
        case (case_r)
            2'd0: if (later && in_patch) begin
                      fe = 8'd40;  fy = 8'd95;  fs = 8'd10;
                  end
            2'd1: if (later && in_patch) begin
                      fe = 8'd40;  fy = 8'd95;
                      if (tx_mod3 == 2'd0)      fs = 8'd60;
                      else if (tx_mod3 == 2'd1) fs = 8'd14;
                      else                      fs = 8'd12;
                  end
            2'd2: if (later) begin
                      fe = 8'd60;  fy = 8'd110;  fs = 8'd8;
                  end
            default: begin
                      if (p3[31:30] == 2'b00) begin
                          fe = e0 ^ p3[7:0];
                          fy = y0 ^ p3[15:8];
                          fs = s0 ^ {2'b00, p3[21:16]};
                      end else begin
                          fe = e0 ^ {3'b000, p3[4:0]};
                          fy = y0 ^ {3'b000, p3[12:8]};
                          fs = s0 ^ {5'b00000, p3[18:16]};
                      end
                  end
        endcase
    end

    // Tile counters, generators and output register
    always @(posedge clk) begin
        if (rst) begin
            running <= 1'b0;
            t_valid <= 1'b0;
            case_r  <= 2'd0;
            fidx_r  <= 3'd0;
            idx     <= 12'd0;
            tx      <= 7'd0;
            ty      <= 6'd0;
            tx_mod3 <= 2'd0;
            lfsr_a  <= SEED_A;
            lfsr_p  <= SEED_P;
        end else if (frame_start) begin
            running <= 1'b1;
            t_valid <= 1'b0;
            case_r  <= cfg_case;
            fidx_r  <= cfg_fidx;
            idx     <= 12'd0;
            tx      <= 7'd0;
            ty      <= 6'd0;
            tx_mod3 <= 2'd0;
            lfsr_a  <= SEED_A;
            lfsr_p  <= SEED_P ^ {29'd0, cfg_fidx};
        end else begin
            t_valid <= running;
            if (running) begin
                t_idx   <= idx;
                t_last  <= (idx == N_TILES - 1);
                t_me    <= fe;
                t_my    <= fy;
                t_ms    <= fs;
                lfsr_a  <= a3;
                lfsr_p  <= p3;
                idx     <= idx + 12'd1;
                if (idx == N_TILES - 1)
                    running <= 1'b0;
                if (tx == TILES_X - 1) begin
                    tx      <= 7'd0;
                    tx_mod3 <= 2'd0;
                    ty      <= ty + 6'd1;
                end else begin
                    tx      <= tx + 7'd1;
                    tx_mod3 <= (tx_mod3 == 2'd2) ? 2'd0 : tx_mod3 + 2'd1;
                end
            end
        end
    end

endmodule
