"""Tests for Redux SDK shader and game-material list parsing."""

from pathlib import Path
import tempfile
import unittest

from io_scene_redux.utils import asset_lists


CONTENT = Path(r"D:\Soft\ReduxSDK\content")


class AssetListTests(unittest.TestCase):
    def test_nested_material_sections_are_not_choices(self):
        source = '''materials = create_section {
    ["default"] = create_section {
        name = "default",
        nested = create_section { ["wrong"] = 1 },
    },
    ["materials\\\\metal"] = create_section {},
}
'''
        self.assertEqual(asset_lists._table_keys(source, "materials"),
                         ["default", "materials\\metal"])

    def test_sdk_databases(self):
        if not CONTENT.is_dir():
            self.skipTest("Redux SDK content is unavailable")
        shaders = asset_lists.shader_names(CONTENT)
        materials = asset_lists.material_names(CONTENT)
        self.assertIn("geometry\\default", shaders)
        self.assertIn("geometry\\fresnel", shaders)
        self.assertIn("default", materials)
        self.assertIn("materials\\metal", materials)
        self.assertGreater(len(shaders), 200)
        self.assertGreater(len(materials), 50)
        self.assertLess(len(materials), 200)


if __name__ == "__main__":
    unittest.main()
