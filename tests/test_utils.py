import math
import struct
import unittest
from pathlib import Path

from io_scene_redux.utils.formats_io import (ChunkedReader, ChunkedWriter,
                                             FormatError, PackedReader,
                                             PackedWriter)
from io_scene_redux.utils import bone, tex


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
