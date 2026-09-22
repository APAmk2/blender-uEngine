import bpy
from bpy.props import CollectionProperty, IntProperty, StringProperty
from bpy_extras.io_utils import ImportHelper

from ...utils import ie
from . import imp


class REDUX_OT_import_model(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.redux_model"
    bl_label = "Import Redux Model"
    bl_options = {"UNDO"}
    filename_ext = ".model"
    filter_glob: StringProperty(default="*.model", options={"HIDDEN"})
    files: CollectionProperty(type=bpy.types.OperatorFileListElement, options={"HIDDEN"})
    directory: StringProperty(subtype="DIR_PATH", options={"HIDDEN"})
    lod: IntProperty(name="LOD", description="LOD index to import", default=0, min=0, max=255)

    def execute(self, context):
        return ie.run_import(self, context,
                             lambda ctx, path: imp.import_path(ctx, path, self.lod))


CLASSES = (REDUX_OT_import_model,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
