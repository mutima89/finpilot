"""PyInstaller entry point for the FinPilot desktop app."""
import sys

from finpilot.app import main

if __name__ == "__main__":
    sys.exit(main())
