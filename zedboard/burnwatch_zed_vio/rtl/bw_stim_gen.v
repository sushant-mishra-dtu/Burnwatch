// -----------------------------------------------------------------------------
// bw_stim_gen.v   ***  SIMULATED INPUT  ***
// Synthetic camera-frame generator for the ZedBoard demo.
//
// In the real BurnWatch system the frames come from a camera through HDMI.
// The ZedBoard in Cloud Labs has no video input, so this block makes a
// 1280x720 RGB frame inside the FPGA and streams it, one pixel per clock in
// raster order, into Part A over a valid/ready handshake. Part A cannot tell
// it apart from a real feed.
//
// Every pixel is a pure integer function of (x, y, scene settings), so
// model/bw_model.py builds exactly the same frame and runs the reference
// detector/golden.py on it to get the expected results.
//
// Scene (applied in this order):
//   background : 8x8 grey checkerboard texture, v = 140+(x>>3 & 15) on light
//                cells, 40+(y>>3 & 15) on dark cells; R = v+4, G = v, B = v-4
//   smoke a    : inside the smoke box, every channel c = ((4-a)*c + a*128) >> 2
//                (blend towards grey 128: fades the texture, moves towards
//                mid-grey; a = 0 none ... 4 flat grey)
//   cloth      : inside the cloth box, RGB = (200, 30, 30) (saturated red)
//   lights     : every channel c = min(c + 40, 255) (global lighting change)
// Pixel word: rgb[7:0] = R, rgb[15:8] = G, rgb[23:16] = B
// (docs/contracts.md section 7: R | G<<8 | B<<16).
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps
module bw_stim_gen #(
    parameter IMG_W    = 1280,
    parameter IMG_H    = 720,
    parameter SMOKE_X0 = 480,  parameter SMOKE_X1 = 800,   // smoke box, x0 <= x < x1
    parameter SMOKE_Y0 = 240,  parameter SMOKE_Y1 = 480,
    parameter CLOTH_X0 = 160,  parameter CLOTH_X1 = 320,   // cloth box
    parameter CLOTH_Y0 = 96,   parameter CLOTH_Y1 = 224
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        frame_start,   // 1-cycle pulse: restart at (0,0) with this scene
    input  wire [2:0]  scene_smoke,   // smoke strength 0..4 (values above 4 act as 4)
    input  wire        scene_lights,  // add the +40 lighting change
    input  wire        scene_cloth,   // add the red cloth
    input  wire        pause,         // test hook: stop producing pixels (0 on the board)
    output wire        m_valid,       // stream out
    input  wire        m_ready,
    output wire [23:0] m_rgb
);

    // ---------------- registers ----------------
    reg  [10:0] gx;                   // x of the next pixel to generate
    reg  [9:0]  gy;                   // y of the next pixel to generate
    reg         running;              // still pixels left in this frame
    reg  [2:0]  smoke_r;              // scene, latched at frame_start
    reg         lights_r;
    reg         cloth_r;
    reg         out_valid;            // output register (holds one pixel)
    reg  [23:0] out_rgb;

    // ---------------- next values ----------------
    reg  [10:0] gx_next;
    reg  [9:0]  gy_next;
    reg         running_next;
    reg         out_valid_next;
    reg  [23:0] out_rgb_next;
    reg         load;                 // generate a new pixel this cycle

    // ---------------- pattern wires ----------------
    reg  [7:0]  cell_v;
    reg  [7:0]  r0, g0, b0;           // background
    reg         in_smoke, in_cloth;
    reg  [7:0]  r1, g1, b1;           // after smoke and cloth
    reg  [8:0]  sum_r, sum_g, sum_b;  // after +40
    reg  [7:0]  r2, g2, b2;           // final pixel

    assign m_valid = out_valid;
    assign m_rgb   = out_rgb;

    // Smoke blend ((4-a)*c + a*128) >> 2, written as shift-and-add for each
    // strength a (a is constant during a frame, so this is a small mux, no multiplier)
    function [7:0] blend;
        input [7:0] c;
        input [2:0] a;
        reg   [9:0] t;
        begin
            case (a)
                3'd0: t = {c, 2'b00};                                  // 4c
                3'd1: t = {2'b00, c} + {1'b0, c, 1'b0} + 10'd128;      // 3c + 128
                3'd2: t = {1'b0, c, 1'b0} + 10'd256;                   // 2c + 256
                3'd3: t = {2'b00, c} + 10'd384;                        // c + 384
                default: t = 10'd512;                                  // a >= 4: flat 128
            endcase
            blend = t[9:2];
        end
    endfunction

    // Pattern: background texture for pixel (gx, gy)
    always @(*) begin
        if (gx[3] ^ gy[3])
            cell_v = 8'd140 + {4'd0, gx[6:3]};
        else
            cell_v = 8'd40 + {4'd0, gy[6:3]};
        r0 = cell_v + 8'd4;
        g0 = cell_v;
        b0 = cell_v - 8'd4;
    end

    // Pattern: smoke blend and red cloth
    always @(*) begin
        in_smoke = (gx >= SMOKE_X0) && (gx < SMOKE_X1) && (gy >= SMOKE_Y0) && (gy < SMOKE_Y1);
        in_cloth = cloth_r && (gx >= CLOTH_X0) && (gx < CLOTH_X1) && (gy >= CLOTH_Y0) && (gy < CLOTH_Y1);
        if (in_cloth) begin
            r1 = 8'd200; g1 = 8'd30; b1 = 8'd30;
        end else if (in_smoke) begin
            r1 = blend(r0, smoke_r); g1 = blend(g0, smoke_r); b1 = blend(b0, smoke_r);
        end else begin
            r1 = r0; g1 = g0; b1 = b0;
        end
    end

    // Pattern: global lighting change (+40, saturating at 255)
    always @(*) begin
        sum_r = {1'b0, r1} + 9'd40;
        sum_g = {1'b0, g1} + 9'd40;
        sum_b = {1'b0, b1} + 9'd40;
        if (lights_r) begin
            r2 = sum_r[8] ? 8'd255 : sum_r[7:0];
            g2 = sum_g[8] ? 8'd255 : sum_g[7:0];
            b2 = sum_b[8] ? 8'd255 : sum_b[7:0];
        end else begin
            r2 = r1; g2 = g1; b2 = b1;
        end
    end

    // Next state: raster counters and the output handshake
    always @(*) begin
        load           = running && !pause && (!out_valid || m_ready);
        gx_next        = gx;
        gy_next        = gy;
        running_next   = running;
        out_valid_next = out_valid;
        out_rgb_next   = out_rgb;
        if (out_valid && m_ready)
            out_valid_next = 1'b0;                 // pixel taken
        if (load) begin
            out_valid_next = 1'b1;                 // present the new pixel
            out_rgb_next   = {b2, g2, r2};
            if (gx == IMG_W - 1) begin
                gx_next = 11'd0;
                if (gy == IMG_H - 1) begin
                    gy_next      = 10'd0;
                    running_next = 1'b0;           // last pixel of the frame
                end else begin
                    gy_next = gy + 10'd1;
                end
            end else begin
                gx_next = gx + 11'd1;
            end
        end
    end

    // State registers
    always @(posedge clk) begin
        if (rst) begin
            gx        <= 11'd0;
            gy        <= 10'd0;
            running   <= 1'b0;
            smoke_r   <= 3'd0;
            lights_r  <= 1'b0;
            cloth_r   <= 1'b0;
            out_valid <= 1'b0;
            out_rgb   <= 24'd0;
        end else if (frame_start) begin
            gx        <= 11'd0;
            gy        <= 10'd0;
            running   <= 1'b1;
            smoke_r   <= scene_smoke;
            lights_r  <= scene_lights;
            cloth_r   <= scene_cloth;
            out_valid <= 1'b0;
        end else begin
            gx        <= gx_next;
            gy        <= gy_next;
            running   <= running_next;
            out_valid <= out_valid_next;
            out_rgb   <= out_rgb_next;
        end
    end

endmodule
