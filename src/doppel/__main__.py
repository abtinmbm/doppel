"""Runs the package with `python -m doppel` by calling doppel.main().

This is how Doppel is started: the `doppel` .exe launcher that uv creates is
unsigned, and Windows Smart App Control blocks unsigned .exe files.
"""

from doppel import main

main()
