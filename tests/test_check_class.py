import json
import unittest

import support
from support import codes, draft
from check_class import check_class, parse_block
from common import InputError

FULL = ["warmup=12", "boxing=15", "briefing=5", "wod=18", "cooldown=10"]


def blocks(specs):
    return [parse_block(s) for s in specs]


class TotalTest(unittest.TestCase):
    def test_sum_matches_total(self):
        errors, warnings, result = check_class(60, blocks(FULL), ("warmup", "wod", "cooldown", "boxing"))
        self.assertEqual(errors, [])
        self.assertEqual(result["block_sum_min"], 60)
        self.assertEqual([(b["start_min"], b["end_min"]) for b in result["blocks"]][-1], (50, 60))
        self.assertIn("wod_not_checked", codes(warnings))

    def test_sum_mismatch_is_error(self):
        errors, _, _ = check_class(60, blocks(["warmup=10", "wod=20", "cooldown=10"]))
        self.assertEqual(codes(errors), ["class_total_mismatch"])
        self.assertEqual(errors[0]["diff"], -20)

    def test_required_boxing_missing(self):
        errors, _, _ = check_class(60, blocks(["warmup=20", "wod=30", "cooldown=10"]),
                                   ("warmup", "wod", "cooldown", "boxing"))
        self.assertEqual(codes(errors), ["class_block_missing"])


class WodBlockTest(unittest.TestCase):
    def setUp(self):
        self.data = support.fixture_data()

    def test_wod_block_holds_workout(self):
        d = draft([{"id": "box_jump", "reps": 15}], duration_min=15)
        errors, warnings, result = check_class(60, blocks(FULL), draft=d, data=self.data)
        self.assertEqual(errors, [])
        self.assertEqual((result["wod_block_min"], result["workout"]["minutes"]), (18, 15))

    def test_wod_block_shorter_than_workout(self):
        d = draft([{"id": "box_jump", "reps": 15}], duration_min=20)
        errors, _, _ = check_class(60, blocks(FULL), draft=d, data=self.data)
        self.assertEqual(codes(errors), ["wod_block_too_short"])

    def test_for_time_uses_tc(self):
        d = draft([{"id": "box_jump", "reps": 15}], format="FOR_TIME", duration_min=None,
                  time_cap_min=18, rounds=3)
        errors, warnings, _ = check_class(60, blocks(FULL), draft=d, data=self.data)
        self.assertEqual(errors, [])
        self.assertIn("wod_block_no_buffer", codes(warnings))

    def test_workout_and_class_limits_are_separate(self):
        # 수업 60분 합계는 맞지만 본운동이 코치 요청 상한(18분)을 넘으면 실패
        d = draft([{"id": "box_jump", "reps": 15}], duration_min=20, max_workout_min=18)
        errors, _, _ = check_class(60, blocks(["warmup=10", "boxing=15", "wod=25", "cooldown=10"]),
                                   draft=d, data=self.data)
        self.assertEqual(codes(errors), ["workout_over_request"])


class ParseTest(unittest.TestCase):
    def test_label_and_errors(self):
        b = parse_block("boxing=15:Shadow Boxing")
        self.assertEqual((b["kind"], b["minutes"], b["label"]), ("boxing", 15, "Shadow Boxing"))
        for bad in ("boxing", "yoga=10", "wod=abc", "wod=0"):
            with self.assertRaises(InputError):
                parse_block(bad)


class CliTest(unittest.TestCase):
    def test_cli_pass_and_fail(self):
        args = ["--total", "60", *sum((["--block", b] for b in FULL), []), "--require", "boxing",
                "--wod", support.EXAMPLE_DRAFT, "--data-dir", support.FIXTURE_DATA, "--json"]
        code, out, _ = support.run_script("check_class", *args)
        self.assertEqual((code, json.loads(out)["script"]), (0, "check_class"))
        code, _, _ = support.run_script("check_class", "--total", "60", "--block", "wod=20")
        self.assertEqual(code, 1)
        code, _, _ = support.run_script("check_class", "--total", "60", "--block", "yoga=20")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()


