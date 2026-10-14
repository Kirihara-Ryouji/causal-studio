"""Bundle the verified Windows folder, examples and user guide."""
from pathlib import Path
import shutil
import zipfile

root = Path(__file__).resolve().parent
app = root / 'dist' / 'CausalStudio'
if not (app/'CausalStudio.exe').is_file():
    raise SystemExit('Build the executable before packaging.')
shutil.copy2(root/'README.md', app/'README.md')
shutil.copytree(root/'examples', app/'examples', dirs_exist_ok=True)
with zipfile.ZipFile(root/'dist'/'CausalStudio-Windows-x64.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for path in sorted(app.rglob('*')):
        if path.is_file():
            archive.write(path, path.relative_to(app.parent))
print('Release archive ready.')
