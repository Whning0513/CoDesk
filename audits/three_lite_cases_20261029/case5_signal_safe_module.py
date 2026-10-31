"""Translate coordinator SIGTERM into a catchable error for runner cleanup."""

import runpy
import signal
import sys


def _terminate(signum, frame):
    raise InterruptedError(f'coordinator received signal {signum}')


def main():
    if len(sys.argv) < 2:
        raise SystemExit('usage: case5_signal_safe_module.py MODULE [ARGS...]')
    module = sys.argv[1]
    sys.argv = [module, *sys.argv[2:]]
    signal.signal(signal.SIGTERM, _terminate)
    runpy.run_module(module, run_name='__main__', alter_sys=True)


if __name__ == '__main__':
    main()
