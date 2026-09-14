"""Permite `python -m src.analytics <comando>` (ver src/analytics/__init__.py para el CLI).

BD_BI_TFM: analytics.py se convirtió en un paquete (src/analytics/__init__.py)
para poder convivir con los submódulos causal_analysis.py y
time_series_analysis.py bajo el mismo nombre `src.analytics` — ver
INTEGRATION_NOTES.md. `python -m paquete` ejecuta paquete/__main__.py, no
__init__.py, así que este archivo es necesario para que el comando
documentado siga funcionando igual que antes.
"""

import sys

from src.analytics import main

if __name__ == "__main__":
    sys.exit(main())
