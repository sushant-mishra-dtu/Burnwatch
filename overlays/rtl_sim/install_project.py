"""Install the standalone RTL simulation into a user-selected Vivado project.

Run with the repo's laptop Python environment. No detector/contracts edits.
The external project and sources are backed up before their first replacement.
"""
import argparse
from datetime import datetime
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--vectors", type=Path, required=True)
    args = parser.parse_args()
    project = args.project.resolve(strict=True)
    root = project.parent
    sources = root / (project.stem + ".srcs")
    design = sources / "sources_1" / "new" / "tile_engine.sv"
    bench = sources / "sim_1" / "new" / "tb_tile_engine.sv"
    if not design.is_file() or not bench.is_file():
        raise SystemExit("Expected the two source files in the selected project")
    vector_source = args.vectors.resolve(strict=True)
    for name in ("synthetic", "synthetic-u3"):
        if not (vector_source / name / "params.txt").is_file():
            raise SystemExit(f"Missing vectors: {name}")
    backup = root / ("codex_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    backup.mkdir()
    for original in (project, design, bench):
        destination = backup / original.relative_to(root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination)
    source_dir = Path(__file__).resolve().parent
    shutil.copy2(source_dir / "tile_engine.sv", design)
    shutil.copy2(source_dir / "tb_tile_engine.sv", bench)
    data = root / "simulation_data"
    for name in ("synthetic", "synthetic-u3"):
        shutil.copytree(vector_source / name, data / name, dirs_exist_ok=True)
    results = root / "simulation_results"
    results.mkdir(exist_ok=True)
    include = bench.parent / "bw_sim_paths.svh"
    include.write_text(
        f'`define BW_VECTOR_ROOT "{data.as_posix()}"\n'
        f'`define BW_REPORT_PATH "{(results / "rtl_result.txt").as_posix()}"\n',
        encoding="ascii",
    )
    configure = root / "configure_and_simulate.tcl"
    configure.write_text(
        f'open_project {{{project.as_posix()}}}\n'
        'set_property top tile_engine [get_filesets sources_1]\n'
        'set_property top_auto_set false [get_filesets sources_1]\n'
        'set_property top tb_tile_engine [get_filesets sim_1]\n'
        'set_property top_auto_set false [get_filesets sim_1]\n'
        'set_property used_in {simulation} [get_files *tb_tile_engine.sv]\n'
        f'set_property include_dirs {{{bench.parent.as_posix()}}} [get_filesets sim_1]\n'
        'set_property xsim.simulate.runtime all [get_filesets sim_1]\n'
        'set_property xsim.simulate.log_all_signals false [get_filesets sim_1]\n'
        'update_compile_order -fileset sources_1\n'
        'update_compile_order -fileset sim_1\n'
        'launch_simulation -simset sim_1 -mode behavioral\n'
        'close_sim\n'
        'close_project\n',
        encoding="ascii",
    )
    (root / "run_local_sim.ps1").write_text(
        "$ErrorActionPreference = 'Stop'\n"
        'Set-Location -LiteralPath $PSScriptRoot\n'
        '& "M:\\amd_xilinx\\Vivado\\2022.1\\bin\\vivado.bat" -mode batch '
        '-source "$PSScriptRoot\\configure_and_simulate.tcl" '
        '-log "$PSScriptRoot\\simulation_results\\vivado.log" '
        '-journal "$PSScriptRoot\\simulation_results\\vivado.jou"\n'
        'if ($LASTEXITCODE -ne 0) { throw "Vivado failed; inspect simulation_results/vivado.log" }\n'
        '$resultPath = Join-Path $PSScriptRoot "simulation_results\\rtl_result.txt"\n'
        'if (!(Test-Path -LiteralPath $resultPath) -or '
        '!((Get-Content -LiteralPath $resultPath) -match "BURNWATCH RTL PASS")) '
        '{ throw "Simulation did not complete successfully" }\n'
        'Get-Content -LiteralPath $resultPath\n',
        encoding="ascii",
    )
    shutil.copy2(source_dir / "README.md", root / "README_LOCAL_SIM.md")
    print(f"Installed design: {design}")
    print(f"Installed testbench: {bench}")
    print(f"Originals backed up: {backup}")


if __name__ == "__main__":
    main()
