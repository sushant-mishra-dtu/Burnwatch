`timescale 1ns / 1ps
`include "bw_sim_paths.svh"
module tb_tile_engine;
    localparam integer PIXELS=1280*720, NT=3600;
    reg ap_clk=0, ap_rst_n=0, ap_start=0, reset=0, update_this_frame=1;
    wire ap_idle, ap_done, scores_valid, gate_out;
    reg [3:0] k_slow, k_fast;
    reg [7:0] w_edge, w_grey, t_flag, sat_max;
    reg [4:0] score_shift;
    reg [15:0] sat_tol, t_global;
    reg [11:0] gate_tiles;
    wire [19:0] frame_addr;
    reg [31:0] frame_data;
    wire [7:0] scores;
    wire [11:0] scores_addr, changed_out;
    wire [31:0] frame_count;
    byte unsigned frame_bytes [0:PIXELS*4-1];
    byte unsigned expected_scores [0:NT-1];
    byte unsigned expected_state [0:21600];
    bit seen [0:NT-1];
    bit active=0;
    integer received=0, errors=0, total_frames=0, total_scores=0;
    integer frame_number=0, current_cycles=0, maximum_cycles=0, report_fd;
    string vector_root, report_path, current_set;
    tile_engine dut (.*);
    always #5 ap_clk = ~ap_clk;

    function automatic [31:0] pixel_word(input integer address);
        integer offset;
        begin
            offset = address * 4;
            if (address >= 0 && address < PIXELS)
                pixel_word = {frame_bytes[offset+3], frame_bytes[offset+2],
                              frame_bytes[offset+1], frame_bytes[offset]};
            else pixel_word = 0;
        end
    endfunction
    // File loads explicitly refresh frame_data. Avoid sensitivity to a 3.7 MB
    // array; the harness models the combinational memory port at each address.
    always @(frame_addr) frame_data = pixel_word(frame_addr);

    task automatic mismatch(input string message_text);
        begin
            if (errors < 10) $display("MISMATCH set=%s frame=%0d %s", current_set, frame_number, message_text);
            errors = errors + 1;
        end
    endtask

    always @(posedge ap_clk) begin
        if (active) begin
            current_cycles = current_cycles + 1;
            if (current_cycles > 2000000) $fatal(1, "Frame watchdog expired");
            if (scores_valid) begin
                if (scores_addr >= NT) mismatch("score address outside 45x80 grid");
                else begin
                    if (seen[scores_addr]) mismatch("duplicate tile score");
                    seen[scores_addr] = 1;
                    if (scores !== expected_scores[scores_addr])
                        mismatch($sformatf("tile=(%0d,%0d) expected=%0d got=%0d",
                            scores_addr/80, scores_addr%80, expected_scores[scores_addr], scores));
                end
                received = received + 1;
            end
        end
    end

    task automatic read_params(input string set_dir, output integer frames);
        integer fd, status, value, fields_seen;
        string line, key;
        begin
            fd = $fopen({set_dir,"/params.txt"}, "r");
            if (!fd) $fatal(1,"Cannot open %s/params.txt",set_dir);
            frames=0; fields_seen=0;
            while (!$feof(fd)) begin
                status=$fgets(line,fd);
                if ($sscanf(line,"%s %d",key,value)==2) begin
                    case (key)
                        "SPEC": if(value!=1) $fatal(1,"Unsupported vector spec");
                        "IMG_W": if(value!=1280) $fatal(1,"Expected 1280 pixels per row");
                        "IMG_H": if(value!=720) $fatal(1,"Expected 720 rows");
                        "TILE": if(value!=16) $fatal(1,"Expected 16x16 tiles");
                        "FRAMES": frames=value;
                        "K_SLOW": begin k_slow=value; fields_seen=fields_seen|1; end
                        "K_FAST": begin k_fast=value; fields_seen=fields_seen|2; end
                        "W_EDGE": begin w_edge=value; fields_seen=fields_seen|4; end
                        "W_GREY": begin w_grey=value; fields_seen=fields_seen|8; end
                        "SCORE_SHIFT": begin score_shift=value; fields_seen=fields_seen|16; end
                        "T_FLAG": begin t_flag=value; fields_seen=fields_seen|32; end
                        "SAT_MAX": begin sat_max=value; fields_seen=fields_seen|64; end
                        "SAT_TOL": begin sat_tol=value; fields_seen=fields_seen|128; end
                        "T_GLOBAL": begin t_global=value; fields_seen=fields_seen|256; end
                        "GATE_TILES": begin gate_tiles=value; fields_seen=fields_seen|512; end
                    endcase
                end
            end
            $fclose(fd);
            if(frames<40 || fields_seen!=1023) $fatal(1,"Incomplete vector parameters");
        end
    endtask

    task automatic run_set(input string set_name);
        integer frames, expectation_fd, fd, status, n, i, expected_no;
        integer expected_reset, expected_update, expected_gate, expected_changed;
        integer expected_frame_count, expected_bE, expected_bY, expected_bS;
        string set_dir, line, filename;
        bit have_state;
        begin
            current_set=set_name; set_dir={vector_root,"/",set_name};
            read_params(set_dir,frames);
            expectation_fd=$fopen({set_dir,"/expect.txt"},"r");
            if(!expectation_fd) $fatal(1,"Cannot open expect.txt");
            expected_frame_count=0;
            $display("START set=%s frames=%0d geometry=1280x720",set_name,frames);
            for(n=0;n<frames;n=n+1) begin
                status=0;
                while(status!=5 && !$feof(expectation_fd)) begin
                    status=$fgets(line,expectation_fd);
                    status=$sscanf(line,"%d %d %d %d %d",expected_no,expected_reset,
                                   expected_update,expected_gate,expected_changed);
                end
                if(status!=5 || expected_no!=n) $fatal(1,"Missing/misordered expectation for frame %0d",n);
                frame_number=n;
                filename=$sformatf("%s/frame_%04d.bin",set_dir,n);
                fd=$fopen(filename,"rb");
                if(!fd) $fatal(1,"Cannot open %s",filename);
                status=$fread(frame_bytes,fd); $fclose(fd);
                if(status!=PIXELS*4) $fatal(1,"Wrong frame file size: %s",filename);
                filename=$sformatf("%s/scores_%04d.bin",set_dir,n);
                fd=$fopen(filename,"rb");
                if(!fd) $fatal(1,"Cannot open %s",filename);
                status=$fread(expected_scores,fd); $fclose(fd);
                if(status!=NT) $fatal(1,"Wrong score file size");
                filename=$sformatf("%s/state_%04d.bin",set_dir,n);
                fd=$fopen(filename,"rb"); have_state=(fd!=0);
                if(have_state) begin
                    status=$fread(expected_state,fd); $fclose(fd);
                    if(status!=21601) $fatal(1,"Wrong state file size");
                end
                frame_data=pixel_word(frame_addr);
                @(negedge ap_clk);
                if(!ap_idle) $fatal(1,"Core not idle before frame");
                for(i=0;i<NT;i=i+1) seen[i]=0;
                received=0; current_cycles=0;
                reset=expected_reset; update_this_frame=expected_update;
                active=1; ap_start=1;
                @(negedge ap_clk); ap_start=0;
                wait(ap_done===1'b1);
                @(negedge ap_clk); active=0;
                if(received!=NT) mismatch($sformatf("expected 3600 scores, received %0d",received));
                for(i=0;i<NT;i=i+1) if(!seen[i]) mismatch($sformatf("missing tile %0d",i));
                if(gate_out !== (expected_gate!=0)) mismatch("gate differs from golden");
                if(changed_out !== 12'(expected_changed)) mismatch("changed differs from golden");
                expected_frame_count=expected_reset ? 1 : expected_frame_count+1;
                if(frame_count !== 32'(expected_frame_count)) mismatch("frame_count differs");
                if(have_state) begin
                    for(i=0;i<NT;i=i+1) begin
                        expected_bE=integer'(expected_state[2*i])+256*integer'(expected_state[2*i+1]);
                        expected_bY=integer'(expected_state[7200+2*i])+256*integer'(expected_state[7201+2*i]);
                        expected_bS=integer'(expected_state[14400+2*i])+256*integer'(expected_state[14401+2*i]);
                        if(dut.bE[i] !== 16'(expected_bE) || dut.bY[i] !== 16'(expected_bY) ||
                           dut.bS[i] !== 16'(expected_bS)) mismatch($sformatf("baseline tile %0d differs",i));
                    end
                    if(dut.prev_gate !== (expected_state[21600]!=0)) mismatch("prev_gate differs");
                end
                if(errors) $fatal(1,"Golden comparison failed: %0d mismatches",errors);
                if(current_cycles>maximum_cycles) maximum_cycles=current_cycles;
                total_frames=total_frames+1; total_scores=total_scores+received;
                $display("PASS set=%s frame=%0d scores=%0d gate=%0d changed=%0d cycles=%0d",
                    set_name,n,received,gate_out,changed_out,current_cycles);
            end
            $fclose(expectation_fd);
        end
    endtask

    initial begin
        vector_root=`BW_VECTOR_ROOT;
        report_path=`BW_REPORT_PATH;
        report_fd=$fopen(report_path,"w");
        if(!report_fd) $fatal(1,"Cannot create report %s",report_path);
        repeat(5) @(negedge ap_clk);
        ap_rst_n=1;
        run_set("synthetic");
        run_set("synthetic-u3");
        $display("BURNWATCH RTL PASS frames=%0d tile_scores=%0d mismatches=%0d max_cycles=%0d",
                 total_frames,total_scores,errors,maximum_cycles);
        $fdisplay(report_fd,"BURNWATCH RTL PASS frames=%0d tile_scores=%0d mismatches=%0d max_cycles=%0d",
                  total_frames,total_scores,errors,maximum_cycles);
        $fdisplay(report_fd,"Clock period: 10 ns. Simulated core cycles, not measured board throughput.");
        $fclose(report_fd);
        $finish;
    end
endmodule
