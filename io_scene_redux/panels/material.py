import bpy
from bpy.props import BoolProperty, StringProperty

from .. import icons
from ..utils import asset_lists


_STATIC_FLAG_LABELS = {
    0x0001: "Lightmap (static)",
    0x0002: "No Collision (static)",
    0x0004: "Wallmark (static)",
    0x0008: "No Rendering (static)",
    0x0010: "Portal Non Walkable (static)",
    0x0020: "No Shadows (static)",
    0x0040: "Local AO (static)",
    0x0100: "Transparent (static)",
}
_STATIC_FLAG_BITS = tuple(_STATIC_FLAG_LABELS)
_STATIC_FLAG_MASK = sum(_STATIC_FLAG_BITS)
_MENU_TREES = {}


def _content_root(context):
    if context is None:
        return None
    addon = context.preferences.addons.get("io_scene_redux")
    if addon is None or not addon.preferences.content_root:
        return None
    return bpy.path.abspath(addon.preferences.content_root)


def _names(context, field):
    root = _content_root(context)
    if not root:
        return ()
    return (asset_lists.shader_names(root) if field == "redux_shader" else
            asset_lists.material_names(root))


def _menu_tree(names):
    cached = _MENU_TREES.get(names)
    if cached is not None:
        return cached

    root = {}
    for name in names:
        branch = root
        parts = name.split("\\")
        for part in parts[:-1]:
            branch = branch.setdefault(part, {})
        branch[parts[-1]] = (name, "")

    def to_items(branch):
        submenus = []
        values = []
        for label, value in branch.items():
            if isinstance(value, dict):
                submenus.append((label, to_items(value)))
            else:
                values.append((label, value))
        return sorted(submenus, key=lambda item: item[0].casefold()) + \
            sorted(values, key=lambda item: item[0].casefold())

    result = to_items(root)
    _MENU_TREES[names] = result
    return result


class REDUX_OT_dynamic_menu(bpy.types.Operator):
    bl_idname = "redux.dynamic_menu"
    bl_label = ""
    bl_description = "Set the selected Redux value"

    prop: StringProperty()
    value: StringProperty()
    desc: StringProperty()

    @classmethod
    def description(cls, _context, properties):
        return getattr(properties, "desc", "")

    def execute(self, context):
        data = getattr(context, REDUX_OT_dynamic_menu.bl_idname + ".data")
        data[self.prop] = self.value
        return {"FINISHED"}


def _path_prefix(path):
    return REDUX_OT_dynamic_menu.bl_idname + ".idx." + ".".join(map(str, path))


def _current_menu_path(context):
    result = []
    for _ in range(20):
        for index in range(100):
            if getattr(context, _path_prefix(result + [index]), None) is None:
                if index:
                    result.append(index - 1)
                break
    return result


class REDUX_MT_dynamic_menu(bpy.types.Menu):
    bl_label = ""
    prop_name = ""
    source_field = ""

    @classmethod
    def items_for_path(cls, path):
        data = _menu_tree(_names(bpy.context, cls.source_field))
        for index in path:
            data = data[index][1]
        return data

    def draw(self, context):
        layout = self.layout
        path = _current_menu_path(context)
        if path:
            next_sibling = path[:-1] + [path[-1] + 1]
            layout.context_pointer_set(_path_prefix(next_sibling), None)

        items = self.items_for_path(path)
        for index, (label, data) in enumerate(items):
            prefix = _path_prefix(path + [index])
            layout.context_pointer_set(prefix, context)
            if isinstance(data, list):
                layout.menu(self.bl_idname, text=label)
            else:
                value, desc = data
                operator = layout.operator(REDUX_OT_dynamic_menu.bl_idname, text=label)
                operator.prop = self.prop_name
                operator.value = value
                operator.desc = desc

        layout.context_pointer_set(_path_prefix(path + [len(items)]), None)

    @staticmethod
    def set_layout_data(layout, data):
        layout.context_pointer_set(REDUX_OT_dynamic_menu.bl_idname + ".data", data)


class REDUX_MT_shader(REDUX_MT_dynamic_menu):
    bl_idname = "REDUX_MT_shader"
    prop_name = "redux_shader"
    source_field = "redux_shader"


class REDUX_MT_game_material(REDUX_MT_dynamic_menu):
    bl_idname = "REDUX_MT_game_material"
    prop_name = "redux_game_material"
    source_field = "redux_game_material"


def _flag_name(mask):
    return "redux_flag_%04x" % mask


def _flag_property(mask):
    def get(material):
        return bool(int(material.get("redux_flags", 0)) & mask)

    def set(material, enabled):
        flags = int(material.get("redux_flags", 0))
        material["redux_flags"] = flags | mask if enabled else flags & ~mask

    return BoolProperty(name=_STATIC_FLAG_LABELS[mask],
                        get=get, set=set)


class REDUX_PT_material(bpy.types.Panel):
    bl_label = "Redux SDK Material"
    bl_idname = "REDUX_PT_material"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"

    def draw_header(self, _context):
        self.layout.label(icon_value=icons.metro_icon_id())

    @classmethod
    def poll(cls, context):
        return context.material is not None and "redux_shader" in context.material

    def draw(self, context):
        layout = self.layout
        material = context.material
        for key, label in (("redux_part_name", "Part"),
                           ("redux_texture", "Texture")):
            if key in material:
                layout.prop(material, '["%s"]' % key, text=label)
        for key, label in (("redux_shader", "Shader"),
                           ("redux_game_material", "Game material")):
            if key in material:
                if _names(context, key):
                    row = layout.row(align=True)
                    row.prop(material, '["%s"]' % key, text=label)
                    REDUX_MT_dynamic_menu.set_layout_data(row, material)
                    menu = (REDUX_MT_shader.bl_idname if key == "redux_shader" else
                            REDUX_MT_game_material.bl_idname)
                    row.menu(menu, text="", icon="TRIA_DOWN")
                else:
                    layout.prop(material, '["%s"]' % key, text=label)
        if "redux_lmd" in material:
            layout.prop(material, '["redux_lmd"]', text="Lightmap density")
        if "redux_flags" in material:
            box = layout.box()
            if material.get("redux_flags_schema") == "static_part":
                box.label(text="Static part flags")
                grid = box.grid_flow(columns=2, even_columns=True, align=True)
                for mask in _STATIC_FLAG_BITS:
                    grid.prop(material, _flag_name(mask))
                unknown = int(material["redux_flags"]) & ~_STATIC_FLAG_MASK
                if unknown:
                    box.label(text="Unknown bits: 0x%X" % unknown, icon="INFO")
            else:
                box.prop(material, '["redux_flags"]', text="Flags")
        if "redux_texture_file" in material:
            layout.label(text="Source: " + material["redux_texture_file"])
        elif "redux_texture_status" in material:
            layout.label(text="Texture: " + material["redux_texture_status"], icon="INFO")


def register():
    for mask in _STATIC_FLAG_BITS:
        setattr(bpy.types.Material, _flag_name(mask), _flag_property(mask))
    for cls in (REDUX_OT_dynamic_menu, REDUX_MT_shader,
                REDUX_MT_game_material, REDUX_PT_material):
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed((REDUX_OT_dynamic_menu, REDUX_MT_shader,
                         REDUX_MT_game_material, REDUX_PT_material)):
        bpy.utils.unregister_class(cls)
    for mask in _STATIC_FLAG_BITS:
        delattr(bpy.types.Material, _flag_name(mask))
    _MENU_TREES.clear()
