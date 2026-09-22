import base64
from pathlib import Path
import re
import bpy
from mathutils import Matrix, Quaternion, Vector
from ...rw import skeleton as binary, lua_redux as lua
from ...utils.formats_io import ChunkedReader, Reader
from ...utils import axis, ie, version
from ..common import _active_armature, _content_root


_motion_skeleton_keys = {}


def _bone_matrices(skeleton):
    by_name = {bone.name: bone for bone in skeleton.bones}
    cache = {}

    def matrix(name, stack=()):
        if name in cache:
            return cache[name]
        if name in stack:
            raise binary.FormatError("Cyclic bone hierarchy")
        bone = by_name[name]
        if len(bone.q) == 4:
            # Skeleton archives store the inverse of the bone's local rotation.
            rotation = Quaternion((bone.q[3], *bone.q[:3])).inverted().to_matrix().to_4x4()
        else:
            from mathutils import Euler
            rotation = Euler(bone.q).to_matrix().inverted().to_4x4()
        local = axis.to_blender_matrix(Matrix.Translation(Vector(bone.t)) @ rotation)
        cache[name] = matrix(bone.parent, stack + (name,)) @ local if bone.parent in by_name else local
        return cache[name]

    return {name: matrix(name) for name in by_name}

def _create_armature(context, name, skeleton, source_data=None, source_key=None):
    ie.ensure_object_mode(context)
    converted_legacy = False
    if any(len(b.q) == 3 for b in skeleton.bones):
        converted_legacy = True
        from mathutils import Euler
        for bone in skeleton.bones:
            if len(bone.q) == 3:
                q = Euler(bone.q).to_quaternion()
                bone.q = (q.x, q.y, q.z, q.w)
        skeleton.version = 4
    arm = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, arm)
    obj["redux_axis_basis"] = axis.BASIS_ID
    version.link_object(obj, context)
    version.set_active_object(obj, context)
    version.select_object(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    matrices = _bone_matrices(skeleton)
    for bone in skeleton.bones:
        eb = arm.edit_bones.new(bone.name)
        eb.length = 0.1
        eb.matrix = matrices[bone.name]
    for bone in skeleton.bones:
        if bone.parent in arm.edit_bones:
            arm.edit_bones[bone.name].parent = arm.edit_bones[bone.parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    for index, bone in enumerate(skeleton.bones):
        arm.bones[bone.name]["redux_body_part"] = bone.body_part
        arm.bones[bone.name]["redux_index"] = index
    obj["redux_bones_crc"] = "%08X" % skeleton.crc
    if source_key:
        obj["redux_skeleton_key"] = source_key
    if source_data is not None and not converted_legacy:
        serialized = source_data
    else:
        serialized = binary.write_skeleton(binary.Skeleton(
            skeleton.bones, skeleton.crc, skeleton.locators, skeleton.partitions,
            skeleton.params, skeleton.motions))
    obj["redux_skeleton_data"] = base64.b64encode(serialized).decode("ascii")
    return obj

def _model_skeleton_key(chunks):
    for ident, payload in chunks:
        if ident == 20:
            reader = Reader(payload)
            key = reader.stringz().replace("/", "\\")
            reader.done()
            parts = key.split("\\")
            if not parts or any(part in ("", ".", "..") or ":" in part for part in parts):
                raise binary.FormatError("Invalid skeleton key in companion .model")
            return "\\".join(parts)
    return None


def _skeleton_key_from_model(source_path):
    """Read the explicit skeleton reference in a mesh's companion .model."""
    model_path = Path(source_path).with_suffix(".model")
    return (_model_skeleton_key(ChunkedReader(model_path.read_bytes()))
            if model_path.is_file() else None)


def _skeleton_key_from_parent_models(source_path, meshes):
    """Find a rig named by a nearby .model that lists this mesh in chunk 16."""
    source = Path(source_path)
    if not source.is_relative_to(meshes):
        return None
    mesh_key = source.relative_to(meshes).with_suffix("").as_posix().replace("/", "\\").lower()
    keys = set()
    for model_path in source.parent.glob("*.model"):
        chunks = list(ChunkedReader(model_path.read_bytes()))
        payloads = dict(chunks)
        if 16 not in payloads or 20 not in payloads:
            continue
        reader = Reader(payloads[16])
        count = reader.unpack("<I")[0]
        if count > 256:
            continue
        references = []
        for _ in range(count):
            references.extend(item.strip().replace("/", "\\").lower()
                              for item in reader.stringz().split(","))
        reader.done()
        if mesh_key in references:
            key = _model_skeleton_key(chunks)
            if key:
                keys.add(key.lower())
    if len(keys) > 1:
        raise binary.FormatError("Nearby .model files name different skeletons for this .mesh")
    return next(iter(keys), None)


def _skeleton_from_prefix_model(source_path):
    """Find the most specific sibling model whose stem prefixes a mesh part.

    Legacy assets can split an assembly into files such as
    ``name_radio.mesh`` while only ``name.model`` records the skeleton.
    """
    source = Path(source_path)
    source_stem = source.stem.lower()
    candidates = []
    for model_path in source.parent.glob("*.model"):
        model_stem = model_path.stem.lower()
        if not model_stem or not source_stem.startswith(model_stem + "_"):
            continue
        key = _model_skeleton_key(list(ChunkedReader(model_path.read_bytes())))
        if key:
            candidates.append((len(model_stem), model_path, key.lower()))
    if not candidates:
        return None
    length = max(item[0] for item in candidates)
    matches = {(model_path, key) for candidate_length, model_path, key in candidates
            if candidate_length == length}
    keys = {key for _model_path, key in matches}
    if len(keys) > 1:
        raise binary.FormatError("Prefix-matching .model files name different skeletons")
    return next(iter(matches))


def _skeleton_key_for_mesh(context, source_path, crc):
    """Prefer the model's rig, except when it describes an assembly rig.

    Some character .model files reference the shared human rig while their
    same-name .mesh is a one-bone attachment with a local skeleton.
    """
    preferred = _skeleton_key_from_model(source_path)
    root = _content_root(context, source_path)
    meshes = root / "meshes" if root else None
    if meshes is None or not meshes.is_dir():
        return preferred
    if preferred is None:
        preferred = _skeleton_key_from_parent_models(source_path, meshes)
    if preferred is None:
        suggestion = _skeleton_from_prefix_model(source_path)
        if suggestion:
            model_path, suggested_key = suggestion
            if _active_armature(context, crc, suggested_key):
                return suggested_key
            raise binary.FormatError(
                "%s has no explicit skeleton reference. Import companion .model first: %s" %
                (Path(source_path).name, model_path))
    if preferred is None:
        return None

    def matching_skeleton(stem):
        for suffix in (".skeleton.lua", ".skeleton"):
            path = Path(str(stem) + suffix)
            if not path.is_file():
                continue
            data = path.read_bytes()
            skeleton = (lua.read_skeleton_lua(data.decode("utf-8", "surrogateescape"))
                        if suffix == ".skeleton.lua" else binary.read_skeleton(data))
            if skeleton.crc == crc:
                return path
        return None

    preferred_stem = meshes.joinpath(*preferred.split("\\"))
    if matching_skeleton(preferred_stem):
        return preferred
    local_path = matching_skeleton(Path(source_path).with_suffix(""))
    if local_path and local_path.is_relative_to(meshes):
        return _key_for_path(local_path, meshes)
    return preferred


def _key_for_path(path, meshes_root):
    relative = path.relative_to(meshes_root).as_posix()
    suffix = ".skeleton.lua" if relative.endswith(".skeleton.lua") else ".skeleton"
    return relative[:-len(suffix)].replace("/", "\\")


def _same_bind_pose(left, right):
    if len(left.bones) != len(right.bones):
        return False
    for a, b in zip(left.bones, right.bones):
        if a.name != b.name or a.parent != b.parent:
            return False
        if any(abs(x - y) > 1e-3 for x, y in zip(a.t, b.t)):
            return False
        if min(max(abs(x - y) for x, y in zip(a.q, b.q)),
               max(abs(x + y) for x, y in zip(a.q, b.q))) > 1e-3:
            return False
    return True


def _matching_skeletons(meshes, crc):
    matches = []
    for path in meshes.rglob("*.skeleton.lua"):
        data = path.read_bytes()
        match = re.search(rb'\bcrc\s*=\s*"?(\d+)"?', data)
        if match and int(match.group(1)) == crc:
            skeleton = lua.read_skeleton_lua(data.decode("utf-8", "surrogateescape"))
            matches.append((path, skeleton, None))
    for path in meshes.rglob("*.skeleton"):
        data = path.read_bytes()
        try:
            skeleton = binary.read_skeleton(data)
        except binary.FormatError:
            continue
        if skeleton.crc == crc:
            matches.append((path, skeleton, data))
    return matches


def _skeleton_key_for_motion(context, source_path, crc):
    """Resolve a motion by the directories declared in skeleton archives."""
    root = _content_root(context, source_path)
    if root is None:
        return None
    motions = root / "motions"
    source = Path(source_path)
    meshes = root / "meshes"
    if not source.is_relative_to(motions) or not meshes.is_dir():
        return None
    directory = source.parent.relative_to(motions).as_posix().replace("/", "\\").lower()
    cache_key = (str(meshes).lower(), crc, directory)
    if cache_key in _motion_skeleton_keys:
        return _motion_skeleton_keys[cache_key]
    matches = [(path, skeleton) for path, skeleton, _data in
               _matching_skeletons(meshes, crc)
               if directory in (entry.strip().replace("/", "\\").lower()
                                for entry in skeleton.motions.split(","))]
    if not matches:
        return None
    if any(not _same_bind_pose(matches[0][1], candidate)
           for _path, candidate in matches[1:]):
        raise binary.FormatError(
            "Several skeletons declare motion directory %r with different bind poses" % directory)
    key = _key_for_path(matches[0][0], meshes)
    _motion_skeleton_keys[cache_key] = key
    return key


def _load_matching_skeleton(context, source_path, crc, preferred_key=None):
    addon = context.preferences.addons.get("io_scene_redux")
    if addon and not addon.preferences.auto_skeleton:
        return None
    root = _content_root(context, source_path)
    meshes = root / "meshes" if root else None
    if not meshes or not meshes.is_dir():
        return None
    if preferred_key:
        stem = meshes.joinpath(*preferred_key.split("\\"))
        for suffix in (".skeleton.lua", ".skeleton"):
            path = Path(str(stem) + suffix)
            if path.is_file():
                data = path.read_bytes()
                skeleton = (lua.read_skeleton_lua(data.decode("utf-8", "surrogateescape"))
                            if suffix == ".skeleton.lua" else binary.read_skeleton(data))
                if skeleton.crc != crc:
                    raise binary.FormatError("Companion .model skeleton CRC does not match .mesh")
                return _create_armature(context, path.stem, skeleton,
                                        None if suffix == ".skeleton.lua" else data,
                                        preferred_key)
        raise binary.FormatError("Companion .model skeleton %r was not found" % preferred_key)
    matches = _matching_skeletons(meshes, crc)
    if not matches:
        return None
    if any(not _same_bind_pose(matches[0][1], candidate[1])
           for candidate in matches[1:]):
        raise binary.FormatError(
            "Several skeletons share CRC %08X but have different bind poses; import the matching .model or skeleton first" % crc)
    path, skeleton, data = matches[0]
    return _create_armature(context, path.stem, skeleton, data,
                            _key_for_path(path, meshes))


def import_path(context, path):
    data = Path(path).read_bytes()
    if str(path).lower().endswith(".skeleton.lua"):
        skeleton = lua.read_skeleton_lua(data.decode("utf-8", "surrogateescape"))
        source_data = None
    elif str(path).lower().endswith(".skeleton"):
        skeleton = binary.read_skeleton(data)
        source_data = data
    else:
        raise binary.FormatError("Expected .skeleton or .skeleton.lua")
    root = _content_root(context, path)
    meshes = root / "meshes" if root else None
    source_key = (_key_for_path(Path(path), meshes)
                  if meshes and Path(path).is_relative_to(meshes) else None)
    _create_armature(context, Path(path).name, skeleton, source_data, source_key)
    return 1

