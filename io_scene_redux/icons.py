from pathlib import Path
import pkgutil
import tempfile

import bpy
from bpy.utils import previews


_preview = None
_temporary_directory = None


def register():
    global _preview, _temporary_directory
    icon_path = Path(__file__).with_name("metro.png")
    if not icon_path.is_file():
        data = pkgutil.get_data(__package__, "metro.png")
        if data is None:
            raise FileNotFoundError("metro.png is missing from the Redux add-on")
        _temporary_directory = tempfile.TemporaryDirectory(prefix="redux_icon_")
        icon_path = Path(_temporary_directory.name) / "metro.png"
        icon_path.write_bytes(data)
    preview = previews.new()
    try:
        preview.load("metro", str(icon_path), "IMAGE")
    except Exception:
        previews.remove(preview)
        if _temporary_directory is not None:
            _temporary_directory.cleanup()
            _temporary_directory = None
        raise
    _preview = preview


def unregister():
    global _preview, _temporary_directory
    if _preview is not None:
        previews.remove(_preview)
        _preview = None
    if _temporary_directory is not None:
        _temporary_directory.cleanup()
        _temporary_directory = None


def metro_icon_id():
    icon = _preview["metro"]
    # Blender may leave the preview unrendered until its pixel data is touched.
    len(icon.icon_pixels)
    return icon.icon_id
