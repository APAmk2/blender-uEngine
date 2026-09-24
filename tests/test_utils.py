import math
import struct
import unittest
from pathlib import Path

from io_scene_redux.utils.formats_io import (ChunkedReader, ChunkedWriter,
                                             FormatError, PackedReader,
                                             PackedWriter)
from io_scene_redux.utils import bone, tex


M3_CONTENT = Path(r"D:\Archive\m3sdk\content")
M4_CONTENT = Path(r"D:\Archive\m4_2022\UNPACK\content")
REDUX_CONTENT = Path(r"D:\Soft\ReduxSDK\content")


class UtilityTests(unittest.TestCase):
    def test_original_formats_io_interface(self):
        writer = PackedWriter()
        writer.putf("<I", 17)
        writer.puts("redux")
        reader = PackedReader(writer.data)
        self.assertEqual(reader.getf("<I"), (17,))
        self.assertEqual(reader.gets(), "redux")
        reader.readed()

        chunks = ChunkedWriter()
        chunks.put(3, b"data")
        self.assertEqual(ChunkedReader(chunks.data).read(), [(3, b"data")])

    def test_chunk_writer_reader_preserve_full_ids(self):
        writer = ChunkedWriter()
        writer.put(0x80000001, b"abc")
        self.assertEqual(list(ChunkedReader(writer.data)), [(0x80000001, b"abc")])
        with self.assertRaises(FormatError):
            list(ChunkedReader(writer.data[:-1]))

    def test_texture_path_is_inside_content(self):
        root = Path("content")
        self.assertEqual(tex.make_abs_tex_path(root, "wall\\brick"),
                         root / "textures" / "wall" / "brick.png")
        with self.assertRaises(ValueError):
            tex.make_abs_tex_path(root, "..\\secret")
        self.assertEqual(list(tex.texture_candidates(root, "act\\act_hair"))[:3],
                         [root / "textures" / "act" / ("act_hair" + extension)
                          for extension in (".png", ".tga", ".psd")])

    @unittest.skipUnless(M3_CONTENT.exists(), "M3 SDK content is not installed")
    def test_m3_compiled_texture_fallback(self):
        data, source = tex.compiled_texture_dds(M3_CONTENT, "black_invisible")
        self.assertEqual(source.suffix, ".512")
        self.assertEqual(data[:4], b"DDS ")
        self.assertEqual(struct.unpack_from("<2I", data, 12), (512, 512))
        self.assertEqual(data[84:88], b"DX10")
        self.assertEqual(struct.unpack_from("<I", data, 128)[0], 99)
        self.assertEqual(len(data), 148 + 512 * 512)
        dds_path = tex._compiled_cache_path(source, data)
        png_path = tex._convert_dds_to_png(M3_CONTENT, dds_path)
        self.assertIsNotNone(png_path)
        self.assertEqual(png_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    @unittest.skipUnless(M4_CONTENT.exists(), "M4 2022 content is not installed")
    def test_m4_compiled_texture_fallback(self):
        data, source = tex.compiled_texture_dds(M4_CONTENT, "black_invisible")
        self.assertEqual(source.suffix, ".512")
        self.assertEqual(data[:4], b"DDS ")
        self.assertEqual(len(data), 148 + 512 * 512)
        converter = tex._sdk_texconv(M4_CONTENT)
        self.assertEqual(converter, Path(tex.__file__).resolve().parent.parent /
                         "bin" / "texconv.exe")
        dds_path = tex._compiled_cache_path(source, data)
        png_path = tex._convert_dds_to_png(M4_CONTENT, dds_path)
        self.assertIsNotNone(png_path)
        self.assertEqual(png_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    @unittest.skipUnless(REDUX_CONTENT.exists(), "Redux SDK content is not installed")
    def test_redux_compiled_texture_fallback(self):
        data, source = tex.compiled_texture_dds(
            REDUX_CONTENT, "wpn34\\wpn34_padonocheg_addon")
        self.assertEqual(source.suffix, ".64")
        self.assertEqual(data[:4], b"DDS ")
        self.assertEqual(data[84:88], b"DXT1")
        self.assertEqual(len(data), 128 + 64 * 64 // 2)

    def test_generated_obb_contains_points(self):
        points = [(0, 0, 0), (1, 0, 0), (1, 2, 0), (0, 2, 3)]
        values = struct.unpack("<15f", bone.generate_obb(points))
        axes = (values[0:3], values[3:6], values[6:9])
        center, halfsize = values[9:12], values[12:15]
        for point in points:
            relative = [point[i] - center[i] for i in range(3)]
            for axis, half in zip(axes, halfsize):
                projection = sum(a * b for a, b in zip(relative, axis))
                self.assertLessEqual(abs(projection), half + 1e-5)
        self.assertTrue(all(math.isfinite(value) for value in values))


if __name__ == "__main__":
    unittest.main()
