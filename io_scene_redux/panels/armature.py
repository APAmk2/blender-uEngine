import bpy

from .. import icons


class REDUX_PT_armature(bpy.types.Panel):
    bl_label = "Redux SDK Skeleton"
    bl_idname = "REDUX_PT_armature"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"

    def draw_header(self, _context):
        self.layout.label(icon_value=icons.metro_icon_id())

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == "ARMATURE" and \
            "redux_bones_crc" in context.object

    def draw(self, context):
        obj = context.object
        value = obj["redux_bones_crc"]
        self.layout.label(text="Bone CRC: %s" % (
            value if isinstance(value, str) else "%08X" % (int(value) & 0xffffffff)))
        self.layout.label(text="Bones: %d" % len(obj.data.bones))
        if obj.get("redux_skeleton_key"):
            self.layout.label(text="Source: " + obj["redux_skeleton_key"])


def register():
    bpy.utils.register_class(REDUX_PT_armature)


def unregister():
    bpy.utils.unregister_class(REDUX_PT_armature)
