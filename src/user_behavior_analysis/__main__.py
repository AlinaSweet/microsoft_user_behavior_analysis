"""Run the package command interface through Python's module entry point."""

import logging

from user_behavior_analysis.api.cli import main

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    raise SystemExit(main())
