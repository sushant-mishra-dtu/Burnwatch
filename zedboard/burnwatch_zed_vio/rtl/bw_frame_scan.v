// -----------------------------------------------------------------------------
// bw_frame_scan.v   (Part A, stage 1)
// Frame scanner: takes pixels from the input stream in raster order and tags
// each one with its row/column.
//
// The 3x3 Sobel window gives the edge value of pixel (r, c) only once pixel
// (r+1, c+1) has arrived. To flush the last column and the last row, the
// scanner walks (IMG_H+1) x (IMG_W+1) "slots": slot (ir, ic) with ic = IMG_W
// or ir = IMG_H is a padding slot that takes no input pixel and pushes a zero
// pixel instead. Those padding values only ever reach border pixels, whose
// edge value is forced to 0, exactly like golden.py.
//
// Throughput: one slot per clock while the input has data, so one frame takes
// (IMG_H+1)*(IMG_W+1) = 923,601 clocks at 1280x720 (9.24 ms at 100 MHz).
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps
module bw_frame_scan #(
    parameter IMG_W = 1280,
    parameter IMG_H = 720
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        frame_start,   // 1-cycle pulse: start scanning a new frame
    // pixel stream in
    input  wire        s_valid,
    output wire        s_ready,
    input  wire [23:0] s_rgb,
    // stage-1 output (registered)
    output reg         p_valid,       // one slot advanced this cycle
    output reg  [9:0]  p_ir,          // slot row    0..IMG_H
    output reg  [10:0] p_ic,          // slot column 0..IMG_W
    output reg  [23:0] p_rgb          // pixel, or 0 in a padding slot
);

    reg  [9:0]  ir;                   // current slot
    reg  [10:0] ic;
    reg         running;

    reg  [9:0]  ir_next;
    reg  [10:0] ic_next;
    reg         running_next;
    reg         slot_pad;             // this slot is padding (no input pixel)
    reg         fire;                 // the slot advances this cycle

    assign s_ready = running && !slot_pad;

    // Slot type, handshake and next slot position
    always @(*) begin
        slot_pad     = (ic == IMG_W) || (ir == IMG_H);
        fire         = running && (slot_pad || s_valid);
        ir_next      = ir;
        ic_next      = ic;
        running_next = running;
        if (fire) begin
            if (ic == IMG_W) begin
                ic_next = 11'd0;
                if (ir == IMG_H) begin
                    ir_next      = 10'd0;
                    running_next = 1'b0;   // last slot: frame fully scanned
                end else begin
                    ir_next = ir + 10'd1;
                end
            end else begin
                ic_next = ic + 11'd1;
            end
        end
    end

    // Slot counters
    always @(posedge clk) begin
        if (rst) begin
            ir      <= 10'd0;
            ic      <= 11'd0;
            running <= 1'b0;
        end else if (frame_start) begin
            ir      <= 10'd0;
            ic      <= 11'd0;
            running <= 1'b1;
        end else begin
            ir      <= ir_next;
            ic      <= ic_next;
            running <= running_next;
        end
    end

    // Stage-1 output register
    always @(posedge clk) begin
        if (rst || frame_start) begin
            p_valid <= 1'b0;
        end else begin
            p_valid <= fire;
        end
        p_ir  <= ir;
        p_ic  <= ic;
        p_rgb <= slot_pad ? 24'd0 : s_rgb;
    end

endmodule
