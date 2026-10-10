# Native RTL synthesis/report flow. Invoke with -tclargs <existing .xpr>.
# The two source modules and their scoring algorithm are not modified here.
if {$argc != 1} { error "Usage: vivado -mode batch -source synthesize_project.tcl -tclargs <project.xpr>" }
set project_file [file normalize [lindex $argv 0]]
if {![file exists $project_file]} { error "Project does not exist: $project_file" }
set project_root [file dirname $project_file]
set report_dir [file join $project_root synthesis_results]
file mkdir $report_dir
open_project $project_file
set synth_run [get_runs synth_1]
# Vivado 2022.1's generated read_checkpoint command can fail on this project's
# space-containing incremental DCP path. Disable both automatic and manual reuse.
set_property AUTO_INCREMENTAL_CHECKPOINT 0 $synth_run
set_property INCREMENTAL_CHECKPOINT {} $synth_run
set_property top tile_engine [get_filesets sources_1]
set_property top_auto_set false [get_filesets sources_1]
set_property used_in {simulation} [get_files *tb_tile_engine.sv]
set clock_xdc [file join $project_root [file rootname [file tail $project_file]].srcs constrs_1 new tile_engine_clock.xdc]
file mkdir [file dirname $clock_xdc]
set clock_file [open $clock_xdc w]
puts $clock_file {create_clock -name ap_clk -period 10.000 [get_ports ap_clk]}
close $clock_file
if {[llength [get_files -quiet [list $clock_xdc]]] == 0} {
    add_files -fileset constrs_1 -norecurse [list $clock_xdc]
}
update_compile_order -fileset sources_1
reset_run synth_1
launch_runs synth_1 -jobs 6
wait_on_run synth_1
set run_status [get_property STATUS $synth_run]
puts "BURNWATCH SYNTHESIS STATUS: $run_status"
if {![string match {*Complete*} $run_status]} {
    close_project
    error "Synthesis did not complete; inspect synth_1/tile_engine.vds"
}
open_run synth_1
report_utilization -file [file join $report_dir utilization.rpt]
report_timing_summary -report_unconstrained -file [file join $report_dir timing_summary.rpt]
write_checkpoint -force [file join $report_dir tile_engine_synth.dcp]
close_project
puts "BURNWATCH SYNTHESIS COMPLETE: reports in $report_dir"
