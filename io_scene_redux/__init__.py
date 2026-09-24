bl_info = {
    "name": "4A Engine SDK Tools",
    "author": "APAMk2",
    "version": (0, 7, 0),
    "blender": (3, 2, 0),
    "location": "File > Import/Export",
    "description": "Import and export 4A Engine SDK models, skeletons and compiled motions",
    "category": "Import-Export",
}


def register():
    from . import addon
    addon.register()


def unregister():
    from . import addon
    addon.unregister()
