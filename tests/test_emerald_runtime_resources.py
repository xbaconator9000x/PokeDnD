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
        self.write("runtime-watermark.csv", "label,low,top,used,untouched\na,50362432,50363968,256,1280\nb,50362432,50363968,512,1024\n")
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

    def irq_trace(self, second):
        self.write("runtime-irq.csv",
                   "label,low,top,used,untouched\n"
                   f"a,{0x03007E40},{0x03007FA0},192,160\n" + second + "\n")

    def test_irq_peak_retained(self):
        self.irq_trace(f"b,{0x03007E40},{0x03007FA0},224,128")
        report = resources.validate(self.root, require_irq=True)
        self.assertEqual(report["irq_stack_peak_written_bytes"], 224)
        self.assertEqual(report["irq_stack_min_untouched_bytes"], 128)

    def test_system_stack_watermark_regression_rejected(self):
        self.write("runtime-watermark.csv",
                   "label,low,top,used,untouched\na,50362432,50363968,512,1024\nb,50362432,50363968,256,1280\n")
        with self.assertRaisesRegex(ValueError, "regressed"):
            resources.validate(self.root, require_watermark=True)

    def test_irq_watermark_regression_rejected(self):
        self.irq_trace(f"b,{0x03007E40},{0x03007FA0},128,224")
        with self.assertRaisesRegex(ValueError, "regressed"):
            resources.validate(self.root, require_irq=True)

    def test_irq_budget_boundary(self):
        self.irq_trace(f"b,{0x03007E40},{0x03007FA0},320,32")
        self.assertEqual(resources.validate(self.root, require_irq=True)["irq_stack_min_untouched_bytes"], 32)

    def test_irq_invalid(self):
        for label, low, top, used, untouched in (
            ("b", 0x03007E40, 0x03007FA0, 324, 28),
            ("b", 0x03007E44, 0x03007FA0, 192, 160),
            ("b", 0x03007E40, 0x03007FA4, 192, 160),
            ("b", 0x03007E40, 0x03007FA0, 193, 159),
            ("b", 0x03007E40, 0x03007FA0, 192, 156),
            ("c", 0x03007E40, 0x03007FA0, 192, 160),
        ):
            self.irq_trace(f"{label},{low},{top},{used},{untouched}")
            with self.subTest(label=label, low=low, top=top, used=used, untouched=untouched):
                with self.assertRaises(ValueError):
                    resources.validate(self.root, require_irq=True)

    def test_irq_required(self):
        with self.assertRaises(FileNotFoundError):
            resources.validate(self.root, require_irq=True)

    def test_irq_no_writes_rejected(self):
        self.write("runtime-irq.csv", "label,low,top,used,untouched\n" +
                   "".join(f"{label},{0x03007E40},{0x03007FA0},0,352\n" for label in ("a", "b")))
        with self.assertRaises(ValueError):
            resources.validate(self.root, require_irq=True)

    def test_heap_reserve_boundary(self):
        for peak in (744, 745):
            self.write("runtime-heap.csv",
                       "label,current,peak,failures,capacity,epoch\n"
                       f"a,100,{peak},0,1000,1\nb,100,{peak},0,1000,1\n")
            if peak == 744:
                self.assertEqual(resources.validate(self.root, require_heap=True)["heap_remaining_at_peak"], 256)
            else:
                with self.assertRaisesRegex(ValueError, "heap reserve"):
                    resources.validate(self.root, require_heap=True)


    def test_video_checkpoints(self):
        self.write("runtime-video.csv", "label,dispcnt,dispstat,vcount,bg0cnt,bg1cnt,bg2cnt,bg3cnt\na,4352,0,12,7168,0,0,0\nb,4352,1,170,7168,0,0,0\n")
        report = resources.validate(self.root, require_video=True)
        self.assertEqual(report["video_checkpoints"], 2)
        self.assertEqual(report["text_bg_layouts"][0]["screen_base"], 28)

    def test_video_shared_screen_blocks(self):
        self.write("runtime-video.csv", "label,dispcnt,dispstat,vcount,bg0cnt,bg1cnt,bg2cnt,bg3cnt\na,4864,0,12,7168,7168,0,0\nb,4864,1,170,7168,7424,0,0\n")
        report = resources.validate(self.root, require_video=True)
        self.assertEqual(report["peak_sampled_text_screen_bytes"], 4096)

    def test_video_character_span_union(self):
        # Both BGs reference char block 3 and screen blocks inside it.
        # Second checkpoint adds char block 0 without double-counting screen maps.
        self.write("runtime-video.csv", "label,dispcnt,dispstat,vcount,bg0cnt,bg1cnt,bg2cnt,bg3cnt\na,4864,0,12,7180,7180,0,0\nb,4864,1,170,7180,7424,0,0\n")
        report = resources.validate(self.root, require_video=True)
        self.assertEqual(report["peak_sampled_text_char_base_span_bytes"], 32768)
        self.assertEqual(report["peak_sampled_text_base_union_bytes"], 32768)
        self.assertEqual(report["peak_sampled_text_screen_bytes"], 4096)

    def test_video_invalid(self):
        for value in ("b,4352,0,228,7168,0,0,0", "b,0,0,10,0,0,0,0",
                      "b,4352,0,10,65280,0,0,0"):
            self.write("runtime-video.csv", "label,dispcnt,dispstat,vcount,bg0cnt,bg1cnt,bg2cnt,bg3cnt\na,4352,0,12,7168,0,0,0\n" + value + "\n")
            with self.subTest(value=value), self.assertRaises(ValueError):
                resources.validate(self.root, require_video=True)

    def test_video_missing(self):
        with self.assertRaises(FileNotFoundError):
            resources.validate(self.root, require_video=True)


