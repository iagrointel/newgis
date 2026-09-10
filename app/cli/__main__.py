"""`python -m app.cli` — o mesmo ponto de entrada de `scripts/plat` e de `venv/bin/plat`."""

import sys

from app.cli.principal import main

if __name__ == "__main__":
    sys.exit(main())
