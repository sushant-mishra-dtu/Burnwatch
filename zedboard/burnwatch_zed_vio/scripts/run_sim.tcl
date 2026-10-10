# -----------------------------------------------------------------------------
# run_sim.tcl  -  behavioural simulation in the Vivado simulator (xsim)
#
#   source scripts/run_sim.tcl                -> tb_bw_system, QUICK 320x192 (fast)
#   set bw_sim full;  source scripts/run_sim.tcl   -> tb_bw_system, 1280x720 (~32 M clocks, slow)
#   set bw_sim unit;  source scripts/run_sim.tcl   -> tb_bw_tile_score (Part B datapath)
#
# The testbench prints PASS/FAIL lines and finally "TB_BW_SYSTEM PASS" or
# "TB_BW_SYSTEM FAIL" (or TB_TILE_SCORE ...) in the Tcl console.
# -----------------------------------------------------------------------------

set origin    [file normalize [file join [file dirname [info script]] ..]]
set proj_name burnwatch_zed_vio
set proj_file [file join $origin vivado $proj_name.xpr]

if {[catch {current_project}]} {
    open_project $proj_file
}
if {![info exists bw_sim]} { set bw_sim quick }

catch {close_sim -force -quiet}
switch -- $bw_sim {
    full {
        set_property top tb_bw_system [get_filesets sim_1]
        set_property verilog_define {} [get_filesets sim_1]
    }
    unit {
        set_property top tb_bw_tile_score [get_filesets sim_1]
        set_property verilog_define {} [get_filesets sim_1]
    }
    default {
        set_property top tb_bw_system [get_filesets sim_1]
        set_property verilog_define {QUICK} [get_filesets sim_1]
    }
}
update_compile_order -fileset sim_1

# make sure the expected-data files are in the simulation folder
set xsim_dir [file join $origin vivado $proj_name.sim sim_1 behav xsim]
file mkdir $xsim_dir
foreach f [glob [file join $origin sim expected *.mem]] {
    file copy -force $f $xsim_dir
}

# xsim.simulate.runtime is "-all" (set by create_project.tcl): runs to $finish
launch_simulation -simset sim_1 -mode behavioral
puts "Simulation ($bw_sim) finished: look for TB_BW_SYSTEM / TB_TILE_SCORE PASS above."
