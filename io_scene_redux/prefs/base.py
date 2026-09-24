import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty


def _update_menus(_self, _context):
    from .. import menus
    menus.append_menu_func()


class REDUX_Preferences(bpy.types.AddonPreferences):
    bl_idname = "io_scene_redux"

    category: EnumProperty(
        name="Settings", items=(("PATHS", "Paths", "SDK paths"),
                                ("FORMATS", "Formats", "Import and export menus"),
                                ("DISPLAY", "Display", "Texture loading")),
        default="PATHS")
    target_sdk: EnumProperty(
        name="Target SDK",
        description="SDK whose content directory and model format are being used",
        items=(("REDUX", "Redux", "Metro 2033 Redux / Last Light Redux SDK"),
               ("M3", "M3", "Metro Exodus SDK content, model versions through 48"),
               ("M4_2022", "M4 2022", "2022 M4 editor content, model version 55")),
        default="REDUX")
    content_root: StringProperty(
        name="SDK content directory", subtype="DIR_PATH",
        description="Path to the selected SDK's content directory; used to find textures, meshes and skeletons")
    auto_skeleton: BoolProperty(name="Load matching skeleton with .mesh", default=True)
    load_textures: BoolProperty(
        name="Load textures", default=True,
        description="Load source images, falling back to compiled engine texture tiers")
    compact_menus: BoolProperty(name="Compact import/export menus", default=False,
                                update=_update_menus)
    enable_static_import: BoolProperty(name="Static import", default=True, update=_update_menus)
    enable_mesh_import: BoolProperty(name="Skin mesh import", default=True, update=_update_menus)
    enable_skeleton_import: BoolProperty(name="Skeleton import", default=True, update=_update_menus)
    enable_m2_import: BoolProperty(name="Motion import", default=True, update=_update_menus)
    enable_model_import: BoolProperty(name="Model import", default=True, update=_update_menus)
    enable_static_export: BoolProperty(name="Static export", default=True, update=_update_menus)
    enable_mesh_export: BoolProperty(name="Skin mesh export", default=True, update=_update_menus)
    enable_skeleton_export: BoolProperty(name="Skeleton export", default=True, update=_update_menus)

    def draw(self, _context):
        from . import ui
        ui.draw(self.layout, self)


def register():
    bpy.utils.register_class(REDUX_Preferences)


def unregister():
    bpy.utils.unregister_class(REDUX_Preferences)
