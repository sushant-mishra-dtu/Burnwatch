// -----------------------------------------------------------------------------
// bw_sdp_ram.v
// Simple dual-port RAM: one synchronous write port, one registered read port.
// Written in the Vivado (UG901) inference template, so it maps to block RAM
// (or LUT RAM when small). The RAM starts at all zeros (BRAM INIT values).
// A read and a write to the SAME address in the same cycle returns the OLD
// value; the BurnWatch pipelines never do this.
// -----------------------------------------------------------------------------
`timescale 1ns / 1ps
module bw_sdp_ram #(
    parameter DW = 8,                 // data width
    parameter AW = 12                 // address width (depth = 2**AW)
) (
    input  wire          clk,
    input  wire          we,          // write enable
    input  wire [AW-1:0] waddr,       // write address
    input  wire [DW-1:0] wdata,       // write data
    input  wire          re,          // read enable (rdata holds when re = 0)
    input  wire [AW-1:0] raddr,       // read address
    output reg  [DW-1:0] rdata        // read data, one clock after raddr
);

    reg [DW-1:0] mem [0:(1<<AW)-1];

    // Power-up contents: all zeros (becomes the BRAM INIT attribute)
    integer i;
    initial begin
        for (i = 0; i < (1<<AW); i = i + 1)
            mem[i] = {DW{1'b0}};
        rdata = {DW{1'b0}};
    end

    // Write port
    always @(posedge clk) begin
        if (we)
            mem[waddr] <= wdata;
    end

    // Registered read port
    always @(posedge clk) begin
        if (re)
            rdata <= mem[raddr];
    end

endmodule
