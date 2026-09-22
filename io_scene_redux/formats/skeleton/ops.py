import bpy
from bpy.props import CollectionProperty, StringProperty
from bpy_extras.io_utils import ImportHelper, ExportHelper
from ...utils import ie
from . import imp, exp


class REDUX_OT_import_skeleton(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.redux_skeleton"
    bl_label = "Import Redux Skeleton"
    bl_options = {"UNDO"}
    filename_ext = ".skeleton"
    filter_glob: StringProperty(default="*.skeleton;*.skeleton.lua", options={"HIDDEN"})
    files: CollectionProperty(type=bpy.types.OperatorFileListElement, options={"HIDDEN"})
    directory: StringProperty(subtype="DIR_PATH", options={"HIDDEN"})

    def execute(self, context):
        return ie.run_import(self, context, imp.import_path)


class REDUX_OT_export_skeleton(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.redux_skeleton"
    bl_label = "Export Redux Skeleton"
    filename_ext = ".skeleton"
    filter_glob: StringProperty(default="*.skeleton", options={"HIDDEN"})

    def execute(self, context):
        return ie.run_export(self, context, exp.export_data, ".skeleton")


CLASSES = (REDUX_OT_import_skeleton, REDUX_OT_export_skeleton)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
