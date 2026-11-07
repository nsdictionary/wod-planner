import json
import unittest

import support
from support import codes, draft
from simulate import amrap_rounds, for_time_finish, simulate


def run(d, data=None):
    return simulate(d, data or support.fixture_data())


class WorkoutTimeVerificationTest(unittest.TestCase):
    def test_amrap_within_limit(self):
        errors, _, result = run(support.example_draft())
        self.assertEqual(errors, [])
        v = result["workout_time"]
        self.assertEqual((v["status"], v["basis_field"], v["minutes"], v["max_minutes"]),
                         ("verified", "duration_min", 12, 30))

    def test_boundary_30_is_ok(self):
        errors, _, result = run(support.example_draft(duration_min=30))
        self.assertEqual(errors, [])
        self.assertEqual(result["workout_time"]["status"], "verified")

    def test_amrap_over_30_fails(self):
        errors, _, result = run(support.example_draft(duration_min=35))
        self.assertEqual(codes(errors), ["workout_too_long"])
        self.assertEqual(result["workout_time"]["status"], "failed")
        self.assertEqual(result["estimate"]["status"], "skipped")

    def test_for_time_requires_tc(self):
        d = draft([{"id": "row", "reps": 500}], format="FOR_TIME", duration_min=None, rounds=3)
        errors, _, _ = run(d)
        self.assertEqual(codes(errors), ["time_cap_missing"])

    def test_for_time_duration_is_not_a_tc(self):
        # For Time에 duration_min만 있으면 TC 누락으로 실패하고 duration_min은 무시 경고
        d = draft([{"id": "row", "reps": 500}], format="FOR_TIME", duration_min=15, rounds=3)
        errors, warnings, _ = run(d)
        self.assertEqual(codes(errors), ["time_cap_missing"])
        self.assertIn("ignored_field", codes(warnings))

    def test_for_time_tc_over_30_fails(self):
        d = draft([{"id": "row", "reps": 500}], format="FOR_TIME", duration_min=None,
                  time_cap_min=32, rounds=3)
        self.assertEqual(codes(run(d)[0]), ["workout_too_long"])

    def test_for_time_requires_rounds(self):
        d = draft([{"id": "row", "reps": 500}], format="FOR_TIME", duration_min=None, time_cap_min=20)
        self.assertEqual(codes(run(d)[0]), ["rounds_missing"])

    def test_emom_verified_but_not_estimated(self):
        d = draft([{"id": "burpee", "reps": 10}], format="EMOM", duration_min=20)
        errors, _, result = run(d)
        self.assertEqual(errors, [])
        self.assertEqual(result["workout_time"]["status"], "verified")
        self.assertEqual(result["estimate"]["status"], "not_estimable")
        self.assertIn("Post-MVP", result["estimate"]["reason"])

    def test_emom_over_30_fails(self):
        d = draft([{"id": "v_up", "reps": 10}], format="EMOM", duration_min=40)
        self.assertEqual(codes(run(d)[0]), ["workout_too_long"])

    def test_amrap_requires_duration(self):
        d = draft([{"id": "row", "reps": 250}], duration_min=None)
        self.assertEqual(codes(run(d)[0]), ["duration_missing"])

    def test_unsupported_format(self):
        d = draft([{"id": "row", "reps": 250}], format="TABATA")
        errors, _, result = run(d)
        self.assertEqual(codes(errors), ["unsupported_format"])
        self.assertEqual(result["estimate"]["status"], "skipped")


