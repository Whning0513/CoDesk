"""Restore SIGINT before starting the run-owned background driver.

A non-interactive shell can mark asynchronous children as ignoring SIGINT.
Python preserves that disposition, so restore its normal KeyboardInterrupt
handler before importing and running the driver. Do not signal other processes.
"""
import runpy
import signal


def main() -> None:
    signal.signal(signal.SIGINT, signal.default_int_handler)
    runpy.run_module('oscombo.collab.workspace_assembly_lite_v2p2.live_pilot', run_name='__main__')


if __name__ == '__main__':
    main()
