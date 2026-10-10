## -----------------------------------------------------------------------------
## BurnWatch tile engine + VIO demo, ZedBoard (xc7z020clg484-1)
##
## Pins checked against two sources (10 Oct 2026):
##   * Digilent Zedboard-Master.xdc (github.com/Digilent/digilent-xdc):
##       "Clock Source - Bank 13: PACKAGE_PIN Y9 GCLK", "User LEDs - Bank 33:
##       T22 T21 U22 U21 V22 W22 U19 U14", "bank voltage for IO Bank 13 / 33 is
##       fixed to 3.3V on ZedBoard" (IOSTANDARD LVCMOS33)
##   * Xilinx BoardStore 2022.1, boards/Avnet/zedboard/1.4:
##       part0_pins.xml: sys_clk loc="Y9" iostandard="LVCMOS33";
##       leds_8bits_tri_o_0..7 = T22 T21 U22 U21 V22 W22 U19 U14, LVCMOS33
##       board.xml: sys_clock "System Clock, 100 MHz"
## -----------------------------------------------------------------------------

## 100 MHz system clock (GCLK)
set_property PACKAGE_PIN Y9 [get_ports GCLK]
set_property IOSTANDARD LVCMOS33 [get_ports GCLK]
create_clock -period 10.000 -name gclk [get_ports GCLK]

## User LEDs LD0..LD7 (status mirror; optional, all data is on the VIO)
set_property PACKAGE_PIN T22 [get_ports {LD[0]}]
set_property PACKAGE_PIN T21 [get_ports {LD[1]}]
set_property PACKAGE_PIN U22 [get_ports {LD[2]}]
set_property PACKAGE_PIN U21 [get_ports {LD[3]}]
set_property PACKAGE_PIN V22 [get_ports {LD[4]}]
set_property PACKAGE_PIN W22 [get_ports {LD[5]}]
set_property PACKAGE_PIN U19 [get_ports {LD[6]}]
set_property PACKAGE_PIN U14 [get_ports {LD[7]}]
set_property IOSTANDARD LVCMOS33 [get_ports {LD[*]}]

## LEDs are slow status outputs with no timing relationship to anything
set_false_path -to [get_ports {LD[*]}]
