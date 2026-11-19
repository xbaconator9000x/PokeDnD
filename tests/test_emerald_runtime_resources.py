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

    def test_heap_peak_survives_free(self):
        self.write("runtime-heap.csv", "label,current,peak,failures,capacity,epoch\na,200,300,0,1000,1\nb,100,400,0,1000,1\n")
        report = resources.validate(self.root, require_heap=True)
        self.assertEqual(report["heap_peak_bytes"], 400)
        self.assertEqual(report["heap_remaining_at_peak"], 600)

    def test_heap_invalid(self):
        for row in ("b,100,200,0,1000,1", "b,400,300,0,1000,1",
                    "b,100,300,1,1000,1", "b,100,300,0,1000,2",
                    "b,100,1001,0,1000,1"):
            self.write("runtime-heap.csv", "label,current,peak,failures,capacity,epoch\na,200,300,0,1000,1\n" + row + "\n")
            with self.subTest(row=row), self.assertRaises(ValueError):
                resources.validate(self.root, require_heap=True)

    def test_heap_required(self):
        with self.assertRaises(FileNotFoundError):
            resources.validate(self.root, require_heap=True)

    def test_watermark_peak_retained(self):
        self.write("runtime-watermark.csv", "label,low,top,used,untouched\na,50362432,50363968,512,1024\nb,50362432,50363968,256,1280\n")
        report = resources.validate(self.root, require_watermark=True)
        self.assertEqual(report["system_stack_peak_written_bytes"], 512)
        self.assertEqual(report["system_stack_min_untouched_bytes"], 1024)

    def test_watermark_invalid(self):
        for row in ("b,50362432,50363968,1408,128",
                    "b,50362436,50363968,512,1020",
                    "b,50362432,50363968,513,1023",
                    "b,50362432,50363968,512,1000",
                    "c,50362432,50363968,512,1024"):
            self.write("runtime-watermark.csv", "label,low,top,used,untouched\na,50362432,50363968,512,1024\n" + row + "\n")
            with self.subTest(row=row), self.assertRaises(ValueError):
                resources.validate(self.root, require_watermark=True)

    def test_watermark_required(self):
        with self.assertRaises(FileNotFoundError):
            resources.validate(self.root, require_watermark=True)
