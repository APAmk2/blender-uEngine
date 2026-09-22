from pathlib import Path


SOURCE_EXTENSIONS = (".png", ".tga", ".psd", ".jpg", ".jpeg",
                     ".tif", ".tiff", ".bmp", ".dds")


def normalize_tex_relpath(name):
    parts = name.replace("/", "\\").split("\\")
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ValueError("Invalid Redux texture path")
    return parts


def make_abs_tex_path(content_root, texture_name):
    path = Path(content_root).joinpath("textures", *normalize_tex_relpath(texture_name))
    return Path(str(path) + ".png")


def texture_candidates(content_root, texture_name):
    """Source images for one Redux texture name, in preferred order."""
    base = Path(content_root).joinpath("textures", *normalize_tex_relpath(texture_name))
    if base.suffix.lower() in SOURCE_EXTENSIONS:
        yield base
        base = base.with_suffix("")
    for extension in SOURCE_EXTENSIONS:
        yield Path(str(base) + extension)


def load_image_by_tex_path(path):
    import bpy
    if not path.is_file():
        return None
    try:
        image = bpy.data.images.load(str(path), check_existing=True)
        return image if all(image.size) else None
    except RuntimeError:
        return None


def load_texture_image(content_root, texture_name):
    for path in texture_candidates(content_root, texture_name):
        image = load_image_by_tex_path(path)
        if image is not None:
            return image, path
    return None, None
