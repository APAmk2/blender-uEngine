import os
from .formats_io import FormatError


def ensure_object_mode(context):
    if context.mode != "OBJECT" and context.active_object:
        import bpy
        bpy.ops.object.mode_set(mode="OBJECT")


def run_import(operator, context, import_path):
    try:
        paths = selected_import_paths(operator)
    except (FormatError, OSError, ValueError, KeyError) as exc:
        operator.report({"ERROR"}, str(exc))
        return {"CANCELLED"}
    imported = 0
    failed = []
    for path in paths:
        try:
            imported += import_path(context, path)
        except (FormatError, OSError, ValueError, KeyError) as exc:
            failed.append((os.path.basename(path), str(exc)))
    all_failed = len(failed) == len(paths)
    for name, error in failed[:5]:
        operator.report({"ERROR"} if all_failed else {"WARNING"},
                        "%s: %s" % (name, error))
    if failed:
        operator.report({"ERROR"} if all_failed else {"WARNING"},
                        "Imported %d object(s) from %d file(s); %d failed%s" % (
            imported, len(paths) - len(failed), len(failed),
            " (first 5 shown)" if len(failed) > 5 else ""))
    else:
        operator.report({"INFO"}, "Imported %d Redux object(s) from %d file(s)" % (
            imported, len(paths)))
    return {"CANCELLED"} if all_failed else {"FINISHED"}


def selected_import_paths(operator):
    """Return the file browser selection, or the single direct filepath."""
    files = getattr(operator, "files", ())
    if files:
        directory = getattr(operator, "directory", "") or os.path.dirname(operator.filepath)
        paths = []
        for entry in files:
            if os.path.basename(entry.name) != entry.name:
                raise ValueError("Invalid selected file name %r" % entry.name)
            paths.append(os.path.join(directory, entry.name))
        return paths
    return [operator.filepath]


def run_export(operator, context, export_data, extension, **options):
    try:
        path = operator.filepath
        if not path.lower().endswith(extension):
            path = os.path.splitext(path)[0] + extension
        data = export_data(context, **options)
        with open(path, "wb") as stream:
            stream.write(data)
        operator.report({"INFO"}, "Wrote %s" % path)
        return {"FINISHED"}
    except (FormatError, OSError, ValueError, KeyError) as exc:
        operator.report({"ERROR"}, str(exc))
        return {"CANCELLED"}
