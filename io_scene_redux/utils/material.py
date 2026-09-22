import bpy


def find_material(record, flags_schema=None):
    for material in bpy.data.materials:
        if (material.get("redux_texture") == record.texture and
                material.get("redux_shader") == record.shader and
                material.get("redux_game_material") == record.game_material and
                material.get("redux_part_name") == record.name and
                material.get("redux_flags") == record.flags and
                material.get("redux_lmd") == record.lmd and
                material.get("redux_flags_schema") == flags_schema):
            return material
    return None
