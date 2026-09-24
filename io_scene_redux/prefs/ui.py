
def draw(layout, prefs):
    layout.row().prop(prefs, "category", expand=True)
    column = layout.column(align=True)
    if prefs.category == "PATHS":
        column.prop(prefs, "target_sdk")
        column.prop(prefs, "content_root")
        column.prop(prefs, "auto_skeleton")
    elif prefs.category == "FORMATS":
        column.prop(prefs, "compact_menus")
        for name in ("static", "mesh", "skeleton", "m2", "model"):
            column.prop(prefs, "enable_%s_import" % name)
        for name in ("static", "mesh", "skeleton", "m2"):
            column.prop(prefs, "enable_%s_export" % name)
    else:
        column.prop(prefs, "load_textures")