class BoxingIntervalTest(unittest.TestCase):
    BASE = ["warmup=12", "boxing=15", "briefing=5", "wod=18", "cooldown=10"]

    def run_iv(self, spec, specs=None):
        from check_class import parse_interval
        return check_class(60 if specs is None else sum(parse_block(s)["minutes"] for s in specs),
                           blocks(specs or self.BASE), intervals=[parse_interval(spec)])

    def boxing(self, result):
        return next(b for b in result["blocks"] if b["kind"] == "boxing")

    def test_rounds_work_rest_matches_block(self):
        errors, _, result = self.run_iv("boxing=4x3/1")   # 3×4 + 1×3 = 15
        self.assertEqual(errors, [])
        iv = self.boxing(result)["intervals"]
        self.assertEqual((iv["total_min"], iv["rests"]), (15, 3))

    def test_no_rest_after_last_round_by_default(self):
        _, _, result = self.run_iv("boxing=4x3/1")
        tl = self.boxing(result)["intervals"]["timeline"]
        self.assertEqual(tl[-1]["type"], "work")
        self.assertEqual(tl[-1]["end_min"], self.boxing(result)["end_min"])
        self.assertEqual(sum(1 for t in tl if t["type"] == "rest"), 3)

    def test_rest_after_last_only_when_specified(self):
        errors, _, _ = self.run_iv("boxing=4x3/1+")      # 16 ≠ 15
        self.assertEqual(codes(errors), ["interval_total_mismatch"])
        self.assertEqual(errors[0]["diff"], 1)
        specs = ["warmup=11", "boxing=16", "briefing=5", "wod=18", "cooldown=10"]
        errors, _, result = self.run_iv("boxing=4x3/1+", specs)
        self.assertEqual(errors, [])
        self.assertEqual(self.boxing(result)["intervals"]["timeline"][-1]["type"], "rest")

    def test_internal_mismatch_fails_even_if_class_total_ok(self):
        errors, _, _ = self.run_iv("boxing=3x3/1")       # 11 ≠ 15
        self.assertEqual(codes(errors), ["interval_total_mismatch"])
        self.assertEqual(errors[0]["diff"], -4)

    def test_fractional_minutes(self):
        specs = ["warmup=12.5", "boxing=14.5", "briefing=5", "wod=18", "cooldown=10"]
        errors, _, result = self.run_iv("boxing=5x2.5/0.5", specs)  # 12.5 + 2 = 14.5
        self.assertEqual(errors, [])
        self.assertEqual(self.boxing(result)["intervals"]["total_min"], 14.5)

    def test_boxing_without_interval_is_warning_only(self):
        errors, warnings, _ = check_class(60, blocks(self.BASE))
        self.assertEqual(errors, [])
        self.assertIn("boxing_intervals_unspecified", codes(warnings))

    def test_interval_for_missing_block(self):
        from check_class import parse_interval
        errors, _, _ = check_class(60, blocks(["warmup=20", "wod=30", "cooldown=10"]),
                                   intervals=[parse_interval("boxing=4x3/1")])
        self.assertEqual(codes(errors), ["interval_block_missing"])

    def test_bad_interval_specs(self):
        from check_class import parse_interval
        for bad in ("boxing=4x", "boxing=0x3/1", "yoga=4x3/1", "boxing", "boxing=4x3/-1"):
            with self.assertRaises(InputError):
                parse_interval(bad)

    def test_cli_interval_mismatch_exit_1(self):
        args = ["--total", "60", *sum((["--block", b] for b in self.BASE), [])]
        code, out, _ = support.run_script("check_class", *args, "--interval", "boxing=4x3/1")
        self.assertEqual(code, 0)
        self.assertIn("3분 × 4라운드 + 휴식 1분 × 3회 = 15분", out)
        code, out, _ = support.run_script("check_class", *args, "--interval", "boxing=4x3/1+")
        self.assertEqual(code, 1)
        self.assertIn("수업안을 쓸 수 없음", out)
