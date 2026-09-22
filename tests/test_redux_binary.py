"""Regression checks against documented SDK samples; no Blender installation needed."""

import unittest
from pathlib import Path

from io_scene_redux.rw import (archive, common as binary, model as redux_model,
                               static, mesh, skeleton, lua_redux as lua, motion)


ROOT = Path(__file__).resolve().parents[2]
CONTENT = Path(r"D:\Soft\ReduxSDK\content")


class FormatTests(unittest.TestCase):
    @unittest.skipUnless(CONTENT.exists(), "Redux SDK content is not installed")
    def test_version_8_static_round_trip(self):
        path = CONTENT / "maps/2033/l01_hunter/source/sec2.static"
        source = path.read_bytes()
        model = static.read_static(source)
        self.assertEqual(model.header[0], 8)
        self.assertEqual(len(model.parts), 12)
        self.assertEqual(sum(len(part.vertices) for part in model.parts), 18548)
        self.assertEqual(sum(len(part.faces) for part in model.parts), 16745)
        self.assertEqual(static.write_static(model), source)

    @unittest.skipUnless(CONTENT.exists(), "Redux SDK content is not installed")
    def test_model_variants(self):
        static_path = CONTENT / "meshes/static/station_props/med/taz.model"
        static_model = redux_model.read_model(static_path.read_bytes())
        self.assertEqual((static_model.version, static_model.model_type), (22, 1))
        self.assertEqual(len(static.read_static(static_path.read_bytes(), expected_type=1).parts), 2)

        assembly_path = (CONTENT / "meshes/dynamic/human/story_characters/"
                         "chr_miller_sparta/chr_miller_sparta.model")
        assembly = redux_model.read_model(assembly_path.read_bytes())
        self.assertEqual(assembly.skeleton_key, "dynamic\\human\\human")
        self.assertEqual(len(assembly.lods), 3)
        self.assertIn("dynamic\\human\\story_characters\\chr_miller_sparta\\"
                      "chr_miller_sparta_body", assembly.lods[0])

        embedded_path = CONTENT / "meshes/dynamic/hud/weapon/planshet/planshet.model"
        embedded = redux_model.read_model(embedded_path.read_bytes())
        embedded_skeleton = archive.read_skeleton(embedded.embedded_skeleton)
        embedded_mesh = mesh.read_mesh(embedded.embedded_mesh)
        self.assertEqual(embedded.version, 23)
        self.assertEqual(len(embedded_skeleton.bones), 2)
        self.assertEqual(embedded_skeleton.crc, embedded_mesh.bones_crc)
        self.assertEqual(len(embedded_mesh.parts), 5)

    def test_static_round_trip(self):
        for path in ROOT.glob("*.static"):
            with self.subTest(path=path.name):
                source = path.read_bytes()
                model = static.read_static(source)
                self.assertTrue(model.parts)
                self.assertEqual(static.write_static(model), source)

    @unittest.skipUnless(CONTENT.exists(), "Redux SDK content is not installed")
    def test_version_18_static_round_trip(self):
        path = CONTENT / "maps/2034/l04_plane/source/scene_metro.static"
        source = path.read_bytes()
        model = static.read_static(source)
        self.assertEqual(model.header[0], 18)
        self.assertEqual(model.guid, b"")
        self.assertEqual((len(model.parts), len(model.parts[0].vertices),
                          len(model.parts[0].faces)), (1, 24, 12))
        self.assertEqual(len(model.parts[0].vertex_basis), 24)
        self.assertEqual(static.write_static(model), source)

    @unittest.skipUnless(CONTENT.exists(), "Redux SDK content is not installed")
    def test_version_16_static_round_trip(self):
        path = CONTENT / "maps/2034/l04_plane/source/mcd_1stfloor/mcd_basement.static"
        source = path.read_bytes()
        model = static.read_static(source)
        self.assertEqual(model.header[0], 16)
        self.assertEqual(model.guid, b"")
        self.assertEqual(len(model.parts), 8)
        self.assertEqual((len(model.parts[0].vertices), len(model.parts[0].faces)),
                         (43, 41))
        self.assertEqual(len(model.parts[0].vertex_basis), 43)
        self.assertEqual(static.write_static(model), source)

    @unittest.skipUnless(CONTENT.exists(), "Redux SDK content is not installed")
    def test_version_21_static_round_trip(self):
        path = CONTENT / "maps/2034/l17_red_square/source/sec_03.static"
        source = path.read_bytes()
        model = static.read_static(source)
        self.assertEqual(model.header[0], 21)
        self.assertEqual(len(model.guid), 16)
        self.assertEqual(len(model.parts[0].vertex_basis), len(model.parts[0].vertices))
        self.assertEqual(static.write_static(model), source)

    def test_mesh_round_trip(self):
        for path in ROOT.glob("*.mesh"):
            with self.subTest(path=path.name):
                source = path.read_bytes()
                model = mesh.read_mesh(source)
                self.assertEqual(model.bones_crc, 0x942B7D90)
                self.assertEqual(mesh.write_mesh(model), source)

    @unittest.skipUnless(CONTENT.exists(), "Redux SDK content is not installed")
    def test_hud_skin_weight_byte_order(self):
        path = CONTENT / "meshes/dynamic/hud/34_hand_stalker/hud_stalker.mesh"
        part = mesh.read_mesh(path.read_bytes()).parts[0]
        first = part.vertices[0]
        self.assertEqual(first.offset[3], 1)
        self.assertEqual(first.influences(part.used_bones), [(42, 1.0)])
        for vertex in part.vertices:
            self.assertAlmostEqual(sum(weight for _bone, weight in
                                       vertex.influences(part.used_bones)), 1.0, places=5)

    @unittest.skipUnless(CONTENT.exists(), "Redux SDK content is not installed")
    def test_version_21_hud_mesh_round_trip(self):
        path = CONTENT / "meshes/dynamic/hud/34_hand/hud.mesh"
        source = path.read_bytes()
        model = mesh.read_mesh(source)
        self.assertEqual(model.header[0], 21)
        self.assertEqual(len(model.parts), 2)
        self.assertEqual([part.header[0] for part in model.parts], [21, 21])
        self.assertEqual(mesh.write_mesh(model), source)

    @unittest.skipUnless(CONTENT.exists(), "Redux SDK content is not installed")
    def test_legacy_mesh_round_trip(self):
        paths = (
            "motions/object/reshetka_02/idle_open.mesh",
            "motions/object/tunnel_props/tupik_02_part1_1x1m/"
            "tupik_01_part1_1x1m_crash_back.mesh",
            "meshes/dynamic/human/mp_characters/soldier/"
            "chr_soldier_ataches_radio.mesh",
        )
        for expected, relative in zip((7, 9, 14), paths):
            with self.subTest(version=expected):
                source = (CONTENT / relative).read_bytes()
                model = mesh.read_mesh(source)
                self.assertEqual(model.header[0], expected)
                self.assertTrue(model.parts)
                self.assertEqual(mesh.write_mesh(model), source)

    @unittest.skipUnless(CONTENT.exists(), "Redux SDK content is not installed")
    def test_empty_mesh_placeholder_round_trip(self):
        path = CONTENT / "meshes/dynamic/objects/box/dummy_01.mesh"
        source = path.read_bytes()
        model = mesh.read_mesh(source)
        self.assertEqual(model.header[:2], bytes((16, 0)))
        self.assertEqual(model.parts, [])
        self.assertEqual(mesh.write_mesh(model), source)

    @unittest.skipUnless(CONTENT.exists(), "Redux SDK content is not installed")
    def test_legacy_static_model_versions(self):
        paths = (
            (20, "maps/2034/l03_camp_2/meshes/$edit_geom.model"),
            (17, "maps/2034/l14_bridge/meshes/$edit_geom.model"),
            (7, "meshes/dynamic/objects/vdnh_kran/.model"),
        )
        for expected, relative in paths:
            with self.subTest(version=expected):
                source = (CONTENT / relative).read_bytes()
                descriptor = redux_model.read_model(source)
                geometry = static.read_static(source, expected_type=1)
                self.assertEqual((descriptor.version, descriptor.model_type),
                                 (expected, 1))
                self.assertTrue(geometry.parts)

    @unittest.skipUnless(CONTENT.exists(), "Redux SDK content is not installed")
    def test_multiple_embedded_model_meshes(self):
        path = CONTENT / "meshes/dynamic/hud/weapon/att/abzac_autofire.model"
        descriptor = redux_model.read_model(path.read_bytes())
        self.assertEqual([len(value) for value in descriptor.embedded_lods], [1, 1, 0])
        self.assertEqual(len(descriptor.embedded_meshes), 1)
        self.assertEqual([len(mesh.read_mesh(value).parts)
                          for value in descriptor.embedded_meshes], [2])

    @unittest.skipUnless(CONTENT.exists(), "Redux SDK content is not installed")
    def test_embedded_skeleton_named_array_records(self):
        path = CONTENT / "meshes/dynamic/objects/cars/car_or_01.model"
        descriptor = redux_model.read_model(path.read_bytes())
        embedded = archive.read_skeleton(descriptor.embedded_skeleton)
        self.assertEqual(len(embedded.bones), 7)

    @unittest.skipUnless(CONTENT.exists(), "Redux SDK content is not installed")
    def test_embedded_skeleton_choice_fields(self):
        path = CONTENT / "meshes/dynamic/monsters/dark/dark.model"
        descriptor = redux_model.read_model(path.read_bytes())
        embedded = archive.read_skeleton(descriptor.embedded_skeleton)
        self.assertTrue(embedded.bones)

    @unittest.skipUnless(CONTENT.exists(), "Redux SDK content is not installed")
    def test_compact_skeleton_round_trip(self):
        for path in CONTENT.rglob("*.skeleton"):
            # Windows globbing is case insensitive; FaceFX uses uppercase .SKELETON.
            if path.suffix != ".skeleton":
                continue
            with self.subTest(path=path.name):
                source = path.read_bytes()
                model = skeleton.read_skeleton(source)
                if model.version == 4:
                    self.assertEqual(skeleton.write_skeleton(model), source)

    @unittest.skipUnless(CONTENT.exists(), "Redux SDK content is not installed")
    def test_human_lua_skeleton(self):
        path = CONTENT / "meshes/dynamic/human/human.skeleton.lua"
        skeleton = lua.read_skeleton_lua(path.read_text(encoding="utf-8"))
        self.assertEqual(len(skeleton.bones), 113)
        self.assertEqual(skeleton.crc, 0x942B7D90)
        self.assertEqual(len(skeleton.partitions), 10)
        self.assertEqual(len(skeleton.params), 87)

    def test_truncated_chunks_rejected(self):
        source = (ROOT / "actor_body.mesh").read_bytes()
        with self.assertRaises(binary.FormatError):
            mesh.read_mesh(source[:-1])

    @unittest.skipUnless(CONTENT.exists(), "Redux SDK content is not installed")
    def test_compiled_motion_curves(self):
        path = CONTENT / "motions/human/ai/alert_gun_attack_0.m2"
        clip = motion.read_m2(path.read_bytes())
        self.assertEqual(clip.bones_crc, 0x942B7D90)
        self.assertEqual(clip.bones_count, 113)
        self.assertEqual(clip.frame_total, 20)
        self.assertEqual(len(clip.animated_bones), 95)
        rotation = clip.bone_curves[0][0].sample(0.3)
        self.assertAlmostEqual(sum(value * value for value in rotation), 1.0, places=3)


if __name__ == "__main__":
    unittest.main()
