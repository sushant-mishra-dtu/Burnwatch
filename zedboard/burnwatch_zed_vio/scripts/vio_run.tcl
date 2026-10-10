# -----------------------------------------------------------------------------
# vio_run.tcl  -  OPTIONAL helper for the Vivado Hardware Manager Tcl console
#
# Does from the Tcl console what the VIO GUI does by hand, and compares the
# input probes with the expected values (scripts/bw_expected.tcl, generated
# from golden.py). Use it to save time in a 15-minute slot; the GUI steps in
# README.md give the same results. Run AFTER the device is programmed with
# output/bw_top_zed.bit and output/bw_top_zed.ltx.
#
#   source <package>/scripts/vio_run.tcl
#   bw_setup              ;# radix of every probe (unsigned) - once
#   bw_reset              ;# pulse the VIO reset
#   bw_run 2 0            ;# part_sel test_sel [t_flag=40]: run, print, compare
#   bw_all                ;# the 14 demo tests, one PASS/FAIL line each
#   bw_tile 1640          ;# read back one tile (features, score, baselines)
#   bw_show               ;# print every input probe
# -----------------------------------------------------------------------------

source [file join [file dirname [file normalize [info script]]] bw_expected.tcl]

# The VIO core on the programmed device
proc bw_vio {} {
    set v [lindex [get_hw_vios -of_objects [current_hw_device]] 0]
    if {$v eq ""} { error "No VIO found: program the device with the .bit AND the .ltx file" }
    return $v
}

# One probe by net name (exact name first, then any name ending in it)
proc bw_probe {name} {
    set v [bw_vio]
    set p [get_hw_probes -quiet $name -of_objects $v]
    if {[llength $p] != 1} {
        set p [get_hw_probes -quiet -of_objects $v -filter "NAME =~ \"*$name\""]
    }
    if {[llength $p] != 1} {
        error "VIO probe '$name' not found ([llength $p] matches). Probes: [get_hw_probes -of_objects $v]"
    }
    return $p
}

proc bw_setup {} {
    foreach p [get_hw_probes -of_objects [bw_vio]] {
        catch {set_property INPUT_VALUE_RADIX  UNSIGNED $p}
        catch {set_property OUTPUT_VALUE_RADIX UNSIGNED $p}
    }
    puts "All VIO probes set to unsigned decimal."
}

proc bw_set {name value} {
    set p [bw_probe $name]
    set_property OUTPUT_VALUE_RADIX UNSIGNED $p
    set_property OUTPUT_VALUE $value $p
    commit_hw_vio $p
}

proc bw_refresh {} {
    refresh_hw_vio [bw_vio]
}

proc bw_get {name} {
    set p [bw_probe $name]
    set_property INPUT_VALUE_RADIX UNSIGNED $p
    return [expr {[get_property INPUT_VALUE $p] + 0}]
}

proc bw_reset {} {
    bw_set vio_start 0
    bw_set vio_rst 1
    after 50
    bw_set vio_rst 0
    after 50
    bw_refresh
    puts "Reset: busy=[bw_get busy] done=[bw_get done] error=[bw_get error] run_id=[bw_get run_id]"
}

set bw_result_names {busy done result_valid error err_code run_id frames_run gate_hist gate changed
    flagged score_sum max_score max_idx frame_count sum_e sum_y sum_s cycles
    rd_err rd_me rd_my rd_ms rd_score rd_be rd_by rd_bs heartbeat}

proc bw_show {} {
    bw_refresh
    foreach n $::bw_result_names {
        puts [format "  %-13s %s" $n [bw_get $n]]
    }
}

proc bw_tile {idx} {
    bw_set vio_tile_sel $idx
    after 50
    bw_refresh
    puts [format "tile %d (row %d col %d): mE=%d mY=%d mS=%d score=%d bE=%d bY=%d bS=%d rd_err=%d" \
        $idx [expr {$idx / 80}] [expr {$idx % 80}] [bw_get rd_me] [bw_get rd_my] [bw_get rd_ms] \
        [bw_get rd_score] [bw_get rd_be] [bw_get rd_by] [bw_get rd_bs] [bw_get rd_err]]
}

# Run one test: Start 0 -> 1, wait for done (max 5 s), Start back to 0
proc bw_run {part test {t_flag 40} {quiet 0}} {
    bw_set vio_start 0
    bw_set vio_part_sel $part
    bw_set vio_test_sel $test
    bw_set vio_t_flag $t_flag
    bw_set vio_tile_sel $::bw_expected_tile
    bw_refresh
    set rid0 [bw_get run_id]
    bw_set vio_start 1
    set ok 0
    for {set i 0} {$i < 50} {incr i} {
        after 100
        bw_refresh
        if {[bw_get done] == 1 && [bw_get run_id] != $rid0} { set ok 1; break }
    }
    bw_set vio_start 0
    after 50
    bw_refresh
    if {!$ok} {
        puts "part=$part test=$test: no done within 5 s (busy=[bw_get busy])"
        return 0
    }
    set key "$part,$test,$t_flag"
    set bad {}
    if {[dict exists $::bw_expected $key]} {
        set exp [dict get $::bw_expected $key]
        dict for {n v} $exp {
            if {$n eq "label"} continue
            set got [bw_get $n]
            if {$got != $v} { lappend bad "$n=$got (expected $v)" }
        }
        if {[bw_get error] != 0} { lappend bad "error=1 err_code=[bw_get err_code]" }
        set label [dict get $exp label]
        set verdict [expr {[llength $bad] == 0 ? "PASS" : "FAIL"}]
    } else {
        set label "(no expected values for $key)"
        set verdict "----"
    }
    puts [format "%-4s part=%d test=%d T_FLAG=%-3d %-40s run_id=%d frames=%d gate_hist=%d changed=%d flagged=%d score_sum=%d max=%d@%d cycles=%d err=%d/%d" \
        $verdict $part $test $t_flag $label [bw_get run_id] [bw_get frames_run] [bw_get gate_hist] \
        [bw_get changed] [bw_get flagged] [bw_get score_sum] [bw_get max_score] [bw_get max_idx] \
        [bw_get cycles] [bw_get error] [bw_get err_code]]
    foreach b $bad { puts "       mismatch: $b" }
    return [expr {[llength $bad] == 0}]
}

# All demo tests in the order of docs/EXPECTED_RESULTS.md
proc bw_all {} {
    set pass 0
    set n 0
    foreach key [dict keys $::bw_expected] {
        lassign [split $key ,] part test t_flag
        incr n
        incr pass [bw_run $part $test $t_flag]
    }
    puts "bw_all: $pass of $n tests PASS"
}

puts "vio_run.tcl loaded: bw_setup, bw_reset, bw_run <part> <test> \[t_flag\], bw_all, bw_tile <idx>, bw_show"
