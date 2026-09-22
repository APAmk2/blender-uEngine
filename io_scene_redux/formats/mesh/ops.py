import bpy
from bpy.props import BoolProperty, CollectionProperty, StringProperty
from bpy_extras.io_utils import ImportHelper, ExportHelper
from ...utils import ie
from . import imp, exp


class REDUX_OT_import_mesh(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.redux_mesh"
    bl_label = "Import Redux Skin Mesh"
    bl_options = {"UNDO"}
    filename_ext = ".mesh"
    filter_glob: StringProperty(default="*.mesh", options={"HIDDEN"})
    files: CollectionProperty(type=bpy.types.OperatorFileListElement, options={"HIDDEN"})
    directory: StringProperty(subtype="DIR_PATH", options={"HIDDEN"})

    def execute(self, context):
        return ie.run_import(self, context, imp.import_path)


class REDUX_OT_export_mesh(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.redux_mesh"
    bl_label = "Export Redux Skin Mesh"
    filename_ext = ".mesh"
    filter_glob: StringProperty(default="*.mesh", options={"HIDDEN"})
    recompute_bone_boxes: BoolProperty(name="Recompute bone boxes", default=False)

    def execute(self, context):
        return ie.run_export(self, context, exp.export_data, ".mesh",
                             recompute_bone_boxes=self.recompute_bone_boxes)


CLASSES = (REDUX_OT_import_mesh, REDUX_OT_export_mesh)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
