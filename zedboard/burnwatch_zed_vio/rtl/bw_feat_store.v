// -----------------------------------------------------------------------------
// bw_feat_store.v   Tile-feature monitor
// Watches the tile stream that enters Part B (or leaves Part A in Part-A-only
// tests), keeps the last frame's features of every tile in a RAM for VIO
// read-back, and sums them so one frame can be checked at a glance.
//   sum_e = sum of mE over all tiles, likewise sum_y, sum_s  (<= 3600*255 < 2^20)
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps
module bw_feat_store (
    input  wire        clk,
    input  wire        rst,
    input  wire        run_clear,     // new test
    input  wire        frame_start,   // new frame: restart the sums
    input  wire        t_valid,
    input  wire [11:0] t_idx,
    input  wire [7:0]  t_me,
    input  wire [7:0]  t_my,
    input  wire [7:0]  t_ms,
    output reg  [19:0] sum_e,
    output reg  [19:0] sum_y,
    output reg  [19:0] sum_s,
    input  wire [11:0] rd_idx,        // read-back (one clock latency)
    output wire [7:0]  rd_me,
    output wire [7:0]  rd_my,
    output wire [7:0]  rd_ms
);

    wire [23:0] feat_q;

    // Feature RAM: 4096 x {mE, mY, mS}
    bw_sdp_ram #(.DW(24), .AW(12)) u_feat_ram (
        .clk(clk),
        .we(t_valid), .waddr(t_idx), .wdata({t_me, t_my, t_ms}),
        .re(1'b1), .raddr(rd_idx), .rdata(feat_q)
    );

    assign rd_me = feat_q[23:16];
    assign rd_my = feat_q[15:8];
    assign rd_ms = feat_q[7:0];

    // Feature sums of the current frame
    always @(posedge clk) begin
        if (rst || run_clear || frame_start) begin
            sum_e <= 20'd0;
            sum_y <= 20'd0;
            sum_s <= 20'd0;
        end else if (t_valid) begin
            sum_e <= sum_e + {12'd0, t_me};
            sum_y <= sum_y + {12'd0, t_my};
            sum_s <= sum_s + {12'd0, t_ms};
        end
    end

endmodule
