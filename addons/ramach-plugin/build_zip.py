"""Build installable Blender add-on ZIP with a top-level ramach_plugin package."""

from pathlib import Path
import zipfile


HERE = Path(__file__).resolve().parent
DIST = HERE / "dist"
DIST.mkdir(exist_ok=True)
TARGET = DIST / "ramach-plugin-v0.1.0.zip"
with zipfile.ZipFile(TARGET, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for file in (HERE / "ramach_plugin").rglob("*.py"):
        archive.write(file, file.relative_to(HERE))
print(TARGET)
