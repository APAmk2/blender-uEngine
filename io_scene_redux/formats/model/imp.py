from pathlib import Path

import bpy

from ...rw import archive, model as binary
from ...rw.common import FormatError
from ..common import _content_root
from ..mesh import imp as mesh_imp
from ..skeleton.imp import _create_armature
from ..static import imp as static_imp


def _resource_path(meshes, key, extension):
    parts = key.replace("/", "\\").split("\\")
    if not parts or any(part in ("", ".", "..") or ":" in part for part in parts):
        raise FormatError("Invalid .model resource key %r" % key)
    path = meshes.joinpath(*parts)
    if path.suffix.lower() != extension:
        path = Path(str(path) + extension)
    if not path.is_file():
        raise FormatError("Referenced resource %r was not found" % key)
    return path


def _model_key(path, meshes):
    source = Path(path).resolve()
    try:
        return source.relative_to(meshes.resolve()).with_suffix("").as_posix().replace("/", "\\")
    except ValueError:
        return source.stem


def _move_to_collection(context, path, objects, lod):
    collection = bpy.data.collections.new(Path(path).stem)
    context.collection.children.link(collection)
    collection["redux_format"] = "model"
    collection["redux_model_source"] = str(path)
    collection["redux_model_lod"] = lod
    for obj in objects:
        for owner in tuple(obj.users_collection):
            owner.objects.unlink(obj)
        collection.objects.link(obj)
        obj["redux_model_source"] = str(path)
        obj["redux_model_lod"] = lod
    return collection


def import_path(context, path, lod=0):
    data = Path(path).read_bytes()
    descriptor = binary.read_model(data)
    before = set(bpy.data.objects)
    if descriptor.model_type == 1:
        static_imp.import_data(context, path, data, expected_type=1,
                               source_name=Path(path).name)
    else:
        root = _content_root(context, path)
        meshes = root / "meshes" if root else None
        if meshes is None or not meshes.is_dir():
            raise FormatError("Set SDK content directory to import a dynamic .model")
        skeleton_key = descriptor.skeleton_key or None
        if descriptor.embedded_skeleton:
            skeleton = archive.read_skeleton(descriptor.embedded_skeleton)
            skeleton_key = _model_key(path, meshes) + "#embedded"
            _create_armature(context, Path(path).stem + ".skeleton", skeleton,
                             source_key=skeleton_key)
        if descriptor.embedded_lods:
            if lod >= len(descriptor.embedded_lods) or not descriptor.embedded_lods[lod]:
                raise FormatError(".model has no embedded geometry for LOD %d" % lod)
            embedded_meshes = descriptor.embedded_lods[lod]
            for index, embedded_mesh in enumerate(embedded_meshes):
                suffix = (".embedded.mesh" if len(embedded_meshes) == 1
                          else ".embedded.%02d.mesh" % index)
                mesh_imp.import_data(context, path, embedded_mesh,
                                     skeleton_key, Path(path).stem + suffix)
        elif descriptor.lods:
            if lod >= len(descriptor.lods) or not descriptor.lods[lod]:
                raise FormatError(".model has no mesh resources for LOD %d" % lod)
            for key in descriptor.lods[lod]:
                mesh_path = _resource_path(meshes, key, ".mesh")
                mesh_imp.import_path(context, str(mesh_path), skeleton_key)
        else:
            raise FormatError("Dynamic .model has no embedded or referenced mesh geometry")
    created = set(bpy.data.objects) - before
    if not created:
        raise FormatError(".model import created no objects")
    _move_to_collection(context, path, created, lod)
    return len(created)
