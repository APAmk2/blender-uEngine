from . import material, armature, viewport

MODULES = (material, armature, viewport)


def register():
    for module in MODULES:
        module.register()


def unregister():
    for module in reversed(MODULES):
        module.unregister()
