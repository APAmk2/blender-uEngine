import bpy
from bpy.props import BoolProperty, CollectionProperty, StringProperty
from bpy_extras.io_utils import ImportHelper, ExportHelper
from ...utils import ie
from . import imp, exp


class REDUX_OT_import_static(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.redux_static"
    bl_label = "Import Redux Static"
    bl_options = {"UNDO"}
    filename_ext = ".static"
    filter_glob: StringProperty(default="*.static", options={"HIDDEN"})
    files: CollectionProperty(type=bpy.types.OperatorFileListElement, options={"HIDDEN"})
    directory: StringProperty(subtype="DIR_PATH", options={"HIDDEN"})

    def execute(self, context):
        return ie.run_import(self, context, imp.import_path)


class REDUX_OT_export_static(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.redux_static"
    bl_label = "Export Redux Static"
    filename_ext = ".static"
    filter_glob: StringProperty(default="*.static", options={"HIDDEN"})
    apply_modifiers: BoolProperty(name="Apply modifiers", default=False)
    apply_transform: BoolProperty(name="Apply object transform", default=True)

    def execute(self, context):
        return ie.run_export(self, context, exp.export_data, ".static",
                             apply_modifiers=self.apply_modifiers,
                             apply_transform=self.apply_transform)


CLASSES = (REDUX_OT_import_static, REDUX_OT_export_static)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
