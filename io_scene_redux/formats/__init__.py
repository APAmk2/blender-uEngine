from .static import ops as static_ops
from .mesh import ops as mesh_ops
from .skeleton import ops as skeleton_ops
from .m2 import ops as motion_ops
from .model import ops as model_ops

MODULES = (static_ops, mesh_ops, skeleton_ops, motion_ops, model_ops)


def register():
    for module in MODULES:
        module.register()


def unregister():
    for module in reversed(MODULES):
        module.unregister()
