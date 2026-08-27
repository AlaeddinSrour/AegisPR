"""Trusted container entrypoint kept outside the audited workspace mount."""

import logging
import sys

from src.main import main

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logging.getLogger("aegispr").error("%s", " ".join(str(exc).split()))
        sys.exit(1)
