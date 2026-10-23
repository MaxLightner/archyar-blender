"""Build the one-time Blender installation archive (standard library only)."""

from pathlib import Path
import os
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "archyar_blender"
OUTPUT = ROOT / "dist" / "archyar-blender-v0.3.0.zip"


def build():
    OUTPUT.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUTPUT, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(PACKAGE.rglob('*')):
            if path.is_file() and path.suffix in {'.py', '.json'}:
                archive.write(path, path.relative_to(ROOT).as_posix())
        revision = os.environ.get('GITHUB_SHA', '').strip()
        if len(revision) == 40 and all(c in '0123456789abcdef' for c in revision):
            archive.writestr('archyar_blender/_installed_sha', revision + '\n')
    print(OUTPUT)


if __name__ == '__main__':
    build()
