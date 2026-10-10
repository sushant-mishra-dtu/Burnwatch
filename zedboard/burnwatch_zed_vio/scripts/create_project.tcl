# -----------------------------------------------------------------------------
# create_project.tcl  -  BurnWatch tile engine + VIO demo, ZedBoard, Vivado 2022.1
#
# Creates vivado/burnwatch_zed_vio.xpr next to this package:
#   * part xc7z020clg484-1 (ZedBoard board part set too, if installed)
#   * rtl/*.v in sources_1 (top bw_top_zed), constrs/zedboard_bw.xdc in constrs_1
#   * sim/*.v + sim/expected/*.mem in sim_1 (top tb_bw_system, QUICK geometry)
#   * the VIO IP vio_0 (28 input probes, 6 output probes), output products
#     generated and its out-of-context synthesis run created
#
# Run from the package root, either
#   vivado -mode batch -source scripts/create_project.tcl
# or in the Vivado Tcl console:
#   cd <package root>
#   source scripts/create_project.tcl
# -----------------------------------------------------------------------------

set origin    [file normalize [file join [file dirname [info script]] ..]]
set proj_name burnwatch_zed_vio
set proj_dir  [file join $origin vivado]
set part      xc7z020clg484-1

if {[file exists [file join $proj_dir $proj_name.xpr]]} {
    puts "NOTE: replacing the existing project in $proj_dir"
}
create_project $proj_name $proj_dir -part $part -force

# Board part (optional: the design uses only the PL, the GCLK pin and LEDs)
set bp [get_board_parts -quiet -latest_file_version {*zedboard*}]
if {[llength $bp] > 0} {
    set_property board_part [lindex $bp 0] [current_project]
    puts "Board part: [lindex $bp 0]"
} else {
    puts "Board files for ZedBoard not installed: using the bare part $part (fine for this design)"
}
set_property target_language    Verilog [current_project]
set_property simulator_language Verilog [current_project]
set_property default_lib        xil_defaultlib [current_project]

# ---------------- design sources ----------------
add_files -norecurse -fileset sources_1 [lsort [glob [file join $origin rtl *.v]]]
set_property top bw_top_zed [get_filesets sources_1]

# ---------------- constraints ----------------
add_files -norecurse -fileset constrs_1 [file join $origin constrs zedboard_bw.xdc]
set_property target_constrs_file [file join $origin constrs zedboard_bw.xdc] [current_fileset -constrset]

# ---------------- simulation sources ----------------
add_files -norecurse -fileset sim_1 [list \
    [file join $origin sim tb_bw_system.v] \
    [file join $origin sim tb_bw_tile_score.v]]
add_files -norecurse -fileset sim_1 [lsort [glob [file join $origin sim expected *.mem]]]
set_property top tb_bw_system [get_filesets sim_1]
set_property top_lib xil_defaultlib [get_filesets sim_1]
# QUICK = 320x192 geometry (fast). Remove the define for the full 1280x720 run.
set_property verilog_define {QUICK} [get_filesets sim_1]
set_property -name {xsim.simulate.runtime} -value {-all} -objects [get_filesets sim_1]
set_property -name {xsim.simulate.log_all_signals} -value {false} -objects [get_filesets sim_1]

# The testbenches read the expected .mem files from the simulation run folder.
# Vivado copies sim-fileset data files there; copy them as well to be safe.
set xsim_dir [file join $proj_dir $proj_name.sim sim_1 behav xsim]
file mkdir $xsim_dir
foreach f [glob [file join $origin sim expected *.mem]] {
    file copy -force $f $xsim_dir
}

# ---------------- VIO IP ----------------
# Input probes (FPGA -> VIO, observed). Order = probe_in0 .. probe_in27.
set vio_in_widths  {1 1 1 1 4 8 4 8 1 12 12 20 8 12 16 20 20 20 1 8 8 8 8 16 16 16 32 1}
# Output probes (VIO -> FPGA, drive the logic) and their initial values.
#                   rst start part test tile_sel t_flag
set vio_out_widths {1   1     2    3    12       8}
set vio_out_init   {0x0 0x0   0x0  0x0  0x668    0x28}

create_ip -name vio -vendor xilinx.com -library ip -module_name vio_0
set cfg [list \
    CONFIG.C_NUM_PROBE_IN          [llength $vio_in_widths] \
    CONFIG.C_NUM_PROBE_OUT         [llength $vio_out_widths] \
    CONFIG.C_EN_PROBE_IN_ACTIVITY  {1}]
for {set i 0} {$i < [llength $vio_in_widths]} {incr i} {
    lappend cfg CONFIG.C_PROBE_IN${i}_WIDTH [lindex $vio_in_widths $i]
}
for {set i 0} {$i < [llength $vio_out_widths]} {incr i} {
    lappend cfg CONFIG.C_PROBE_OUT${i}_WIDTH    [lindex $vio_out_widths $i]
    lappend cfg CONFIG.C_PROBE_OUT${i}_INIT_VAL [lindex $vio_out_init $i]
}
set_property -dict $cfg [get_ips vio_0]

set vio_xci [get_files vio_0.xci]
generate_target all $vio_xci
export_ip_user_files -of_objects $vio_xci -no_script -sync -force -quiet
create_ip_run $vio_xci

# ---------------- run settings ----------------
set_property strategy {Vivado Synthesis Defaults}      [get_runs synth_1]
set_property strategy {Vivado Implementation Defaults} [get_runs impl_1]
set_property STEPS.PHYS_OPT_DESIGN.IS_ENABLED true     [get_runs impl_1]
# .ltx is written by write_bitstream when debug cores exist; build.tcl also writes it explicitly

update_compile_order -fileset sources_1
update_compile_order -fileset sim_1

puts "Project ready: [file join $proj_dir $proj_name.xpr]"
puts "Next: source scripts/build.tcl   (bitstream)  or  source scripts/run_sim.tcl   (simulation)"
