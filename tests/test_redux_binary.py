"""Regression checks against documented SDK samples; no Blender installation needed."""

import unittest
from pathlib import Path

from io_scene_redux.rw import (archive, common as binary, model as redux_model,
                               static, mesh, skeleton, lua_redux as lua, motion)


ROOT = Path(__file__).resolve().parents[2]
CONTENT = Path(r"D:\Soft\ReduxSDK\content")
M3_CONTENT = Path(r"D:\Archive\m3sdk\content")
M4_CONTENT = Path(r"D:\Archive\m4_2022\UNPACK\content")


class FormatTests(unittest.TestCase):
    @unittest.skipUnless(M3_CONTENT.exists(), "M3 SDK content is not installed")
    def test_m3_skin_versions_and_embedded_skeleton(self):
        paths = (
            "meshes/dynamic/hud/hand/exodus/base_glove/export/hud_base_glove_r.mesh",
            "meshes/dynamic/hud/weapon/wpn_base/wpn_kolya1911/"
            "kolya1911_mag_big.mesh",
        )
        versions = []
        for relative in paths:
            value = mesh.read_mesh((M3_CONTENT / relative).read_bytes())
            versions.append(value.header[0])
            self.assertTrue(value.parts)
            self.assertTrue(value.parts[0].vertices[0].influences(
                value.parts[0].used_bones))
        self.assertEqual(versions, [46, 48])

        path = (M3_CONTENT / "meshes/dynamic/hud/weapon/m3_dynamo_machine/"
                "m3_dynamo_machine.model")
        descriptor = redux_model.read_model(path.read_bytes())
        self.assertTrue(archive.read_skeleton(descriptor.embedded_skeleton).bones)

        dynamite_path = (M3_CONTENT / "meshes/dynamic/hud/weapon/m3_dynamite/"
                         "m3_dynamite.model")
        dynamite = redux_model.read_model(dynamite_path.read_bytes())
        dynamite_skeleton = archive.read_skeleton(dynamite.embedded_skeleton)
        self.assertEqual((len(dynamite_skeleton.bones),
                          len(dynamite_skeleton.partitions[0][1])), (1, 1))
        self.assertTrue(skeleton.write_skeleton(dynamite_skeleton))

    @unittest.skipUnless(M4_CONTENT.exists(), "M4 2022 content is not installed")
    def test_m4_2022_mesh_and_model(self):
        mesh_path = (M4_CONTENT / "meshes/characters/hud/outfit_default/"
                     "m4_player_default_outfit.mesh")
        skin = mesh.read_mesh(mesh_path.read_bytes())
        self.assertEqual(skin.header[0], 51)
        self.assertTrue(skin.parts[0].vertices[0].direct_bones)
        self.assertTrue(skin.parts[0].vertices[0].influences(
            skin.parts[0].used_bones))

        model_path = (M4_CONTENT / "meshes/characters/hud/armor/armor_medium/"
                      "body_armour_medium_b2b_test.model")
        descriptor = redux_model.read_model(model_path.read_bytes())
        self.assertEqual((descriptor.version, descriptor.model_type), (55, 3))
        embedded = mesh.read_mesh(descriptor.embedded_mesh,
                                  descriptor.raw_geometry)
        self.assertTrue(embedded.parts[0].faces)
        self.assertEqual(len(archive.read_skeleton(
            descriptor.embedded_skeleton).bones), 67)

        referenced_path = (M4_CONTENT / "meshes/characters/hud/_base/"
                           "m4_player.model")
        referenced = redux_model.read_model(referenced_path.read_bytes())
        self.assertEqual(referenced.lods[0],
                         [".\\test_body", ".\\test_boots", ".\\test_pants"])
        resolved = [redux_model.resource_path(M4_CONTENT / "meshes",
                                               referenced_path, key, ".mesh")
                    for key in referenced.lods[0]]
        self.assertEqual([path.name for path in resolved],
                         ["test_body.mesh", "test_boots.mesh", "test_pants.mesh"])
        referenced_skeleton = lua.read_skeleton_lua(
            referenced_path.with_suffix(".skeleton.lua").read_text(encoding="utf-8"))
        self.assertEqual(len(referenced_skeleton.bones), 67)
        self.assertTrue(all(len(mask) == 67
                            for _name, mask in referenced_skeleton.partitions))
        for path in resolved:
            skin = mesh.read_mesh(path.read_bytes())
            self.assertEqual(skin.bones_crc, referenced_skeleton.crc)

        recon_path = (M4_CONTENT / "meshes/characters/man/nazis/nazi_light/"
                      "nazi_light_recon.model")
        recon = redux_model.read_model(recon_path.read_bytes())
        jacket_path = redux_model.resource_path(
            M4_CONTENT / "meshes", recon_path, recon.lods[0][0], ".mesh")
        jacket = mesh.read_mesh(jacket_path.read_bytes())
        self.assertNotEqual(jacket.bones_crc, referenced_skeleton.crc)
        jacket_model = redux_model.read_model(
            jacket_path.with_suffix(".model").read_bytes())
        jacket_skeleton_path = (M4_CONTENT / "meshes").joinpath(
            *jacket_model.skeleton_key.split("\\"))
        jacket_skeleton = lua.read_skeleton_lua(
            Path(str(jacket_skeleton_path) + ".skeleton.lua").read_text(
                encoding="utf-8"))
        self.assertEqual(jacket.bones_crc, jacket_skeleton.crc)

    @unittest.skipUnless(M4_CONTENT.exists(), "M4 2022 content is not installed")
    def test_m4_2022_static_model(self):
        path = M4_CONTENT / "meshes/static/spec_test.model"
        descriptor = redux_model.read_model(path.read_bytes())
        geometry = static.read_static(path.read_bytes(), expected_type=1)
        self.assertEqual((descriptor.version, descriptor.model_type), (55, 1))
        self.assertTrue(geometry.parts[0].vertices)

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

    @unittest.skipUnless(M3_CONTENT.exists(), "M3 SDK content is not installed")
    def test_m3_compiled_motion_versions(self):
        root = M3_CONTENT / "motions/hud/weapon/m3_dynamo_machine"
        version_18 = motion.read_m2((root / "charger_pump.m2").read_bytes())
        version_19 = motion.read_m2(
            (root / "charger_idle_motorboat.m2").read_bytes())
        self.assertEqual((version_18.bones_count, version_18.frame_total), (43, 13))
        self.assertEqual(len(version_18.animated_bones), 4)
        self.assertEqual(len(version_18.locator_names), 2)
        self.assertEqual((version_19.bones_count, version_19.frame_total), (43, 386))
        self.assertTrue(version_19.bone_curves)

        version_16 = motion.read_m2((M3_CONTENT / "motions/object/tackle/"
                                     "fishing_rod_natyajka_left_0.m2").read_bytes())
        version_17 = motion.read_m2((M3_CONTENT / "motions/victoria/tower/"
                                     "tower7_08_02_4.m2").read_bytes())
        self.assertEqual((version_16.bones_count, version_16.frame_total), (12, 134))
        self.assertEqual((version_17.bones_count, version_17.frame_total), (190, 431))
        self.assertEqual(version_17.locator_names, ("loc_righthand",))

        references = motion.read_m2((M3_CONTENT / "motions/hud/weapon/wpn_base/"
                                     "06_bridge_tt_tihar_take_player_start.m2").read_bytes())
        self.assertEqual(references.locator_names, ("loc_wpn_base",))


if __name__ == "__main__":
    unittest.main()
