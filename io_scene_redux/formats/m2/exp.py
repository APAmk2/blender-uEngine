import base64
import math

from ...rw import common as binary, motion
from ...utils import axis


def _integer(value, label):
    result = round(value)
    if abs(value - result) > 1e-4:
        raise binary.FormatError("%s must be an integer frame" % label)
    return result


def _animation_curve(dimensions, values, compressed_format, tolerance=1e-6):
    first = values[0]
    if all(max(abs(left - right) for left, right in zip(first, value)) <= tolerance
           for value in values[1:]):
        return motion.Curve(2, dimensions, (), (first,))
    times = tuple(index / 30.0 for index in range(len(values)))
    return motion.Curve(compressed_format, dimensions, times, tuple(values))


def _action_bones(armature, action, by_index):
    paths = tuple(curve.data_path for curve in action.fcurves)
    result = []
    for bone_id, bone in sorted(by_index.items()):
        pose_bone = armature.pose.bones.get(bone.name)
        if pose_bone is None:
            raise binary.FormatError("Armature pose is missing bone %r" % bone.name)
        prefix = pose_bone.path_from_id() + "."
        if any(path.startswith(prefix) for path in paths):
            result.append(bone_id)
    if not result:
        raise binary.FormatError("The active action has no pose-bone animation curves")
    return tuple(result)


def _target_version(context, action):
    stored = int(action.get("redux_motion_version", 0))
    if stored in (15, 16, 17, 18, 19):
        return stored
    addon = context.preferences.addons.get("io_scene_redux")
    target = addon.preferences.target_sdk if addon else "REDUX"
    return 15 if target == "REDUX" else 19


def export_data(context):
    armature = context.active_object
    if armature is None or armature.type != "ARMATURE":
        raise binary.FormatError("Select the Redux armature whose action will be exported")
    if armature.get("redux_axis_basis") != axis.BASIS_ID:
        raise binary.FormatError("Reimport this skeleton with the current Redux axis conversion")
    animation = armature.animation_data
    action = animation.action if animation else None
    if action is None:
        raise binary.FormatError("The selected armature has no active action")
    unsupported = action.get("redux_unsupported_motion_data", "")
    if unsupported:
        raise binary.FormatError(
            "This imported motion contains unsupported data (%s)" % unsupported)

    try:
        crc_value = armature["redux_bones_crc"]
        bones_crc = (int(crc_value, 16) if isinstance(crc_value, str)
                     else int(crc_value)) & 0xffffffff
    except (KeyError, TypeError, ValueError) as exc:
        raise binary.FormatError("Selected armature has no valid Redux skeleton CRC") from exc
    action_crc = action.get("redux_bones_crc")
    if action_crc is not None:
        parsed = int(action_crc, 16) if isinstance(action_crc, str) else int(action_crc)
        if parsed & 0xffffffff != bones_crc:
            raise binary.FormatError("Action skeleton CRC does not match the selected armature")

    by_index = {int(bone.get("redux_index", index)): bone
                for index, bone in enumerate(armature.data.bones)}
    bones_count = len(armature.data.bones)
    if set(by_index) != set(range(bones_count)):
        raise binary.FormatError("Armature Redux bone indices are incomplete or duplicated")
    animated_bones = _action_bones(armature, action, by_index)
    version = _target_version(context, action)
    capacity = 128 if version == 15 else 256
    if animated_bones[-1] >= capacity:
        raise binary.FormatError(
            "Motion version %d supports animated bone IDs below %d" % (version, capacity))

    frame_start = _integer(action.frame_range[0], "Action start")
    frame_end = _integer(action.frame_range[1], "Action end")
    frame_total = frame_end - frame_start + 1
    if not 0 <= frame_start <= 0xffff or not 0 < frame_total <= 0xffff:
        raise binary.FormatError("Motion frame range does not fit the .m2 header")

    rotations = {bone_id: [] for bone_id in animated_bones}
    translations = {bone_id: [] for bone_id in animated_bones}
    previous = {}
    original_frame = context.scene.frame_current
    try:
        for frame in range(frame_start, frame_start + frame_total):
            context.scene.frame_set(frame)
            for bone_id in animated_bones:
                bone = by_index[bone_id]
                pose_bone = armature.pose.bones[bone.name]
                rest_local = (bone.parent.matrix_local.inverted() @ bone.matrix_local
                              if bone.parent else bone.matrix_local)
                animated_local = rest_local @ pose_bone.matrix_basis
                scale = animated_local.to_scale()
                if any(not math.isfinite(value) or abs(value - 1.0) > 1e-4
                       for value in scale):
                    raise binary.FormatError(
                        "Bone %r has animated scale at frame %d; .m2 scale export is unsupported" %
                        (bone.name, frame))
                local = axis.to_redux_matrix(animated_local)
                quaternion = local.to_quaternion().inverted().normalized()
                value = (quaternion.x, quaternion.y, quaternion.z, quaternion.w)
                prior = previous.get(bone_id)
                if prior is not None and sum(a * b for a, b in zip(prior, value)) < 0:
                    value = tuple(-component for component in value)
                previous[bone_id] = value
                rotations[bone_id].append(value)
                translation = tuple(local.translation)
                if any(not math.isfinite(value) for value in translation):
                    raise binary.FormatError(
                        "Bone %r has a non-finite transform at frame %d" %
                        (bone.name, frame))
                translations[bone_id].append(translation)
    finally:
        context.scene.frame_set(original_frame)

    curves = tuple((
        _animation_curve(4, rotations[bone_id], 5),
        _animation_curve(3, translations[bone_id], 4),
        motion.Curve(7, 3, (), ())) for bone_id in animated_bones)
    offset = tuple(action.get("redux_position_offset", (0.0, 0.0, 0.0)))
    speed = float(action.get("redux_speed", 1.0))
    clip = motion.Motion(bones_crc, bones_count, frame_start, frame_total,
                         offset, speed, animated_bones, curves, (), ())
    extra_chunks = ()
    encoded = action.get("redux_motion_extra_chunks", "")
    if encoded:
        try:
            extra_chunks = tuple(binary.chunks(base64.b64decode(encoded, validate=True)))
        except (ValueError, TypeError) as exc:
            raise binary.FormatError("Saved optional motion chunks are invalid") from exc
        if any(ident not in (6, 7, 8) for ident, _payload in extra_chunks):
            raise binary.FormatError("Saved motion data contains an invalid optional chunk")
    return motion.write_m2(clip, version, extra_chunks)
