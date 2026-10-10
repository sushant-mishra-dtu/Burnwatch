# Standalone module-analysis flow supported by Vivado UG905.
# No package pin mapping, bitstream, or full-system implementation is performed.
if {$argc != 1} { error "Usage: vivado -mode batch -source implement_core_ooc.tcl -tclargs <project.xpr>" }
set project_file [file normalize [lindex $argv 0]]
if {![file exists $project_file]} { error "Project file does not exist" }
set root [file dirname $project_file]
set results [file join $root core_ooc_results]
set rtl [file join $root [file rootname [file tail $project_file]].srcs sources_1 new tile_engine.sv]
if {![file exists $rtl]} { error "Scoring RTL does not exist: $rtl" }
file mkdir $results
create_project -in_memory -part xc7z020clg400-1
read_verilog -sv [list $rtl]
synth_design -top tile_engine -part xc7z020clg400-1 -mode out_of_context
create_clock -name ap_clk -period 10.000 [get_ports ap_clk]
# This constraint models an external parent clock buffer, not a package pin.
set_property HD.CLK_SRC BUFGCTRL_X0Y0 [get_ports ap_clk]
set_property HD.PARTITION 1 [current_design]
write_checkpoint -force [file join $results tile_engine_core_synth.dcp]
opt_design
place_design
phys_opt_design
route_design
report_utilization -file [file join $results utilization.rpt]
report_timing_summary -report_unconstrained -file [file join $results timing_summary.rpt]
report_route_status -file [file join $results route_status.rpt]
report_drc -file [file join $results drc.rpt]
write_checkpoint -force [file join $results tile_engine_core_routed.dcp]
set fp [open [file join $results result.txt] w]
puts $fp "BURNWATCH CORE OOC ROUTING COMPLETE"
puts $fp "Target device: xc7z020clg400-1; clock constraint: 10 ns"
puts $fp "Parent clock source assumption: BUFGCTRL_X0Y0"
puts $fp "Scoring RTL unchanged; module boundary routes and board pinout are not validated"
puts $fp "Timing closure must be assessed in timing_summary.rpt; no bitstream or board test"
close $fp
puts "BURNWATCH CORE OOC ROUTING COMPLETE: $results"
close_project
