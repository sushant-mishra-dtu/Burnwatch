// -----------------------------------------------------------------------------
// bw_pixel_feat.v   (Part A, stage 2 arithmetic, purely combinational)
// Per-pixel luma and saturation, exactly as golden.pixel_features():
//   Y = (77*R + 150*G + 29*B) >> 8          0..255
//   S = max(R, G, B) - min(R, G, B)        0..255
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps
module bw_pixel_feat (
    input  wire [23:0] rgb,           // {B, G, R}
    output reg  [7:0]  y,
    output reg  [7:0]  s
);

    reg [7:0]  r, g, b;
    reg [15:0] y_sum;                 // 77*255 + 150*255 + 29*255 = 65280 fits 16 bits
    reg [7:0]  mx, mn;

    // Luma: weighted sum, then >> 8
    always @(*) begin
        r     = rgb[7:0];
        g     = rgb[15:8];
        b     = rgb[23:16];
        y_sum = 16'd77 * r + 16'd150 * g + 16'd29 * b;
        y     = y_sum[15:8];
    end

    // Saturation: max - min of the three channels
    always @(*) begin
        mx = r;
        if (g > mx) mx = g;
        if (b > mx) mx = b;
        mn = r;
        if (g < mn) mn = g;
        if (b < mn) mn = b;
        s = mx - mn;
    end

endmodule
