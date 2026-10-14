"""Keep actual source paths available to Numba's function cache locators."""
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("dcor")
module_collection_mode = {"dcor": "py"}
