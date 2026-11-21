"""Entry point used when building D2RPriceCheck.exe with PyInstaller."""
import sys
from d2pc.main import main

if __name__ == "__main__":
    sys.exit(main())
