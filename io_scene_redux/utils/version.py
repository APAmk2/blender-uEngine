import bpy


def get_import_export_menus():
    return bpy.types.TOPBAR_MT_file_import, bpy.types.TOPBAR_MT_file_export


def link_object(obj, context=None):
    (context or bpy.context).collection.objects.link(obj)


def set_active_object(obj, context=None):
    (context or bpy.context).view_layer.objects.active = obj


def select_object(obj, selected=True):
    obj.select_set(selected)


def set_action_slot(obj, action):
    # Blender 4.4+ introduced layered Action slots.
    if bpy.app.version >= (4, 4, 0) and getattr(action, "slots", None):
        obj.animation_data.action_slot = action.slots[0]
