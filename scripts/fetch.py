#!/usr/bin/env python3
"""Fetch planned disruptions from PRIM API and generate ICS files per metro line.

Thin entry shim — all logic lives in the fetch_lib package. When invoked as
`python scripts/fetch.py`, Python auto-adds the script's directory to sys.path,
so `fetch_lib` resolves to scripts/fetch_lib/.
"""

from fetch_lib.main import main

if __name__ == "__main__":
    main()
