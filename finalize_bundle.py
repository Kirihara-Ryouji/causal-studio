"""Make dependency metadata and Windows ICU resolution reproducible."""
from importlib import metadata
from pathlib import Path
import shutil

root = Path(__file__).resolve().parent
internal = (root/'dist'/'CausalStudio'/'_internal').resolve()
if not internal.is_dir() or root not in internal.parents:
    raise SystemExit('Expected a built application inside this project.')

# Qt for Windows uses the operating system ICU API. A Conda installation on
# the build machine's PATH can make PyInstaller collect an unrelated ICU DLL
# whose version-suffixed exports are incompatible. Leave resolution to Windows.
for name in ('icuuc.dll', 'icudt78.dll'):
    target = internal/name
    if target.is_file():
        target.unlink()

for name in ('numpy', 'pandas', 'scipy', 'causal-learn', 'tigramite', 'lingam',
             'PySide6-Essentials', 'shiboken6', 'openpyxl', 'numba', 'dcor', 'scikit-learn', 'array-api-compat'):
    distribution = metadata.distribution(name)
    entry = next(f for f in distribution.files if f.name == 'METADATA' and f.parent.name.endswith('.dist-info'))
    source = Path(distribution.locate_file(entry)).parent
    shutil.copytree(source, internal/source.name, dirs_exist_ok=True)
# array-api-compat registers NumPy FFT/linalg namespaces dynamically. Preserve
# the pure-Python package beside the archive so frozen imports can resolve them.
distribution = metadata.distribution('array-api-compat')
source = Path(distribution.locate_file('array_api_compat'))
shutil.copytree(source, internal/'array_api_compat', dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
print('Dependency metadata collected; Windows ICU conflict removed.')
