import bpy
from bpy.props import CollectionProperty, StringProperty
from bpy_extras.io_utils import ImportHelper, ExportHelper
from ...utils import ie
from . import imp, exp


class REDUX_OT_import_m2(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.redux_m2"
    bl_label = "Import Redux Motion"
    bl_options = {"UNDO"}
    filename_ext = ".m2"
    filter_glob: StringProperty(default="*.m2", options={"HIDDEN"})
    files: CollectionProperty(type=bpy.types.OperatorFileListElement, options={"HIDDEN"})
    directory: StringProperty(subtype="DIR_PATH", options={"HIDDEN"})

    def execute(self, context):
        return ie.run_import(self, context, imp.import_path)


class REDUX_OT_export_m2(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.redux_m2"
    bl_label = "Export Redux Motion"
    filename_ext = ".m2"
    filter_glob: StringProperty(default="*.m2", options={"HIDDEN"})

    def execute(self, context):
        return ie.run_export(self, context, exp.export_data, ".m2")


def register():
    bpy.utils.register_class(REDUX_OT_import_m2)
    bpy.utils.register_class(REDUX_OT_export_m2)


def unregister():
    bpy.utils.unregister_class(REDUX_OT_export_m2)
    bpy.utils.unregister_class(REDUX_OT_import_m2)