class EstimateTest(unittest.TestCase):
    def test_example_round_range_from_fixture_values(self):
        # 픽스처 가상 값: T2B 10×2~4=20~40, Box 15×2~3.5=30~52.5, Shuttle 20×8~12=160~240, 전환 3×5~10=15~30
        errors, _, result = run(support.example_draft())
        e = result["estimate"]
        self.assertEqual(e["status"], "estimated")
        self.assertEqual(e["round_sec"], {"low": 225.0, "high": 362.5})
        self.assertEqual(e["transition_sec"]["low"], 15)
        # 720초 ÷ 362.5 = 1.99, 720 ÷ 225 = 3.2
        self.assertEqual(e["expected_rounds"]["low"], 1.99)
        self.assertEqual(e["expected_rounds"]["high"], 3.2)
        self.assertEqual((e["expected_rounds"]["completed_low"], e["expected_rounds"]["completed_high"]), (1, 3))
        self.assertTrue(any("피로도 미반영" in n for n in e["notes"]))
        self.assertTrue(all("테스트용 가상 값" == b["basis"] for b in e["breakdown"]))

    def test_missing_movement_time_is_not_estimable(self):
        d = draft([{"id": "toes_to_bar", "reps": 10}, {"id": "wall_ball", "reps": 20}])
        errors, _, result = run(d)
        self.assertEqual(errors, [])  # 추정 불가는 실패가 아님
        e = result["estimate"]
        self.assertEqual(e["status"], "not_estimable")
        self.assertEqual([m["item"] for m in e["missing"]], ["Wall Balls"])
        self.assertIsNone(e["round_sec"])

    def test_missing_transition_is_not_estimable(self):
        data = support.fixture_data()
        data["rules"]["estimation"]["transition_sec_range"] = None
        _, _, result = run(support.example_draft(), data)
        e = result["estimate"]
        self.assertEqual(e["status"], "not_estimable")
        self.assertEqual([m["item"] for m in e["missing"]], ["동작 간 전환 시간"])

    def test_unregistered_movement_is_listed_as_missing(self):
        d = draft([{"id": "pegboard_climb", "reps": 3}])
        _, _, result = run(d)
        self.assertEqual(result["estimate"]["missing"][0]["item"], "pegboard_climb")

    def test_fatigue_reduces_rounds(self):
        data = support.fixture_data()
        data["rules"]["estimation"]["fatigue_slowdown_per_round"] = {"low": 0.0, "high": 0.1}
        _, _, result = run(support.example_draft(), data)
        e = result["estimate"]
        self.assertEqual(e["fatigue"], {"low": 0.0, "high": 0.1})
        self.assertLess(e["expected_rounds"]["low"], 1.99)
        self.assertEqual(e["expected_rounds"]["high"], 3.2)
        self.assertFalse(any("피로도 미반영" in n for n in e["notes"]))

    def test_meter_unit(self):
        # Row 500m × 0.2~0.3 = 100~150초 + 전환 5~10 → 105~160, 3라운드 → 315~480초
        d = draft([{"id": "row", "reps": 500}], format="FOR_TIME", duration_min=None,
                  time_cap_min=10, rounds=3)
        errors, warnings, result = run(d)
        e = result["estimate"]
        self.assertEqual(errors, [])
        self.assertEqual(e["expected_finish_sec"], {"low": 315.0, "high": 480.0})
        self.assertEqual(e["tc_risk"], "within")
        self.assertEqual(warnings, [])

    def test_for_time_tc_risk_warnings(self):
        possible = draft([{"id": "row", "reps": 500}], format="FOR_TIME", duration_min=None,
                         time_cap_min=7, rounds=3)
        likely = draft([{"id": "row", "reps": 500}], format="FOR_TIME", duration_min=None,
                       time_cap_min=5, rounds=3)
        self.assertEqual(codes(run(possible)[1]), ["tc_possible_over"])
        self.assertEqual(codes(run(likely)[1]), ["tc_likely_over"])
        self.assertEqual(run(likely)[0], [])  # TC 초과 가능성은 경고일 뿐 실패 아님


