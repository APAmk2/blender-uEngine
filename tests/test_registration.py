"""Smoke-test add-on registration without a Blender installation."""

import sys
import types
import unittest
from unittest.mock import patch
from pathlib import Path


class RegistrationTests(unittest.TestCase):
    def test_register_and_unregister(self):
        bpy = types.ModuleType("bpy")
        bpy.types = types.SimpleNamespace(
            Operator=type("Operator", (), {}),
            Panel=type("Panel", (), {}),
            Material=type("Material", (), {}),
            Menu=type("Menu", (), {}),
            AddonPreferences=type("AddonPreferences", (), {}),
            OperatorFileListElement=type("OperatorFileListElement", (), {}),
            TOPBAR_MT_file_import=[],
            TOPBAR_MT_file_export=[],
        )
        registered = []
        loaded_icons = []
        removed_icons = []

        class Preview(dict):
            def load(self, name, path, _kind):
                loaded_icons.append((name, path))
                self[name] = types.SimpleNamespace(icon_id=42, icon_pixels=b"pixels")

        utils = types.ModuleType("bpy.utils")
        utils.register_class = registered.append
        utils.unregister_class = registered.remove
        utils.previews = types.SimpleNamespace(
            new=Preview,
            remove=removed_icons.append,
        )
        bpy.utils = utils
        bpy.path = types.SimpleNamespace(abspath=lambda path: path)
        props = types.ModuleType("bpy.props")
        for name in ("BoolProperty", "CollectionProperty", "EnumProperty", "IntProperty",
                     "StringProperty"):
            setattr(props, name, lambda **_kwargs: None)
        extras = types.ModuleType("bpy_extras")
        io_utils = types.ModuleType("bpy_extras.io_utils")
        io_utils.ImportHelper = type("ImportHelper", (), {})
        io_utils.ExportHelper = type("ExportHelper", (), {})
        extras.io_utils = io_utils
        mathutils = types.ModuleType("mathutils")
        for name in ("Matrix", "Quaternion", "Vector"):
            setattr(mathutils, name, type(name, (), {}))

        mocks = {"bpy": bpy, "bpy.utils": utils, "bpy.props": props, "bpy_extras": extras,
                 "bpy_extras.io_utils": io_utils, "mathutils": mathutils}
        with patch.dict(sys.modules, mocks):
            import io_scene_redux
            io_scene_redux.register()
            from io_scene_redux import icons
            self.assertEqual(icons.metro_icon_id(), 42)
            self.assertEqual(loaded_icons[0][0], "metro")
            for mask in (0x0001, 0x0002, 0x0004, 0x0008,
                         0x0010, 0x0020, 0x0040, 0x0100):
                self.assertTrue(hasattr(bpy.types.Material, "redux_flag_%04x" % mask))
            self.assertFalse(hasattr(bpy.types.Material, "redux_flag_0080"))
            self.assertFalse(hasattr(bpy.types.Material, "redux_flag_8000"))
            self.assertEqual(len(registered), 21)
            self.assertEqual(len(bpy.types.TOPBAR_MT_file_import), 5)
            self.assertEqual(len(bpy.types.TOPBAR_MT_file_export), 4)
            from io_scene_redux.panels.material import REDUX_OT_dynamic_menu
            selector = REDUX_OT_dynamic_menu()
            selector.prop = "redux_shader"
            selector.value = "geometry\\default"
            selector_context = types.SimpleNamespace()
            target = {}
            setattr(selector_context, "redux.dynamic_menu.data", target)
            self.assertEqual(selector.execute(selector_context), {"FINISHED"})
            self.assertEqual(target["redux_shader"], "geometry\\default")
            content = Path(r"D:\Soft\ReduxSDK\content")
            if content.exists():
                from io_scene_redux.formats.skeleton import imp as skeleton_imp
                mesh_path = (content / "meshes/dynamic/human/mp_characters/"
                             "soldier/chr_soldier_ataches_radio.mesh")
                model_path, skeleton_key = skeleton_imp._skeleton_from_prefix_model(mesh_path)
                self.assertEqual(model_path.name, "chr_soldier_ataches.model")
                self.assertEqual(skeleton_key, "dynamic\\human\\human")
                resolution_context = types.SimpleNamespace(
                    preferences=types.SimpleNamespace(addons={}),
                    active_object=None,
                    scene=types.SimpleNamespace(objects=[]))
                with self.assertRaisesRegex(
                        Exception, r"Import companion \.model first: .*chr_soldier_ataches\.model"):
                    skeleton_imp._skeleton_key_for_mesh(
                        resolution_context, mesh_path, 0x942B7D90)
            io_scene_redux.unregister()
            self.assertEqual(len(removed_icons), 1)
            self.assertEqual(registered, [])
            self.assertEqual(bpy.types.TOPBAR_MT_file_import, [])
            self.assertEqual(bpy.types.TOPBAR_MT_file_export, [])


if __name__ == "__main__":
    unittest.main()
