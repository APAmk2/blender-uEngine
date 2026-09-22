"""Checks for multi-file import selection and partial failures."""

from pathlib import Path
from types import SimpleNamespace
import unittest

from io_scene_redux.utils import ie


class FakeOperator:
    def __init__(self, directory, names):
        self.directory = str(directory)
        self.filepath = str(directory / names[0])
        self.files = [SimpleNamespace(name=name) for name in names]
        self.messages = []

    def report(self, level, message):
        self.messages.append((level, message))


class BatchImportTests(unittest.TestCase):
    def test_multiple_files_continue_after_failure(self):
        operator = FakeOperator(Path("redux-test-dir"), ["bad.static", "good.static"])
        visited = []

        def importer(_context, path):
            visited.append(Path(path).name)
            if Path(path).name == "bad.static":
                raise ValueError("bad data")
            return 2

        self.assertEqual(ie.run_import(operator, None, importer), {"FINISHED"})
        self.assertEqual(visited, ["bad.static", "good.static"])
        self.assertTrue(any("1 failed" in message for _, message in operator.messages))

    def test_single_filepath_without_file_selection(self):
        operator = FakeOperator(Path("redux-test-dir"), ["one.mesh"])
        operator.files = []
        visited = []
        self.assertEqual(ie.run_import(operator, None, lambda _c, p: visited.append(p) or 1),
                         {"FINISHED"})
        self.assertEqual(visited, [operator.filepath])

    def test_reject_path_outside_selected_directory(self):
        operator = FakeOperator(Path("redux-test-dir"), ["../outside.mesh"])
        self.assertEqual(ie.run_import(operator, None, lambda _c, _p: 1),
                         {"CANCELLED"})


if __name__ == "__main__":
    unittest.main()
