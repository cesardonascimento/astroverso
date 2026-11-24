import sys

from manager.cli import ensure_command, main

if len(sys.argv) == 1:
    ensure_command()
sys.exit(main())
