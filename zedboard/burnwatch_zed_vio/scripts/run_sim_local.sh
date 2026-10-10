#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# run_sim_local.sh  -  the same testbenches with free simulators (no Vivado)
#   bash scripts/run_sim_local.sh            # iverilog: unit test + QUICK system test
#   bash scripts/run_sim_local.sh full       # + verilator: full 1280x720 system test (~20 s)
#   bash scripts/run_sim_local.sh regen      # regenerate sim/expected from golden.py first
# Needs: iverilog (>= 11), optionally verilator (>= 5, for "full"), python3 + numpy for "regen".
# -----------------------------------------------------------------------------
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/sim/build"
mkdir -p "$BUILD"
RTL=$(ls "$ROOT"/rtl/bw_*.v | grep -v bw_top_zed.v)   # bw_top_zed needs the Vivado VIO IP

if [[ " $* " == *" regen "* ]]; then
    python3 "$ROOT/model/bw_model.py"
fi

cd "$ROOT/sim/expected"          # the testbenches read the .mem files from here

echo "== unit test: bw_tile_score (iverilog)"
iverilog -g2001 -s tb_bw_tile_score -o "$BUILD/unit.vvp" "$ROOT/sim/tb_bw_tile_score.v" "$ROOT/rtl/bw_tile_score.v"
vvp -n "$BUILD/unit.vvp" | grep -E "TB_|MISMATCH"

echo "== system test, QUICK 320x192 (iverilog, ~1.5 min)"
iverilog -g2001 -DQUICK -s tb_bw_system -o "$BUILD/quick.vvp" "$ROOT/sim/tb_bw_system.v" $RTL
vvp -n "$BUILD/quick.vvp" | grep -vE "finish"

if [[ " $* " == *" full "* ]]; then
    echo "== system test, full 1280x720 (verilator)"
    verilator --binary --timing -O3 -Wno-fatal -Wno-lint -Wno-style --top-module tb_bw_system \
        -Mdir "$BUILD/vfull" -o vfull "$ROOT/sim/tb_bw_system.v" $RTL > "$BUILD/verilator_build.log" 2>&1
    "$BUILD/vfull/vfull" | grep -vE "finish"
fi
