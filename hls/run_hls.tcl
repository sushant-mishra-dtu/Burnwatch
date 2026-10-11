# Vitis HLS 2022.1 flow for the BurnWatch tile engine: C simulation, synthesis, IP export.
#
#   vitis_hls -f hls/run_hls.tcl                      (vitis_hls.bat on Windows; see hls/README.md)
#
# Environment (all optional):
#   BW_HLS_STEPS    steps to run, default "csim csynth export"
#   BW_HLS_WORK     project directory, default hls/build (git-ignored). Vitis HLS refuses paths with a space,
#                   so when the repo path has one the default is burnwatch_hls at the root of the repo's drive.
#   BW_GOLDEN_SETS  vector sets under testdata/golden for csim, default "synthetic synthetic-u3 synthetic-regs"
# Sources are copied into the work directory (same reason). The csim log and synthesis report are copied to
# hls/reports/ (csim_last.txt, csynth.rpt).
set here [file normalize [file dirname [info script]]]
set root [file dirname $here]
if {[info exists ::env(BW_HLS_WORK)]} {
    set work $::env(BW_HLS_WORK)
} elseif {[string first " " $here] < 0} {
    set work $here/build
} else {
    set work [lindex [file split $here] 0]burnwatch_hls
}
set steps [expr {[info exists ::env(BW_HLS_STEPS)] ? $::env(BW_HLS_STEPS) : "csim csynth export"}]

file mkdir $work/src
foreach f {tile_engine.cpp tile_engine.h config.h tb_tile_engine.cpp} {
    file copy -force $here/$f $work/src/$f
}
cd $work
# A csim-only run gets its own project, so it never wipes the synthesized/exported IP in tile_engine_prj.
set prj [expr {[lsearch $steps csynth] >= 0 || [lsearch $steps export] >= 0 ? "tile_engine_prj" : "tile_engine_csim"}]
open_project -reset $prj
set_top tile_engine
add_files src/tile_engine.cpp
add_files -tb src/tb_tile_engine.cpp
open_solution -reset sol1 -flow_target vivado
set_part xc7z020clg400-1
create_clock -period 10 -name default
# Zynq-7000 addresses are 32-bit: one AXI-Lite register per pointer (contracts.md section 7).
config_interface -m_axi_addr64=false

set ::env(BW_GOLDEN_DIR) $root/testdata/golden
if {![info exists ::env(BW_GOLDEN_SETS)]} {
    set ::env(BW_GOLDEN_SETS) "synthetic synthetic-u3 synthetic-regs"
}

file mkdir $here/reports
if {[lsearch $steps csim] >= 0} {
    csim_design -O
    file copy -force $work/$prj/sol1/csim/report/tile_engine_csim.log $here/reports/csim_last.txt
}
if {[lsearch $steps csynth] >= 0} {
    csynth_design
    file copy -force $work/$prj/sol1/syn/report/csynth.rpt $here/reports/csynth.rpt
}
if {[lsearch $steps export] >= 0} { export_design -format ip_catalog -rtl verilog }
exit
