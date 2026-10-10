`timescale 1ns / 1ps
// Native standalone scoring core. Algorithm: detector/golden.py, spec v1.
// The frame address/data and score-valid ports are private simulation-harness
// connections, not the AXI interfaces of the planned PYNQ overlay.
module tile_engine (
    input  wire        ap_clk,
    input  wire        ap_rst_n,
    input  wire        ap_start,
    output wire        ap_idle,
    output reg         ap_done,
    input  wire        reset,
    input  wire        update_this_frame,
    input  wire [3:0]  k_slow, k_fast,
    input  wire [7:0]  w_edge, w_grey,
    input  wire [4:0]  score_shift,
    input  wire [7:0]  t_flag, sat_max,
    input  wire [15:0] sat_tol, t_global,
    input  wire [11:0] gate_tiles,
    output wire [19:0] frame_addr,
    input  wire [31:0] frame_data,
    output reg  [7:0]  scores,
    output reg  [11:0] scores_addr,
    output reg         scores_valid,
    output reg         gate_out,
    output reg  [11:0] changed_out,
    output reg  [31:0] frame_count
);
    localparam integer W = 1280, H = 720, TX = 80, NT = 3600;
    localparam [2:0] IDLE=0, CLEAR=1, READ_ROW=2, SCORE=4, FINISH=5;
    reg [2:0] phase;
    reg [10:0] col;
    reg [9:0] row;
    reg [11:0] tile_index;
    reg [1:0] ring;
    reg reset_pending, reset_frame, update_frame, prev_gate;
    reg [3:0] slow_q, fast_q;
    reg [7:0] edge_q, grey_q, flag_q, sat_q;
    reg [4:0] shift_q;
    reg [15:0] sat_tol_q, global_q;
    reg [11:0] gate_tiles_q;
    reg [7:0] line0 [0:W-1];
    reg [7:0] line1 [0:W-1];
    reg [7:0] line2 [0:W-1];
    reg [7:0] ul, uc, ml, mc, dl, dc;
    reg [15:0] sumE [0:NT-1];
    reg [15:0] sumY [0:NT-1];
    reg [15:0] sumS [0:NT-1];
    reg [15:0] bE [0:NT-1];
    reg [15:0] bY [0:NT-1];
    reg [15:0] bS [0:NT-1];
    integer red, green, blue, max_rgb, min_rgb, luminance, saturation;
    integer ur, mr, dr, gx, gy, edge_value, input_tile, edge_tile;
    integer xE, xY, xS, edge_drop, grey_shift, raw_score, tile_score;
    integer baseline_distance, current_distance, deltaY, changed_next, update_k;

    function automatic integer abs_i(input integer value);
        abs_i = (value < 0) ? -value : value;
    endfunction

    function automatic [15:0] update_b(input [15:0] baseline,
                                      input integer feature, input integer k);
        integer signed delta, result_value;
        begin
            delta = feature - integer'(baseline) + ((1 << k) >> 1);
            result_value = integer'(baseline) + (delta >>> k);
            update_b = result_value[15:0];
        end
    endfunction

    assign ap_idle = (phase == IDLE);
    assign frame_addr = row * W + col;

    always @* begin
        red = {24'b0, frame_data[7:0]};
        green = {24'b0, frame_data[15:8]};
        blue = {24'b0, frame_data[23:16]};
        max_rgb = red;
        if (green > max_rgb) max_rgb = green;
        if (blue > max_rgb) max_rgb = blue;
        min_rgb = red;
        if (green < min_rgb) min_rgb = green;
        if (blue < min_rgb) min_rgb = blue;
        luminance = (77*red + 150*green + 29*blue) >> 8;
        saturation = max_rgb - min_rgb;
        input_tile = (row >> 4) * TX + (col >> 4);
        // Read the previous two rows before writing this pixel into the oldest
        // line buffer. The new luma value supplies the bottom/right neighbour.
        case (ring)
            0: begin ur=line1[col]; mr=line2[col]; end
            1: begin ur=line2[col]; mr=line0[col]; end
            default: begin ur=line0[col]; mr=line1[col]; end
        endcase
        dr = luminance;
        gx = ur + 2*mr + dr - integer'(ul) - 2*integer'(ml) - integer'(dl);
        gy = integer'(dl) + 2*integer'(dc) + dr - integer'(ul) - 2*integer'(uc) - ur;
        edge_value = (abs_i(gx) + abs_i(gy)) >> 3;
        edge_tile = ((integer'(row)-1) >> 4)*TX + ((integer'(col)-1) >> 4);
        xE = (integer'(sumE[tile_index]) >> 8) << 8;
        xY = (integer'(sumY[tile_index]) >> 8) << 8;
        xS = (integer'(sumS[tile_index]) >> 8) << 8;
        edge_drop = integer'(bE[tile_index]) - xE;
        if (edge_drop < 0) edge_drop = 0;
        baseline_distance = abs_i(integer'(bY[tile_index]) - 32768);
        current_distance = abs_i(xY - 32768);
        grey_shift = baseline_distance - current_distance;
        if (grey_shift < 0) grey_shift = 0;
        raw_score = (integer'(edge_q)*edge_drop + integer'(grey_q)*grey_shift) >> shift_q;
        tile_score = (raw_score > 255) ? 255 : raw_score;
        if ((integer'(sumS[tile_index]) >> 8) > sat_q ||
            xS > integer'(bS[tile_index]) + integer'(sat_tol_q)) tile_score = 0;
        deltaY = abs_i(xY - integer'(bY[tile_index]));
        changed_next = integer'(changed_out);
        if (!reset_frame && deltaY > global_q) changed_next = changed_next + 1;
        if (reset_frame) tile_score = 0;
        update_k = prev_gate ? integer'(fast_q) : integer'(slow_q);
    end

    always @(posedge ap_clk) begin
        if (!ap_rst_n) begin
            phase <= IDLE;
            col <= 0; row <= 0; ring <= 0; tile_index <= 0;
            reset_pending <= 1; reset_frame <= 0; update_frame <= 0;
            prev_gate <= 0; ap_done <= 0; gate_out <= 0;
            changed_out <= 0; frame_count <= 0;
            scores <= 0; scores_addr <= 0; scores_valid <= 0;
            ul <= 0; uc <= 0; ml <= 0; mc <= 0; dl <= 0; dc <= 0;
            slow_q <= 0; fast_q <= 0; edge_q <= 0; grey_q <= 0;
            flag_q <= 0; sat_q <= 0; shift_q <= 0;
            sat_tol_q <= 0; global_q <= 0; gate_tiles_q <= 0;
        end else begin
            ap_done <= 0;
            scores_valid <= 0;
            case (phase)
                IDLE: if (ap_start) begin
                    reset_frame <= reset | reset_pending;
                    update_frame <= update_this_frame;
                    slow_q <= k_slow; fast_q <= k_fast;
                    edge_q <= w_edge; grey_q <= w_grey;
                    flag_q <= t_flag; sat_q <= sat_max; shift_q <= score_shift;
                    sat_tol_q <= sat_tol; global_q <= t_global; gate_tiles_q <= gate_tiles;
                    tile_index <= 0; row <= 0; col <= 0; ring <= 0;
                    ul <= 0; uc <= 0; ml <= 0; mc <= 0; dl <= 0; dc <= 0;
                    changed_out <= 0; gate_out <= 0;
                    phase <= CLEAR;
                end
                CLEAR: begin
                    sumE[tile_index] <= 0;
                    sumY[tile_index] <= 0;
                    sumS[tile_index] <= 0;
                    if (tile_index == NT-1) begin
                        tile_index <= 0;
                        phase <= READ_ROW;
                    end else tile_index <= tile_index + 1;
                end
                READ_ROW: begin
                    case (ring)
                        0: line0[col] <= luminance[7:0];
                        1: line1[col] <= luminance[7:0];
                        default: line2[col] <= luminance[7:0];
                    endcase
                    sumY[input_tile] <= sumY[input_tile] + luminance;
                    sumS[input_tile] <= sumS[input_tile] + saturation;
                    ul <= uc; uc <= ur[7:0];
                    ml <= mc; mc <= mr[7:0];
                    dl <= dc; dc <= dr[7:0];
                    // The edge belongs to (row-1,col-1), not to this pixel's tile.
                    // Only interior pixels contribute; the image border is zero.
                    if (row >= 2 && col >= 2)
                        sumE[edge_tile] <= sumE[edge_tile] + edge_value;
                    if (col == W-1) begin
                        col <= 0;
                        ul <= 0; uc <= 0; ml <= 0; mc <= 0; dl <= 0; dc <= 0;
                        if (row == H-1) begin
                            tile_index <= 0;
                            phase <= SCORE;
                        end else begin
                            row <= row + 1;
                            ring <= (ring == 2) ? 0 : ring + 1;
                        end
                    end else col <= col + 1;
                end
                SCORE: begin
                    scores <= tile_score[7:0];
                    scores_addr <= tile_index;
                    scores_valid <= 1;
                    changed_out <= changed_next[11:0];
                    if (reset_frame) begin
                        bE[tile_index] <= xE[15:0];
                        bY[tile_index] <= xY[15:0];
                        bS[tile_index] <= xS[15:0];
                    end else if (update_frame && (prev_gate || tile_score < flag_q)) begin
                        bE[tile_index] <= update_b(bE[tile_index], xE, update_k);
                        bY[tile_index] <= update_b(bY[tile_index], xY, update_k);
                        bS[tile_index] <= update_b(bS[tile_index], xS, update_k);
                    end
                    if (tile_index == NT-1) begin
                        gate_out <= (changed_next > gate_tiles_q);
                        prev_gate <= (changed_next > gate_tiles_q);
                        reset_pending <= 0;
                        frame_count <= reset_frame ? 1 : frame_count + 1;
                        phase <= FINISH;
                    end else tile_index <= tile_index + 1;
                end
                FINISH: begin ap_done <= 1; phase <= IDLE; end
                default: phase <= IDLE;
            endcase
        end
    end
endmodule
