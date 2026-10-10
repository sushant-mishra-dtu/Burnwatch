// -----------------------------------------------------------------------------
// bw_sobel_window.v   (Part A, stages 2-4)
// Two-line buffer + 3x3 window + Sobel edge strength, as golden.pixel_features():
//   Gx = (Y[r-1,c+1] + 2Y[r,c+1] + Y[r+1,c+1]) - (Y[r-1,c-1] + 2Y[r,c-1] + Y[r+1,c-1])
//   Gy = (Y[r+1,c-1] + 2Y[r+1,c] + Y[r+1,c+1]) - (Y[r-1,c-1] + 2Y[r-1,c] + Y[r-1,c+1])
//   E  = (|Gx| + |Gy|) >> 3, and E = 0 on the 1-pixel image border.
//
// Input: one scan slot (ir, ic) with that pixel's Y and S (from bw_pixel_feat).
// Output: the CENTRE pixel (r, c) = (ir-1, ic-1) with its Y, S and E, so every
// output is aligned to its own pixel position (the 1-row/1-column latency of
// the window is absorbed here).
//
// Line buffer word (one per column): {Y row ir-1, S row ir-1, Y row ir-2}.
//   stage A : register the slot, read the line buffer at column ic
//   stage B : shift the window by one column, write the line buffer back
//   stage C : Sobel arithmetic and border test, register the centre pixel
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps
module bw_sobel_window #(
    parameter IMG_W = 1280,
    parameter IMG_H = 720
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        in_valid,      // one slot
    input  wire [9:0]  in_ir,
    input  wire [10:0] in_ic,
    input  wire [7:0]  in_y,
    input  wire [7:0]  in_s,
    output reg         out_valid,     // one centre pixel
    output reg  [9:0]  out_r,
    output reg  [10:0] out_c,
    output reg  [7:0]  out_y,
    output reg  [7:0]  out_s,
    output reg  [7:0]  out_e
);

    // ---------------- stage A registers ----------------
    reg         a_valid;
    reg  [9:0]  a_ir;
    reg  [10:0] a_ic;
    reg  [7:0]  a_y, a_s;

    // ---------------- line buffer ----------------
    wire [23:0] lb_q;                 // {mid_y, mid_s, top_y} of column a_ic
    wire [7:0]  lb_mid_y = lb_q[23:16];
    wire [7:0]  lb_mid_s = lb_q[15:8];
    wire [7:0]  lb_top_y = lb_q[7:0];

    // ---------------- window registers (stage B) ----------------
    // column 0 = oldest (c-1), column 1 = centre (c), column 2 = newest (c+1)
    // t = row r-1, m = row r, b = row r+1
    reg  [7:0]  w0t, w0m, w0b;
    reg  [7:0]  w1t, w1m, w1b, w1s;
    reg  [7:0]  w2t, w2m, w2b, w2s;
    reg         b_valid;              // window holds a centre pixel to emit
    reg  [9:0]  b_r;
    reg  [10:0] b_c;

    // ---------------- Sobel wires ----------------
    reg  [9:0]  sum_left, sum_right, sum_top, sum_bot;   // each <= 4*255 = 1020
    reg  [10:0] abs_gx, abs_gy;
    reg  [11:0] mag;                                     // |Gx| + |Gy| <= 2040
    reg         border;
    reg  [7:0]  e_val;

    // Stage A: register the slot (line buffer read happens in parallel)
    always @(posedge clk) begin
        if (rst)
            a_valid <= 1'b0;
        else
            a_valid <= in_valid;
        a_ir <= in_ir;
        a_ic <= in_ic;
        a_y  <= in_y;
        a_s  <= in_s;
    end

    // Line buffer: read column in_ic now, write column a_ic back one cycle later
    bw_sdp_ram #(.DW(24), .AW(11)) u_line_buf (
        .clk   (clk),
        .we    (a_valid),
        .waddr (a_ic),
        .wdata ({a_y, a_s, lb_mid_y}),   // new row becomes "mid", old mid becomes "top"
        .re    (in_valid),
        .raddr (in_ic),
        .rdata (lb_q)
    );

    // Stage B: shift the 3x3 window and tag the centre pixel
    always @(posedge clk) begin
        if (rst) begin
            b_valid <= 1'b0;
        end else begin
            b_valid <= a_valid && (a_ir != 10'd0) && (a_ic != 11'd0);
        end
        if (a_valid) begin
            w0t <= w1t;  w0m <= w1m;  w0b <= w1b;
            w1t <= w2t;  w1m <= w2m;  w1b <= w2b;  w1s <= w2s;
            w2t <= lb_top_y;
            w2m <= lb_mid_y;
            w2b <= a_y;
            w2s <= lb_mid_s;
            b_r <= a_ir - 10'd1;
            b_c <= a_ic - 11'd1;
        end
    end

    // Sobel: column sums and row sums (1-2-1 weights)
    always @(*) begin
        sum_left  = {2'b00, w0t} + {1'b0, w0m, 1'b0} + {2'b00, w0b};
        sum_right = {2'b00, w2t} + {1'b0, w2m, 1'b0} + {2'b00, w2b};
        sum_top   = {2'b00, w0t} + {1'b0, w1t, 1'b0} + {2'b00, w2t};
        sum_bot   = {2'b00, w0b} + {1'b0, w1b, 1'b0} + {2'b00, w2b};
    end

    // Sobel: |Gx| + |Gy|, >> 3, border forced to 0
    always @(*) begin
        abs_gx = (sum_right >= sum_left) ? ({1'b0, sum_right} - {1'b0, sum_left})
                                         : ({1'b0, sum_left}  - {1'b0, sum_right});
        abs_gy = (sum_bot >= sum_top)    ? ({1'b0, sum_bot}   - {1'b0, sum_top})
                                         : ({1'b0, sum_top}   - {1'b0, sum_bot});
        mag    = {1'b0, abs_gx} + {1'b0, abs_gy};
        border = (b_r == 10'd0) || (b_r == IMG_H - 1) || (b_c == 11'd0) || (b_c == IMG_W - 1);
        e_val  = border ? 8'd0 : mag[10:3];
    end

    // Stage C: register the centre pixel with its features
    always @(posedge clk) begin
        if (rst)
            out_valid <= 1'b0;
        else
            out_valid <= b_valid;
        out_r <= b_r;
        out_c <= b_c;
        out_y <= w1m;
        out_s <= w1s;
        out_e <= e_val;
    end

endmodule
