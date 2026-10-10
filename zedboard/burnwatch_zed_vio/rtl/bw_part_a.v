// -----------------------------------------------------------------------------
// bw_part_a.v   PART A: pixel feature extractor (pixels -> tile features)
// Hardware for golden.pixel_features() + golden.tile_means() in FULL mode.
//
//   pixel stream --> bw_frame_scan --> bw_pixel_feat --> bw_sobel_window --> bw_tile_accum --> tiles
//   (valid/ready)    slot (ir, ic)     Y, S             centre pixel Y,S,E   mE, mY, mS per tile
//
// Every pixel is processed: 1280x720 in, 3,600 tile triples out per frame.
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps
module bw_part_a #(
    parameter IMG_W   = 1280,
    parameter IMG_H   = 720,
    parameter TILES_X = 80,
    parameter TILES_Y = 45
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        frame_start,
    // pixel stream in
    input  wire        s_valid,
    output wire        s_ready,
    input  wire [23:0] s_rgb,
    // tile stream out
    output wire        t_valid,
    output wire [11:0] t_idx,
    output wire        t_last,
    output wire [7:0]  t_me,
    output wire [7:0]  t_my,
    output wire [7:0]  t_ms,
    output wire        frame_done      // the last tile is on the output this cycle
);

    // scanner -> pixel features
    wire        p_valid;
    wire [9:0]  p_ir;
    wire [10:0] p_ic;
    wire [23:0] p_rgb;
    wire [7:0]  p_y, p_s;

    // Sobel -> tile accumulator
    wire        c_valid;
    wire [9:0]  c_r;
    wire [10:0] c_c;
    wire [7:0]  c_y, c_s, c_e;

    // Stage 1: frame scanner (slot counters + padding)
    bw_frame_scan #(.IMG_W(IMG_W), .IMG_H(IMG_H)) u_scan (
        .clk(clk), .rst(rst), .frame_start(frame_start),
        .s_valid(s_valid), .s_ready(s_ready), .s_rgb(s_rgb),
        .p_valid(p_valid), .p_ir(p_ir), .p_ic(p_ic), .p_rgb(p_rgb)
    );

    // Stage 2 arithmetic: luma Y and saturation S
    bw_pixel_feat u_pix (
        .rgb(p_rgb), .y(p_y), .s(p_s)
    );

    // Stages 2-4: line buffer, 3x3 window, Sobel edge E
    bw_sobel_window #(.IMG_W(IMG_W), .IMG_H(IMG_H)) u_sobel (
        .clk(clk), .rst(rst),
        .in_valid(p_valid), .in_ir(p_ir), .in_ic(p_ic), .in_y(p_y), .in_s(p_s),
        .out_valid(c_valid), .out_r(c_r), .out_c(c_c),
        .out_y(c_y), .out_s(c_s), .out_e(c_e)
    );

    // Stage 5: 16x16 tile sums -> tile means
    bw_tile_accum #(.TILES_X(TILES_X), .TILES_Y(TILES_Y)) u_accum (
        .clk(clk), .rst(rst), .frame_start(frame_start),
        .in_valid(c_valid), .in_r(c_r), .in_c(c_c),
        .in_y(c_y), .in_s(c_s), .in_e(c_e),
        .t_valid(t_valid), .t_idx(t_idx), .t_last(t_last),
        .t_me(t_me), .t_my(t_my), .t_ms(t_ms)
    );

    assign frame_done = t_valid && t_last;

endmodule
