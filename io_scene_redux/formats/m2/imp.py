from pathlib import Path
import bpy
from mathutils import Matrix, Quaternion, Vector
from ...rw import common as binary, motion
from ...utils import action as action_utils, axis, version
from ..common import _active_armature, _bones_by_index
from ..skeleton.imp import _load_matching_skeleton, _skeleton_key_for_motion

def _import_m2(context, path, data):
    clip = motion.read_m2(data)
    skeleton_key = _skeleton_key_for_motion(context, path, clip.bones_crc)
    armature = _active_armature(context, clip.bones_crc, skeleton_key)
    if armature is None:
        armature = _load_matching_skeleton(context, path, clip.bones_crc, skeleton_key)
    if armature is None:
        raise binary.FormatError("No skeleton with bone CRC %08X; import one first or set SDK content directory" % clip.bones_crc)
    if len(armature.data.bones) != clip.bones_count:
        raise binary.FormatError("Animation and armature bone counts differ")
    by_index = {int(bone.get("redux_index", index)): bone.name
                for index, bone in enumerate(armature.data.bones)}
    if len(by_index) != clip.bones_count:
        raise binary.FormatError("Armature has duplicate Redux bone indices")
    if clip.frame_total > 10000:
        raise binary.FormatError("Clip exceeds the 10000-frame Blender import limit")
    for bone_id, curves in zip(clip.animated_bones, clip.bone_curves):
        if bone_id not in by_index:
            raise binary.FormatError("Animation refers to unknown bone %d" % bone_id)
        if any(curve.format not in (2, 4, 5, 7) for curve in curves):
            raise binary.FormatError("Unsupported animated bone curve format")
        rotation_curve, translation_curve, scale_curve = curves
        if rotation_curve.dimensions != 4 or translation_curve.dimensions != 3:
            raise binary.FormatError("Unexpected bone rotation/translation dimensions")
        if scale_curve.format != 7:
            raise binary.FormatError("Animated bone scale curves are not yet supported")

    context.view_layer.objects.active = armature
    armature.select_set(True)
    armature.animation_data_create()
    action = bpy.data.actions.new(Path(path).stem)
    action.use_fake_user = True  # Keep every clip when a batch assigns the next Action.
    action["redux_bones_crc"] = "%08X" % clip.bones_crc
    action["redux_frame_start"] = clip.frame_start
    action["redux_frame_total"] = clip.frame_total
    action["redux_position_offset"] = tuple(clip.position_offset)
    action["redux_speed"] = clip.speed
    armature.animation_data.action = action
    version.set_action_slot(armature, action)
    context.scene.render.fps = 30
    context.scene.render.fps_base = 1.0
    for pose_bone in armature.pose.bones:
        pose_bone.matrix_basis = Matrix.Identity(4)
        pose_bone.rotation_mode = "QUATERNION"

    for bone_id, curves in zip(clip.animated_bones, clip.bone_curves):
        name = by_index[bone_id]
        rotation_curve, translation_curve, scale_curve = curves
        bone = armature.data.bones[name]
        pose_bone = armature.pose.bones[name]
        rest_local = (bone.parent.matrix_local.inverted() @ bone.matrix_local
                      if bone.parent else bone.matrix_local)
        rest_inverse = rest_local.inverted()
        for frame_index in range(clip.frame_total):
            time = frame_index / 30.0
            qxyzw = rotation_curve.sample(time)
            position = translation_curve.sample(time)
            quaternion = Quaternion((qxyzw[3], *qxyzw[:3])).inverted()
            animated_local = axis.to_blender_matrix(
                Matrix.Translation(Vector(position)) @ quaternion.to_matrix().to_4x4())
            pose_bone.matrix_basis = rest_inverse @ animated_local
            frame = clip.frame_start + frame_index
            pose_bone.keyframe_insert(data_path="location", frame=frame, group=name)
            pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame, group=name)
    context.scene.frame_start = clip.frame_start
    context.scene.frame_end = clip.frame_start + clip.frame_total - 1
    context.scene.frame_set(clip.frame_start)
    action_utils.set_action_linear(action)
    return 1


def import_path(context, path):
    return _import_m2(context, path, Path(path).read_bytes())

