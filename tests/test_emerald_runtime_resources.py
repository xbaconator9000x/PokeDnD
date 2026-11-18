import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("resources", Path(__file__).resolve().parents[1] / "integration/emerald/validate_runtime_resources.py")
resources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resources)


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write("runtime-probe.csv", "label,state\na,0\nb,1\n")
        self.write("runtime-oam.csv", "label,enabled_oam_entries,display_mode,obj_enabled\na,12,0,1\nb,40,0,1\n")
        self.write("runtime-stack.csv", "label,sp,bytes_above_iwram_base\na,50364412,32764\nb,50364408,32760\n")

    def write(self, name, contents):
        (self.root / name).write_text(contents)

    def test_valid(self):
        result = resources.validate(self.root)
        self.assertEqual(result["checkpoints"], 2)
        self.assertEqual(result["max_sampled_oam_entries"], 40)
        self.assertEqual(result["min_sampled_sp"], 50364408)

    def test_missing(self):
        (self.root / "runtime-stack.csv").unlink()
        with self.assertRaises(FileNotFoundError):
            resources.validate(self.root)

    def test_duplicate(self):
        self.write("runtime-probe.csv", "label,state\na,0\na,1\n")
        with self.assertRaises(ValueError):
            resources.validate(self.root)

    def test_order(self):
        self.write("runtime-probe.csv", "label,state\nb,0\na,1\n")
        with self.assertRaises(ValueError):
            resources.validate(self.root)

    def test_invalid_stack(self):
        self.write("runtime-stack.csv", "label,sp,bytes_above_iwram_base\na,50364412,0\nb,50364408,32760\n")
        with self.assertRaises(ValueError):
            resources.validate(self.root)

    def test_invalid_oam(self):
        self.write("runtime-oam.csv", "label,enabled_oam_entries,display_mode,obj_enabled\na,129,0,1\nb,40,0,1\n")
        with self.assertRaises(ValueError):
            resources.validate(self.root)
