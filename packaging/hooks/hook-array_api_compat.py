"""Collect dynamic NumPy FFT/linalg imports used by dcor."""
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("array_api_compat.numpy")
module_collection_mode = {"array_api_compat": "pyz+py"}
