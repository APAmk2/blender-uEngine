"""Audit every Redux file the Blender add-on advertises under an SDK content tree."""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import sys


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from io_scene_redux.rw import (archive, lua_redux, mesh, model, motion,
                               skeleton, static)


def _kind(path):
    lower = path.lower()
    if lower.endswith(".skeleton.lua"):
        return "skeleton.lua"
    if Path(lower).name in (".static", ".mesh", ".model", ".skeleton", ".m2"):
        return Path(lower).name[1:]
    return Path(lower).suffix.lstrip(".")


def _audit_path(arguments):
    path_text, content_text = arguments
    path = Path(path_text)
    content = Path(content_text)
    kind = _kind(path_text)
    try:
        data = path.read_bytes()
        if kind == "static":
            static.read_static(data)
        elif kind == "mesh":
            mesh.read_mesh(data)
        elif kind == "model":
            descriptor = model.read_model(data)
            if descriptor.model_type == 1:
                static.read_static(data, expected_type=1)
            for embedded_lod in descriptor.embedded_lods:
                for embedded_mesh in embedded_lod:
                    mesh.read_mesh(embedded_mesh)
            if descriptor.embedded_skeleton:
                archive.read_skeleton(descriptor.embedded_skeleton)
            if descriptor.lods and descriptor.lods[0]:
                meshes = content / "meshes"
                for key in descriptor.lods[0]:
                    resource = meshes.joinpath(*key.replace("/", "\\").split("\\"))
                    if resource.suffix.lower() != ".mesh":
                        resource = Path(str(resource) + ".mesh")
                    if not resource.is_file():
                        raise FileNotFoundError("LOD 0 mesh resource was not found: %s" % key)
        elif kind == "skeleton":
            skeleton.read_skeleton(data)
        elif kind == "skeleton.lua":
            lua_redux.read_skeleton_lua(data.decode("utf-8", "surrogateescape"))
        elif kind == "m2":
            motion.read_m2(data)
        return kind, path_text, ""
    except Exception as exc:  # Audit must retain every independent failure.
        return kind, path_text, "%s: %s" % (type(exc).__name__, exc)


def _paths(content):
    extensions = (".static", ".mesh", ".model", ".skeleton", ".m2")
    result = []
    for path in content.rglob("*"):
        lower = path.name.lower()
        if path.is_file() and (lower.endswith(extensions) or
                               lower.endswith(".skeleton.lua")):
            result.append(path)
    return sorted(result, key=lambda value: str(value).casefold())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("content", type=Path)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    content = args.content.resolve()
    paths = _paths(content)
    counts = Counter()
    failures = []
    work = ((str(path), str(content)) for path in paths)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for index, (kind, path, error) in enumerate(
                pool.map(_audit_path, work, chunksize=32), 1):
            counts[kind] += 1
            if error:
                failures.append({"format": kind,
                                 "path": str(Path(path).relative_to(content)),
                                 "error": error})
            if index % 1000 == 0 or index == len(paths):
                print("%d/%d files; %d failure(s)" %
                      (index, len(paths), len(failures)), flush=True)
    errors = Counter(item["error"] for item in failures)
    report = {
        "content": str(content),
        "counts": dict(sorted(counts.items())),
        "files": len(paths),
        "failures": failures,
        "failure_counts": dict(errors.most_common()),
    }
    output = args.output or REPO.parent / "CONTENT_AUDIT.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Report: %s" % output)
    print("Counts: %s" % dict(sorted(counts.items())))
    print("Failures: %d" % len(failures))
    for error, count in errors.most_common(20):
        print("%6d  %s" % (count, error))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
