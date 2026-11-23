"""Source contract for read-only native SP sampling; no fabricated high-water evidence."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
NATIVE = (ROOT / "integration/emerald/pokednd_overworld.c").read_text()
PATCHER = (ROOT / "integration/emerald/apply.py").read_text()

class NativeStackSamplingTests(unittest.TestCase):
    def test_linker_bounds_and_pinned_stack_layout(self):
        for token in ("__pokednd_stack_low = ALIGN(", "__pokednd_stack_top = ORIGIN(IWRAM)",
                      "sp_sys: .word IWRAM_END - 0x1c0", "sp_irq: .word IWRAM_END - 0x60"):
            self.assertIn(token, PATCHER)

    def test_samples_actual_sp_without_writing_stack(self):
        self.assertIn('__asm__ volatile ("mov %0, sp" : "=r" (sp));', NATIVE)
        self.assertIn("sp < low || sp > top", NATIVE)
        self.assertIn("gPokeDnDStackSampleInvalid = 1;", NATIVE)
        self.assertIn("depth = (u32)(top - sp);", NATIVE)
        self.assertIn("gPokeDnDStackSamplePeak = depth;", NATIVE)
        self.assertNotIn("memset(__pokednd_stack", NATIVE)
        self.assertNotIn("*((volatile u32 *)sp)", NATIVE)

    def test_sampled_free_reserve_is_consistent_with_peak(self):
        self.assertIn("gPokeDnDStackSampleMinFree", NATIVE)
        self.assertIn("gPokeDnDStackSampleMinFree = sp - low;", NATIVE)
        self.assertIn("gPokeDnDStackSampleMinFree != top - low - gPokeDnDStackSamplePeak", NATIVE)
        self.assertIn("gPokeDnDStackSampleInvalid = 1;", NATIVE)
        self.assertNotIn("memset(__pokednd_stack", NATIVE)

    def test_corrupt_previous_extrema_fail_closed_before_mutation(self):
        sampler = NATIVE.split("static void PokeDnD_SampleSystemStack(void)", 1)[1].split(
            "#endif /* POKEDND_NATIVE_REPLAY_ROCKET */", 1)[0]
        guard = sampler.split("depth = (u32)(top - sp);", 1)[0]
        self.assertIn("gPokeDnDStackSampleMinFree != 0u", guard)
        self.assertIn("gPokeDnDStackSampleCount != 0u", guard)
        self.assertIn("gPokeDnDStackSampleMinFree < 256u", guard)
        self.assertIn("gPokeDnDStackSampleMinFree > top - low", guard)
        self.assertIn("gPokeDnDStackSampleMinFree != top - low - gPokeDnDStackSamplePeak", guard)
        self.assertLess(guard.index("gPokeDnDStackSampleMinFree != top - low - gPokeDnDStackSamplePeak"),
                        sampler.index("gPokeDnDStackSampleMinFree = sp - low;"))
        self.assertIn("gPokeDnDStackSampleInvalid = 1;", guard)

    def test_sampling_runs_before_field_input(self):
        hook = NATIVE.split("bool8 PokeDnD_HandleOverworldInput(u16 newKeys, u16 heldKeys)", 1)[1]
        self.assertLess(hook.index("PokeDnD_SampleSystemStack();"), hook.index("if (!sActive)"))
        self.assertIn("gPokeDnDStackSampleCount++", NATIVE)
        self.assertIn("gPokeDnDStackSampleCount == 0xFFFFFFFFu", NATIVE)

    def test_does_not_claim_unsampled_stack_high_water(self):
        self.assertIn("NOT a whole-program", NATIVE)
        self.assertNotIn("gPokeDnDStackHighWater =", NATIVE)

if __name__ == "__main__":
    unittest.main()
