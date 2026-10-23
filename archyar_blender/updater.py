"""Explicit, one-click source updater for Archyar's public GitHub repository.

Only the archyar_blender package is touched. Updates run on user request, create
a local backup, and take effect after Blender restart. Import/export is separate.
"""

import io
import json
from pathlib import Path
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile

import bpy


REPO = "MaxLightner/archyar-blender"
SOURCE = "https://api.github.com/repos/" + REPO
ALLOWED_SUFFIXES = {'.py', '.json'}
MAX_DOWNLOAD = 20 * 1024 * 1024


def _download(url, limit=MAX_DOWNLOAD):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Archyar-Blender-Updater",
               "X-GitHub-Api-Version": "2022-11-28"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Update archive exceeds the 20 MB size limit")
        return data


def update_addon(context):
    try:
        payload = json.loads(_download(SOURCE + "/commits/main", 1024*1024))
    except urllib.error.HTTPError as error:
        if error.code in (401, 403, 404):
            raise ValueError("Cannot access public GitHub source (HTTP %d); check network or rate limit" % error.code) from None
        raise ValueError("GitHub update check failed (HTTP %d)" % error.code) from None
    sha = str(payload.get("sha", ""))
    if len(sha) != 40 or any(c not in '0123456789abcdef' for c in sha):
        raise ValueError("GitHub returned an invalid revision")
    package = Path(__file__).resolve().parent
    marker = package / "_installed_sha"
    if marker.exists() and marker.read_text(encoding="ascii").strip() == sha:
        return "Already up to date"

    archive = _download(SOURCE + "/zipball/" + sha)
    files = {}
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        for entry in zipped.infolist():
            parts = Path(entry.filename).parts
            if entry.is_dir() or len(parts) < 3 or parts[1] != "archyar_blender":
                continue
            rel = Path(*parts[2:])
            if rel.is_absolute() or '..' in rel.parts or rel.suffix not in ALLOWED_SUFFIXES:
                continue
            if entry.file_size > 2 * 1024 * 1024 or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Update contains an invalid package entry")
            files[rel] = zipped.read(entry)
    if Path("__init__.py") not in files or len(files) > 100:
        raise ValueError("Update archive does not contain a valid Archyar package")

    # Stage everything before changing the installed add-on; never touch other add-ons.
    with tempfile.TemporaryDirectory(prefix="archyar-update-", dir=str(package.parent)) as tmp:
        stage = Path(tmp) / "stage"
        for rel, data in files.items():
            target = stage / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        backup = Path(tmp) / "backup"
        changed = []
        try:
            for rel in sorted(files):
                source = stage / rel
                dest = package / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                old = backup / rel
                old.parent.mkdir(parents=True, exist_ok=True)
                had_old = dest.exists()
                if had_old:
                    shutil.copy2(dest, old)
                os.replace(source, dest)
                changed.append((dest, old, had_old))
            marker.write_text(sha + "\n", encoding="ascii")
        except Exception:
            for dest, old, had_old in reversed(changed):
                if had_old:
                    shutil.copy2(old, dest)
                elif dest.exists():
                    dest.unlink()
            raise
    return "Update installed. Restart Blender to load new code"


class ARCHYAR_OT_update(bpy.types.Operator):
    bl_idname = "archyar.update_addon"
    bl_label = "Update Archyar from GitHub"
    bl_description = "Fetch latest public Archyar source and install it; restart Blender"

    def execute(self, context):
        try:
            message = update_addon(context)
        except (ValueError, OSError, urllib.error.URLError, zipfile.BadZipFile, KeyError) as exc:
            self.report({'ERROR'}, "Archyar update failed: " + str(exc)[:180])
            return {'CANCELLED'}
        self.report({'INFO'}, message)
        return {'FINISHED'}


class VIEW3D_PT_archyar_update(bpy.types.Panel):
    bl_label = "Updates"
    bl_idname = "VIEW3D_PT_archyar_update"
    bl_parent_id = "VIEW3D_PT_archyar"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.operator("archyar.update_addon", icon='FILE_REFRESH')
        layout.label(text="Restart Blender after an update")
        layout.label(text="Public GitHub repository: no token needed", icon='INFO')


CLASSES = (ARCHYAR_OT_update, VIEW3D_PT_archyar_update)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
