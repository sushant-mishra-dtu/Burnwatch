// -----------------------------------------------------------------------------
// bw_tile_accum.v   (Part A, stage 5)
// Tile means, as golden.tile_means(): every 16x16 tile gets
//   mE = sum(E) >> 8,  mY = sum(Y) >> 8,  mS = sum(S) >> 8      (0..255)
//
// Pixels arrive in raster order. A running sum adds the 16 pixels of one tile
// row-segment; at the 16th pixel the segment is added to that tile column's
// partial sum in a small RAM (one entry per tile column, 3 x 16 bits). On the
// last pixel of the tile's last row the tile is complete and is sent out.
// Tiles leave in raster order (tile index ty*TILES_X + tx), one tile every
// 16 clocks during the last pixel row of each tile row.
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps
module bw_tile_accum #(
    parameter TILES_X = 80,
    parameter TILES_Y = 45
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        frame_start,   // restart the tile index at 0
    input  wire        in_valid,      // one pixel (r, c) with its Y, S, E
    input  wire [9:0]  in_r,
    input  wire [10:0] in_c,
    input  wire [7:0]  in_y,
    input  wire [7:0]  in_s,
    input  wire [7:0]  in_e,
    output reg         t_valid,       // one finished tile
    output reg  [11:0] t_idx,         // tile index, raster order
    output reg         t_last,        // last tile of the frame
    output reg  [7:0]  t_me,
    output reg  [7:0]  t_my,
    output reg  [7:0]  t_ms
);

    localparam N_TILES = TILES_X * TILES_Y;

    // ---------------- registers ----------------
    reg  [11:0] run_e, run_y, run_s;      // running sum of the current 16-pixel segment
    reg  [11:0] tile_cnt;                 // index of the next tile to send

    // ---------------- wires ----------------
    wire [3:0]  col_in = in_c[3:0];       // pixel column inside the tile
    wire [3:0]  row_in = in_r[3:0];       // pixel row inside the tile
    wire [6:0]  tx     = in_c[10:4];      // tile column
    wire [47:0] acc_q;                    // partial sums of tile column tx {E, Y, S}
    reg  [11:0] seg_e, seg_y, seg_s;      // finished 16-pixel segment
    reg  [15:0] base_e, base_y, base_s;   // partial sums before this segment
    reg  [15:0] new_e, new_y, new_s;      // partial sums after this segment
    reg         seg_end;                  // 16th pixel of a segment
    reg         tile_end;                 // last pixel of a tile

    // Segment end, tile end and the new partial sums
    always @(*) begin
        seg_end  = in_valid && (col_in == 4'd15);
        tile_end = seg_end && (row_in == 4'd15);
        seg_e    = run_e + {4'd0, in_e};
        seg_y    = run_y + {4'd0, in_y};
        seg_s    = run_s + {4'd0, in_s};
        if (row_in == 4'd0) begin             // first row of a tile row: start from 0
            base_e = 16'd0;
            base_y = 16'd0;
            base_s = 16'd0;
        end else begin
            base_e = acc_q[47:32];
            base_y = acc_q[31:16];
            base_s = acc_q[15:0];
        end
        new_e = base_e + {4'd0, seg_e};
        new_y = base_y + {4'd0, seg_y};
        new_s = base_s + {4'd0, seg_s};
    end

    // Per-tile-column partial sums (read at the first pixel of a segment,
    // written at the 16th pixel)
    bw_sdp_ram #(.DW(48), .AW(7)) u_col_sums (
        .clk   (clk),
        .we    (seg_end),
        .waddr (tx),
        .wdata ({new_e, new_y, new_s}),
        .re    (in_valid && (col_in == 4'd0)),
        .raddr (tx),
        .rdata (acc_q)
    );

    // Running segment sums
    always @(posedge clk) begin
        if (in_valid) begin
            if (col_in == 4'd0) begin
                run_e <= {4'd0, in_e};
                run_y <= {4'd0, in_y};
                run_s <= {4'd0, in_s};
            end else begin
                run_e <= seg_e;
                run_y <= seg_y;
                run_s <= seg_s;
            end
        end
    end

    // Tile output register and tile index counter
    always @(posedge clk) begin
        if (rst) begin
            t_valid  <= 1'b0;
            tile_cnt <= 12'd0;
        end else if (frame_start) begin
            t_valid  <= 1'b0;
            tile_cnt <= 12'd0;
        end else begin
            t_valid <= tile_end;
            if (tile_end)
                tile_cnt <= tile_cnt + 12'd1;
        end
        t_idx  <= tile_cnt;
        t_last <= (tile_cnt == N_TILES - 1);
        t_me   <= new_e[15:8];
        t_my   <= new_y[15:8];
        t_ms   <= new_s[15:8];
    end

endmodule
