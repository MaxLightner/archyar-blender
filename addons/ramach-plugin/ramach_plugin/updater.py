"""Explicit GitHub updater: validate, stage, back up and replace this package only."""

import io
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.error
import urllib.request
import zipfile

import bpy


REPOSITORY = "MaxLightner/archyar-blender"
REPO_PATH = ("addons", "ramach-plugin", "ramach_plugin")
API = f"https://api.github.com/repos/{REPOSITORY}"
MAX_ARCHIVE_BYTES = 30 * 1024 * 1024
MAX_FILE_BYTES = 3 * 1024 * 1024
ALLOWED_FILE_EXTENSIONS = {".py", ".json", ".txt"}


def _fetch(url, limit):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Ramach-Blender-Updater/0.1",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(req, timeout=25) as response:
        blob = response.read(limit + 1)
    if len(blob) > limit:
        raise ValueError("GitHub response exceeds the safe size limit")
    return blob


def _latest_source_revision():
    path = "/".join(REPO_PATH)
    commits_url = API + "/commits?path=" + path + "&per_page=1"
    commits = json.loads(_fetch(commits_url, 1024 * 1024))
    if not isinstance(commits, list) or not commits:
        raise ValueError("No published Ramach Plugin source found on GitHub")
    revision = str(commits[0].get("sha", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("GitHub supplied an invalid commit SHA")
    return revision


def _package_files_from_archive(blob):
    found = {}
    unpacked_bytes = 0
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        for info in archive.infolist():
            parts = info.filename.split("/")
            if info.is_dir() or tuple(parts[1:4]) != REPO_PATH:
                continue
            subpath = parts[4:]
            if not subpath or any(part in ("", ".", "..") for part in subpath):
                raise ValueError("Invalid file path in update archive")
            rel = Path(*subpath)
            if rel.suffix not in ALLOWED_FILE_EXTENSIONS:
                continue
            if info.file_size > MAX_FILE_BYTES or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Invalid or oversized file in update archive")
            unpacked_bytes += info.file_size
            if unpacked_bytes > MAX_ARCHIVE_BYTES or len(found) >= 100:
                raise ValueError("Too many files or excessive extracted data in archive")
            found[rel] = archive.read(info)
    if Path("__init__.py") not in found or len(found) > 100:
        raise ValueError("Archive is missing the Ramach Plugin package")
    return found


def _save_previous_version(package, archive_path):
    """Keep a standard installable ZIP for manual recovery after an update."""
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for file in package.rglob("*"):
            if file.is_file() and (file.suffix in ALLOWED_FILE_EXTENSIONS or file.name == "_installed_sha"):
                archive.write(file, arcname=str(Path("ramach_plugin") / file.relative_to(package)))


def update_from_github():
    package = Path(__file__).resolve().parent
    if package.is_symlink():
        raise ValueError("Updater cannot replace a symlinked add-on")
    revision = _latest_source_revision()
    installed_revision = package / "_installed_sha"
    if installed_revision.is_file() and installed_revision.read_text(encoding="ascii").strip() == revision:
        return "Ramach Plugin is already up to date"

    files = _package_files_from_archive(_fetch(API + "/zipball/" + revision, MAX_ARCHIVE_BYTES))
    # Stage the complete new package before touching the installed code.
    with tempfile.TemporaryDirectory(prefix="ramach-update-", dir=str(package.parent)) as temp:
        temporary = Path(temp)
        staged = temporary / "ramach_plugin"
        staged.mkdir()
        for rel, data in files.items():
            out = staged / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
        (staged / "_installed_sha").write_text(revision + "\n", encoding="ascii")
        saved = temporary / "ramach-plugin-previous.zip"
        _save_previous_version(package, saved)
        backup = temporary / "previous_package"
        package.rename(backup)
        try:
            staged.rename(package)
        except Exception:
            backup.rename(package)
            raise
        # The previous version remains available as an installable backup ZIP.
        try:
            os.replace(saved, package.parent / "ramach-plugin-previous.zip")
        except OSError:
            pass  # An update must not be rolled back only because backup copy failed.
    return "Update installed successfully. Restart Blender to activate it"


class RAMACH_OT_update(bpy.types.Operator):
    bl_idname = "ramach.update_from_github"
    bl_label = "Update from GitHub"
    bl_description = "Download and install only Ramach Plugin from the official repository; restart Blender"

    def execute(self, context):
        try:
            message = update_from_github()
        except (OSError, ValueError, urllib.error.URLError, zipfile.BadZipFile, KeyError) as exc:
            self.report({'ERROR'}, "Update failed: " + str(exc)[:190])
            return {'CANCELLED'}
        self.report({'INFO'}, message)
        return {'FINISHED'}
