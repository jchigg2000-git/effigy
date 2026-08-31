import importlib
import pkgutil
from pathlib import Path

_pkg_dir = Path(__file__).parent

# Import every .py module in this directory so @register decorators fire.
for mod_info in pkgutil.iter_modules([str(_pkg_dir)]):
    importlib.import_module(f"{__name__}.{mod_info.name}")
