import base64
from ...rw import skeleton as binary
from ...utils import axis

def _export_skeleton(context):
    obj = context.active_object
    if not obj or obj.type != "ARMATURE" or "redux_skeleton_data" not in obj:
        raise binary.FormatError("Select an imported Redux skeleton armature")
    if obj.get("redux_axis_basis") != axis.BASIS_ID:
        raise binary.FormatError("Reimport this skeleton with the current Redux axis conversion")
    original = binary.read_skeleton(base64.b64decode(obj["redux_skeleton_data"]))
    old_by_name = {b.name: b for b in original.bones}
    bones = []
    if set(b.name for b in obj.data.bones) != set(old_by_name):
        raise binary.FormatError("Changed bone names require a new skeleton CRC")
    for original_bone in original.bones:
        bone = obj.data.bones[original_bone.name]
        local_blender = (bone.parent.matrix_local.inverted() @ bone.matrix_local
                         if bone.parent else bone.matrix_local)
        local = axis.to_redux_matrix(local_blender)
        q = local.to_quaternion().inverted()
        bones.append(binary.Bone(bone.name, bone.parent.name if bone.parent else "",
                                 (q.x, q.y, q.z, q.w), tuple(local.translation),
                                 int(bone.get("redux_body_part", old_by_name[bone.name].body_part))))
    original.bones = bones
    return binary.write_skeleton(original)


export_data = _export_skeleton

