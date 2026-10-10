# -----------------------------------------------------------------------------
# build.tcl  -  synthesis, implementation, bitstream, reports
#
# Run from the package root after create_project.tcl:
#   vivado -mode batch -source scripts/build.tcl
# or in the Vivado Tcl console (project open or not):
#   source scripts/build.tcl
#
# Results in output/:
#   bw_top_zed.bit   bitstream             (program this)
#   bw_top_zed.ltx   debug probes file     (load this with it: VIO probe names)
#   timing_summary.rpt, utilization.rpt, build_summary.txt
# -----------------------------------------------------------------------------

set origin    [file normalize [file join [file dirname [info script]] ..]]
set proj_name burnwatch_zed_vio
set proj_file [file join $origin vivado $proj_name.xpr]
set out_dir   [file join $origin output]
set jobs      4

if {[catch {current_project}]} {
    if {![file exists $proj_file]} {
        error "No project: run scripts/create_project.tcl first ($proj_file)"
    }
    open_project $proj_file
}

file mkdir $out_dir
# Remove old outputs so a stale .bit/.ltx pair can never be picked up
foreach f {bw_top_zed.bit bw_top_zed.ltx timing_summary.rpt utilization.rpt build_summary.txt} {
    file delete -force [file join $out_dir $f]
}

# ---------------- synthesis (the VIO OOC run is launched with it) ----------------
reset_run synth_1
launch_runs synth_1 -jobs $jobs
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {
    error "Synthesis failed: see [file join $origin vivado $proj_name.runs synth_1 runme.log]"
}

# ---------------- implementation + bitstream ----------------
launch_runs impl_1 -to_step write_bitstream -jobs $jobs
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {
    error "Implementation failed: see [file join $origin vivado $proj_name.runs impl_1 runme.log]"
}

# ---------------- reports and outputs ----------------
open_run impl_1
report_timing_summary -delay_type min_max -max_paths 10 -file [file join $out_dir timing_summary.rpt]
report_utilization -file [file join $out_dir utilization.rpt]
write_debug_probes -force [file join $out_dir bw_top_zed.ltx]

set impl_dir [get_property DIRECTORY [get_runs impl_1]]
file copy -force [file join $impl_dir bw_top_zed.bit] [file join $out_dir bw_top_zed.bit]

set wns  [get_property SLACK [get_timing_paths -setup -max_paths 1 -nworst 1]]
set whs  [get_property SLACK [get_timing_paths -hold -max_paths 1 -nworst 1]]
set ok   [expr {$wns >= 0 && $whs >= 0}]
set fh [open [file join $out_dir build_summary.txt] w]
puts $fh "BurnWatch ZedBoard VIO build"
puts $fh "Vivado:      [version -short]"
puts $fh "Part:        [get_property PART [current_project]]"
puts $fh "Setup WNS:   $wns ns"
puts $fh "Hold WHS:    $whs ns"
puts $fh "Timing met:  [expr {$ok ? {YES} : {NO - do not trust the hardware results}}]"
puts $fh "Bitstream:   [file join $out_dir bw_top_zed.bit]"
puts $fh "Probes:      [file join $out_dir bw_top_zed.ltx]"
close $fh

puts "------------------------------------------------------------"
puts "Setup WNS = $wns ns, hold WHS = $whs ns  ->  timing [expr {$ok ? {MET} : {NOT MET}}]"
puts "Bitstream: [file join $out_dir bw_top_zed.bit]"
puts "Probes:    [file join $out_dir bw_top_zed.ltx]"
puts "------------------------------------------------------------"