class HudAllocationTests(unittest.TestCase):
    def test_native_window_guard(self):
        import subprocess
        source = (Path(__file__).resolve().parents[1] /
                  "integration/emerald/pokednd_hud.c").read_text()
        guard = source.split("static bool8 HudWindowOwnsTiles", 1)[1].split(
            "bool8 PokeDnD_HudOpen", 1)[0]
        harness = r"""
#include <stddef.h>
#include <assert.h>
typedef unsigned int u32;
typedef unsigned char bool8;
#define FALSE 0
#define TRUE 1
#define WINDOWS_MAX 32
struct WindowTemplate {
    unsigned bg, tilemapLeft, tilemapTop, width, height, baseBlock;
};
struct Window { struct WindowTemplate window; void *tileData; };
static struct Window gWindows[WINDOWS_MAX];
static bool8 HudWindowOwnsTiles
""" + guard + r"""
int main(void) {
    unsigned i;
    for (i=0; i<WINDOWS_MAX; ++i) gWindows[i].window.bg=255;
    gWindows[0].window=(struct WindowTemplate){0,1,0,28,6,64};
    gWindows[0].tileData=&gWindows[0];
    gWindows[1].window=(struct WindowTemplate){0,2,15,27,4,404};
    assert(HudWindowOwnsTiles(0));
    gWindows[1].window.baseBlock=231;
    assert(!HudWindowOwnsTiles(0));
    gWindows[1].window.baseBlock=232;
    assert(HudWindowOwnsTiles(0));
    gWindows[1].window.tilemapTop=5;
    assert(!HudWindowOwnsTiles(0));
    gWindows[1].window.bg=1;
    assert(HudWindowOwnsTiles(0));
    gWindows[0].window.baseBlock=857;
    assert(!HudWindowOwnsTiles(0));
    gWindows[0].window.baseBlock=856;
    assert(HudWindowOwnsTiles(0));
    assert(!HudWindowOwnsTiles(WINDOWS_MAX));
    gWindows[0].window.tilemapLeft=5;
    assert(!HudWindowOwnsTiles(0));
    gWindows[0].window.tilemapLeft=4;
    assert(HudWindowOwnsTiles(0));
    gWindows[0].window.tilemapTop=27;
    assert(!HudWindowOwnsTiles(0));
    gWindows[0].window.tilemapTop=26;
    assert(HudWindowOwnsTiles(0));
    gWindows[0].window.height=0;
    assert(!HudWindowOwnsTiles(0));
    gWindows[0].window.height=6;
    gWindows[0].window.width=0;
    assert(!HudWindowOwnsTiles(0));
    gWindows[0].window.width=28;
    gWindows[0].tileData=NULL;
    assert(!HudWindowOwnsTiles(0));
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "guard.c"
            exe = Path(directory) / "guard"
            src.write_text(harness)
            subprocess.run(["cc", "-std=c99", "-Wall", "-Wextra", "-Werror",
                            str(src), "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True)

