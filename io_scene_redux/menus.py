import bpy

from . import icons
from .formats import static_ops, mesh_ops, skeleton_ops, motion_ops, model_ops
from .utils import version


import_ops = (
    (static_ops.REDUX_OT_import_static, "Redux Static (.static)", "static"),
    (mesh_ops.REDUX_OT_import_mesh, "Redux Skin Mesh (.mesh)", "mesh"),
    (skeleton_ops.REDUX_OT_import_skeleton, "Redux Skeleton (.skeleton/.lua)", "skeleton"),
    (motion_ops.REDUX_OT_import_m2, "Redux Motion (.m2)", "m2"),
    (model_ops.REDUX_OT_import_model, "Redux Model (.model)", "model"),
)
export_ops = (
    (static_ops.REDUX_OT_export_static, "Redux Static (.static)", "static"),
    (mesh_ops.REDUX_OT_export_mesh, "Redux Skin Mesh (.mesh)", "mesh"),
    (skeleton_ops.REDUX_OT_export_skeleton, "Redux Skeleton (.skeleton)", "skeleton"),
)


def _preferences():
    context = getattr(bpy, "context", None)
    addons = getattr(getattr(context, "preferences", None), "addons", None)
    addon = addons.get("io_scene_redux") if addons is not None else None
    return addon.preferences if addon else None


def get_enabled_operators(entries, mode):
    preferences = _preferences()
    return [(operator, label) for operator, label, name in entries
            if preferences is None or getattr(preferences, "enable_%s_%s" % (name, mode), True)]


def _draw_operator(operator, label):
    def draw(self, _context):
        self.layout.operator(operator.bl_idname, text=label,
                             icon_value=icons.metro_icon_id())
    return draw


_import_draw = tuple(_draw_operator(operator, label) for operator, label, _ in import_ops)
_export_draw = tuple(_draw_operator(operator, label) for operator, label, _ in export_ops)
_installed = []
_registered = False


class REDUX_MT_import(bpy.types.Menu):
    bl_idname = "REDUX_MT_import"
    bl_label = "Redux SDK"

    def draw(self, _context):
        for operator, label in get_enabled_operators(import_ops, "import"):
            self.layout.operator(operator.bl_idname, text=label,
                                 icon_value=icons.metro_icon_id())


class REDUX_MT_export(bpy.types.Menu):
    bl_idname = "REDUX_MT_export"
    bl_label = "Redux SDK"

    def draw(self, _context):
        for operator, label in get_enabled_operators(export_ops, "export"):
            self.layout.operator(operator.bl_idname, text=label,
                                 icon_value=icons.metro_icon_id())


def _draw_import_menu(self, _context):
    self.layout.menu(REDUX_MT_import.bl_idname,
                     icon_value=icons.metro_icon_id())


def _draw_export_menu(self, _context):
    self.layout.menu(REDUX_MT_export.bl_idname,
                     icon_value=icons.metro_icon_id())


def append_menu_func():
    if not _registered:
        return
    for menu, draw in _installed:
        menu.remove(draw)
    _installed.clear()
    import_menu, export_menu = version.get_import_export_menus()
    preferences = _preferences()
    compact = preferences.compact_menus if preferences else False
    if compact:
        for menu, draw, entries, mode in (
                (import_menu, _draw_import_menu, import_ops, "import"),
                (export_menu, _draw_export_menu, export_ops, "export")):
            if get_enabled_operators(entries, mode):
                menu.append(draw)
                _installed.append((menu, draw))
    else:
        for menu, entries, callbacks, mode in (
                (import_menu, import_ops, _import_draw, "import"),
                (export_menu, export_ops, _export_draw, "export")):
            enabled = {operator for operator, _ in get_enabled_operators(entries, mode)}
            for (operator, _label, _name), draw in zip(entries, callbacks):
                if operator in enabled:
                    menu.append(draw)
                    _installed.append((menu, draw))


def register():
    global _registered
    bpy.utils.register_class(REDUX_MT_import)
    bpy.utils.register_class(REDUX_MT_export)
    _registered = True
    append_menu_func()


def unregister():
    global _registered
    for menu, draw in _installed:
        menu.remove(draw)
    _installed.clear()
    _registered = False
    bpy.utils.unregister_class(REDUX_MT_export)
    bpy.utils.unregister_class(REDUX_MT_import)