class MathTest(unittest.TestCase):
    def test_amrap_rounds_without_fatigue(self):
        self.assertAlmostEqual(amrap_rounds(240, 720), 3.0)
        self.assertAlmostEqual(amrap_rounds(300, 720), 2.4)

    def test_amrap_rounds_with_fatigue(self):
        # 100, 110, 121 → 331초에 3라운드
        self.assertAlmostEqual(amrap_rounds(100, 331, 0.1), 3.0)

    def test_for_time_finish(self):
        self.assertAlmostEqual(for_time_finish(100, 3), 300)
        self.assertAlmostEqual(for_time_finish(100, 3, 0.1), 331)


class RealDataTest(unittest.TestCase):
    """실제 data/: 시간 값이 null이므로 본운동 검증만 되고 추정은 불가여야 한다."""

    def test_plan_example_with_real_data(self):
        from support import common
        data = common.load_data(support.REAL_DATA)
        errors, _, result = simulate(support.example_draft(), data)
        self.assertEqual(errors, [])
        self.assertEqual(result["workout_time"]["status"], "verified")
        e = result["estimate"]
        self.assertEqual(e["status"], "not_estimable")
        items = [m["item"] for m in e["missing"]]
        self.assertIn("Toes-to-Bar", items)
        self.assertIn("동작 간 전환 시간", items)
        self.assertIsNone(e["round_sec"])


class CliTest(unittest.TestCase):
    def test_exit_0_json(self):
        code, out, _ = support.run_script("simulate", support.EXAMPLE_DRAFT,
                                          "--data-dir", support.FIXTURE_DATA, "--json")
        report = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(set(report), {"script", "ok", "exit_code", "errors", "warnings", "result"})
        self.assertEqual(report["result"]["estimate"]["status"], "estimated")

    def test_exit_1_text(self):
        path = support.write_temp_json(self, {"format": "FOR_TIME", "rounds": 3,
                                              "movements": [{"id": "row", "reps": 500}]})
        code, out, _ = support.run_script("simulate", path, "--data-dir", support.FIXTURE_DATA)
        self.assertEqual(code, 1)
        self.assertIn("TC(time_cap_min)가 필수", out)

    def test_exit_2_schema_error(self):
        path = support.write_temp_json(self, {"format": "AMRAP", "duration_min": 12, "movements": "row"})
        code, _, err = support.run_script("simulate", path, "--data-dir", support.FIXTURE_DATA)
        self.assertEqual(code, 2)
        self.assertIn("movements:", err)

    def test_real_data_text_shows_not_estimable(self):
        code, out, _ = support.run_script("simulate", support.EXAMPLE_DRAFT)
        self.assertEqual(code, 0)
        self.assertIn("검증됨", out)
        self.assertIn("추정 불가", out)
        self.assertNotIn("라운드당", out)


if __name__ == "__main__":
    unittest.main()


class RequestLimitTest(unittest.TestCase):
    def test_request_limit_applies(self):
        errors, _, result = run(draft([{"id": "box_jump", "reps": 15}], duration_min=20, max_workout_min=18))
        self.assertEqual(codes(errors), ["workout_over_request"])
        v = result["workout_time"]
        self.assertEqual((v["max_minutes"], v["limit_source"], v["rules_max_minutes"]), (18, "request", 30))

    def test_request_limit_boundary_ok(self):
        errors, _, result = run(draft([{"id": "box_jump", "reps": 15}], duration_min=18, max_workout_min=18))
        self.assertEqual(errors, [])
        self.assertEqual(result["workout_time"]["status"], "verified")

    def test_request_above_rules_uses_rules(self):
        errors, warnings, result = run(draft([{"id": "box_jump", "reps": 15}], duration_min=32, max_workout_min=40))
        self.assertEqual(codes(errors), ["workout_too_long"])
        self.assertIn("request_limit_above_rules", codes(warnings))
        self.assertEqual(result["workout_time"]["max_minutes"], 30)

    def test_for_time_tc_against_request_limit(self):
        d = draft([{"id": "box_jump", "reps": 15}], format="FOR_TIME", duration_min=None,
                  time_cap_min=20, rounds=3, max_workout_min=18)
        self.assertEqual(codes(run(d)[0]), ["workout_over_request"])
