from . import formats, icons, menus, panels, prefs

modules = (formats, prefs, icons, panels, menus)


def register():
    for module in modules:
        module.register()


def unregister():
    for module in reversed(modules):
        module.unregister()
