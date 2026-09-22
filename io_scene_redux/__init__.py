bl_info = {
    "name": "Redux SDK Tools",
    "author": "blender-xray contributors; MetroFormats contributors",
    "version": (0, 6, 7),
    "blender": (3, 2, 0),
    "location": "File > Import/Export",
    "description": "Import and export Redux SDK models, skeletons and compiled motions",
    "category": "Import-Export",
}


def register():
    from . import addon
    addon.register()


def unregister():
    from . import addon
    addon.unregister()
