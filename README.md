# BurnWatch

An FPGA-accelerated open-burning smoke detector. A PYNQ-Z2 scores every frame of a CCTV feed, and AWS checks each suspect frame and sends an alert.

> Work in progress. Every section below is filled in during the build.

## Problem
_To be written from the sourced figures in `docs/sources.md`._

## What BurnWatch does
_To be written: detect, verify, alert, keep video private._

## Architecture
_Architecture figure (`docs/architecture.svg`) goes here._

## PL/PS split
_What runs in the FPGA fabric and what runs on the ARM, with resource use from the synthesis report._

## AWS
_Each service, what it does here, and an example event and verdict._

## Results
_Measured throughput and the clip test table, from `docs/results.md`._

## Limitations
_What we observed and what we do not claim._

## How to run
_Laptop, AWS, PYNQ and HLS/Vivado steps, with exact commands._

## Credits and licences
This project is MIT-licensed (see [LICENSE](LICENSE)). It builds on:

- [Xilinx PYNQ](https://github.com/Xilinx/PYNQ) (BSD-3-Clause)
- [paho-mqtt](https://github.com/eclipse-paho/paho.mqtt.python) (EPL-2.0 / EDL-1.0)
- [boto3](https://github.com/boto/boto3) (Apache-2.0)
- [anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) (MIT)
- [NumPy](https://numpy.org/) (BSD-3-Clause)
- [OpenCV](https://opencv.org/) (Apache-2.0)
- [AWS SAM CLI](https://github.com/aws/aws-sam-cli) (Apache-2.0)

## Built 8–11 October 2026 for Environmental Hacks 2026
