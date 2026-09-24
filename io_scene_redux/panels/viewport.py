from pathlib import Path

import bpy

from .. import icons
from ..formats import static_ops, mesh_ops, skeleton_ops, motion_ops, model_ops
from ..formats import common as format_common


class REDUX_OT_reload_textures(bpy.types.Operator):
    bl_idname = "redux.reload_textures"
    bl_label = "Reload Redux Textures"
    bl_description = "Resolve textures for materials on selected Redux meshes"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(obj.type == "MESH" for obj in context.selected_objects)

    def execute(self, context):
        addon = context.preferences.addons.get("io_scene_redux")
        if addon is None or not addon.preferences.content_root:
            self.report({"ERROR"}, "Set SDK content directory in Redux add-on preferences")
            return {"CANCELLED"}
        root = Path(bpy.path.abspath(addon.preferences.content_root))
        if not (root / "textures").is_dir():
            self.report({"ERROR"}, "SDK content directory has no textures folder")
            return {"CANCELLED"}
        materials = {mat for obj in context.selected_objects if obj.type == "MESH"
                     for mat in obj.data.materials if mat and mat.get("redux_texture")}
        for material in materials:
            record = format_common._mat_record(material, material.name)
            format_common._material(context, str(root), material.name, record)
        loaded = sum(mat.get("redux_texture_status") == "Loaded" for mat in materials)
        self.report({"INFO"}, "Loaded %d of %d Redux texture(s)" % (loaded, len(materials)))
        return {"FINISHED"}


class ReduxViewPanel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Redux"


class REDUX_PT_tools(ReduxViewPanel, bpy.types.Panel):
    bl_idname = "REDUX_PT_tools"
    bl_label = "Redux SDK Tools"

    def draw_header(self, _context):
        self.layout.label(icon_value=icons.metro_icon_id())

    def draw(self, context):
        layout = self.layout
        addon = context.preferences.addons.get("io_scene_redux")
        if addon:
            layout.prop(addon.preferences, "content_root", text="SDK Content")
        layout.label(text="Import")
        column = layout.column(align=True)
        for operator, label in (
                (static_ops.REDUX_OT_import_static, "Static"),
                (mesh_ops.REDUX_OT_import_mesh, "Skin Mesh"),
                (skeleton_ops.REDUX_OT_import_skeleton, "Skeleton"),
                (motion_ops.REDUX_OT_import_m2, "Motion")):
            column.operator(operator.bl_idname, text=label)
        column.operator(model_ops.REDUX_OT_import_model.bl_idname, text="Model Assembly")
        layout.label(text="Export Selected")
        column = layout.column(align=True)
        column.active = bool(context.selected_objects)
        for operator, label in (
                (static_ops.REDUX_OT_export_static, "Static"),
                (mesh_ops.REDUX_OT_export_mesh, "Skin Mesh"),
                (skeleton_ops.REDUX_OT_export_skeleton, "Skeleton"),
                (motion_ops.REDUX_OT_export_m2, "Motion")):
            column.operator(operator.bl_idname, text=label)


class REDUX_PT_model(ReduxViewPanel, bpy.types.Panel):
    bl_idname = "REDUX_PT_model"
    bl_parent_id = "REDUX_PT_tools"
    bl_label = "Selected Model"

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and
                context.active_object.type == "MESH" and
                context.active_object.get("redux_format") in ("static", "mesh"))

    def draw(self, context):
        obj = context.active_object
        layout = self.layout
        layout.label(text="Format: " + obj["redux_format"])
        if "redux_part" in obj:
            layout.label(text="Part: %d" % obj["redux_part"])
        if obj.get("redux_source_text"):
            layout.label(text="Source: " + obj["redux_source_text"])
        layout.operator(REDUX_OT_reload_textures.bl_idname, icon="FILE_REFRESH")
        material = obj.active_material
        if material and material.get("redux_texture"):
            layout.label(text="Texture: " + material["redux_texture"])
            if material.get("redux_texture_status"):
                layout.label(text=material["redux_texture_status"])


class REDUX_PT_skeleton(ReduxViewPanel, bpy.types.Panel):
    bl_idname = "REDUX_PT_skeleton"
    bl_parent_id = "REDUX_PT_tools"
    bl_label = "Selected Skeleton"

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and
                context.active_object.type == "ARMATURE" and
                "redux_bones_crc" in context.active_object)

    def draw(self, context):
        obj = context.active_object
        layout = self.layout
        layout.label(text="Bone CRC: " + str(obj["redux_bones_crc"]))
        layout.label(text="Bones: %d" % len(obj.data.bones))
        if obj.get("redux_skeleton_key"):
            layout.label(text="Source: " + obj["redux_skeleton_key"])
        if obj.animation_data:
            layout.template_ID(obj.animation_data, "action")


CLASSES = (REDUX_OT_reload_textures, REDUX_PT_tools,
           REDUX_PT_model, REDUX_PT_skeleton)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
