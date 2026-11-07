import json
import unittest

import support
from support import codes, draft
from check_equipment import check_equipment


def run(d, data=None):
    return check_equipment(d, data or support.fixture_data())


def item(result, mid):
    return next(m for m in result["movements"] if m["id"] == mid)


def entry(result, mid, target):
    return next(e for e in item(result, mid)["equipment"] if e["target"] == target)


class NormalInputTest(unittest.TestCase):
    def test_plan_example_passes_with_warnings_only(self):
        errors, warnings, result = run(support.example_draft())
        self.assertEqual(errors, [])
        # 풀업바 약 8명, 셔틀런 약 8명 vs 12명 → 부족 가능성 / 박스 9개(정확) vs 12명 → 부족
        self.assertEqual(entry(result, "toes_to_bar", "pullup_bar")["status"], "possibly_short")
        self.assertEqual(entry(result, "shuttle_run", "space.shuttle_run")["status"], "possibly_short")
        self.assertEqual(entry(result, "box_jump", "box")["status"], "short")
        self.assertIn("short", codes(warnings))

    def test_enough_equipment_no_shortage(self):
        errors, warnings, result = run(draft([{"id": "row", "reps": 250}], expected_athletes=5))
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(entry(result, "row", "rower")["status"], "enough")

    def test_movement_without_equipment(self):
        errors, warnings, result = run(draft([{"id": "v_up", "reps": 10}]))
        self.assertEqual((errors, warnings), ([], []))
        self.assertEqual(item(result, "v_up")["equipment"], [])


class BlockingErrorTest(unittest.TestCase):
    def test_unregistered_movement(self):
        errors, _, result = run(draft([{"id": "pegboard_climb", "reps": 3}]))
        self.assertEqual(codes(errors), ["unregistered_movement"])
        self.assertEqual(item(result, "pegboard_climb")["status"], "error")

    def test_equipment_not_owned_suggests_substitute(self):
        errors, _, result = run(draft([{"id": "sled_push", "reps": 20}]))
        self.assertEqual(codes(errors), ["equipment_not_owned"])
        self.assertEqual([s["id"] for s in errors[0]["substitutes"]], ["shuttle_run"])
        self.assertIn("대체 후보", errors[0]["message"])

    def test_banned_only_for_listed_group(self):
        kids_errors, _, _ = run(draft([{"id": "handstand_walk", "reps": 10}], group="kids"))
        adult_errors, _, _ = run(draft([{"id": "handstand_walk", "reps": 10}], group="adult"))
        self.assertEqual(codes(kids_errors), ["banned_movement"])
        self.assertEqual(adult_errors, [])

    def test_ceiling_restriction(self):
        errors, _, result = run(draft([{"id": "ring_muscle_up", "reps": 5}]))
        self.assertEqual(codes(errors), ["space_restricted"])
        self.assertIn("층고", errors[0]["message"])
        self.assertEqual([s["id"] for s in item(result, "ring_muscle_up")["substitutes"]], ["toes_to_bar"])

    def test_blocked_movement_skips_quantity_comparison(self):
        # 링은 수량 미확인이지만, 층고 제한으로 못 쓰는 동작이므로 수량 경고를 내지 않는다
        _, warnings, result = run(draft([{"id": "ring_muscle_up", "reps": 5}]))
        self.assertEqual(warnings, [])
        self.assertEqual(item(result, "ring_muscle_up")["equipment"], [])

    def test_substitute_that_is_itself_blocked_is_not_suggested(self):
        data = support.fixture_data()
        data["equipment"]["equipment"]["pullup_bar"]["available"] = False
        errors, _, result = run(draft([{"id": "ring_muscle_up", "reps": 5}]), data)
        self.assertEqual(item(result, "ring_muscle_up")["substitutes"], [])
        self.assertIn("등록된 대체 동작 없음", errors[0]["message"])

    def test_weight_not_owned(self):
        errors, _, _ = run(draft([{"id": "dumbbell_snatch", "reps": 10, "weights": {"dumbbell": [22.5]}}]))
        self.assertEqual(codes(errors), ["weight_not_owned"])
        self.assertIn("22.5kg", errors[0]["message"])


class ShortageIsNotFailureTest(unittest.TestCase):
    def test_exact_shortage_is_warning_with_options(self):
        errors, warnings, result = run(draft([{"id": "row", "reps": 250}], expected_athletes=12))
        self.assertEqual(errors, [])
        e = entry(result, "row", "rower")
        self.assertEqual((e["needed"], e["status"]), (12, "short"))
        self.assertTrue(e["options"])
        self.assertIn("실행 불가는 아님", warnings[0]["message"])

    def test_concurrent_athletes_override(self):
        # 파트너 WOD: 동시에 6명만 로잉 → 5대에 대해 부족은 여전히 표시하되 필요 수량은 6
        _, _, result = run(draft([{"id": "row", "reps": 250, "concurrent_athletes": 6}]))
        self.assertEqual(entry(result, "row", "rower")["needed"], 6)
        _, _, result = run(draft([{"id": "row", "reps": 250, "concurrent_athletes": 4}]))
        self.assertEqual(entry(result, "row", "rower")["status"], "enough")

    def test_units_per_athlete(self):
        d = draft([{"id": "dumbbell_snatch", "reps": 10, "units_per_athlete": 2,
                    "weights": {"dumbbell": [15]}}], expected_athletes=4)
        _, _, result = run(d)
        e = entry(result, "dumbbell_snatch", "dumbbell")
        self.assertEqual((e["needed"], e["status"]), (8, "short"))

    def test_athletes_unknown_skips_comparison(self):
        _, warnings, result = run(draft([{"id": "row", "reps": 250}], expected_athletes=None))
        self.assertIn("athletes_unknown", codes(warnings))
        self.assertEqual(entry(result, "row", "rower")["status"], "not_compared")


class UncertainQuantityTest(unittest.TestCase):
    def test_approx_enough_still_warns(self):
        _, warnings, result = run(draft([{"id": "toes_to_bar", "reps": 10}], expected_athletes=6))
        self.assertEqual(entry(result, "toes_to_bar", "pullup_bar")["status"], "enough_approx")
        self.assertEqual(codes(warnings), ["quantity_approx"])

    def test_approx_short_is_possibly_short(self):
        _, warnings, _ = run(draft([{"id": "toes_to_bar", "reps": 10}], expected_athletes=12))
        self.assertEqual(codes(warnings), ["possibly_short"])

    def test_unknown_weight_quantity(self):
        _, warnings, result = run(draft([{"id": "dumbbell_snatch", "reps": 10,
                                          "weights": {"dumbbell": [10]}}]))
        self.assertEqual(entry(result, "dumbbell_snatch", "dumbbell")["status"], "unknown")
        self.assertEqual(codes(warnings), ["quantity_unknown"])

    def test_mixed_weights_take_least_precise(self):
        # 15kg 정확 6 + 20kg 약 4 → 합계 약 10
        _, _, result = run(draft([{"id": "dumbbell_snatch", "reps": 10,
                                   "weights": {"dumbbell": [15, 20]}}], expected_athletes=8))
        e = entry(result, "dumbbell_snatch", "dumbbell")
        self.assertEqual(e["have"], {"value": 10, "precision": "approx"})
        self.assertEqual(e["status"], "enough_approx")

    def test_weight_unspecified(self):
        _, warnings, _ = run(draft([{"id": "dumbbell_snatch", "reps": 10}]))
        self.assertEqual(codes(warnings), ["weight_unspecified"])

    def test_unknown_count_equipment(self):
        _, warnings, _ = run(draft([{"id": "kettlebell_swing", "reps": 15}]))
        self.assertEqual(codes(warnings), ["quantity_unknown"])

    def test_availability_unknown(self):
        errors, warnings, _ = run(draft([{"id": "bike_cal", "reps": 15}]))
        self.assertEqual(errors, [])
        self.assertEqual(codes(warnings), ["availability_unknown"])


class WallTargetTest(unittest.TestCase):
    def test_wall_ball_allowed_with_target_warning(self):
        errors, warnings, _ = run(draft([{"id": "wall_ball", "reps": 20}], expected_athletes=10))
        self.assertEqual(errors, [])
        wt = [w for w in warnings if w["code"] == "wall_target"]
        self.assertEqual(len(wt), 1)
        self.assertIn("약 2.3m", wt[0]["message"])
        self.assertIn("표준 높이 타깃 사용 불가", wt[0]["message"])


class CliTest(unittest.TestCase):
    def test_exit_0_and_json_shape(self):
        code, out, _ = support.run_script("check_equipment", support.EXAMPLE_DRAFT,
                                          "--data-dir", support.FIXTURE_DATA, "--json")
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(set(report), {"script", "ok", "exit_code", "errors", "warnings", "result"})
        self.assertEqual((report["script"], report["ok"], report["exit_code"]), ("check_equipment", True, 0))

    def test_exit_1_on_blocking_error(self):
        path = support.write_temp_json(self, {"format": "AMRAP", "duration_min": 10,
                                              "movements": [{"id": "ring_muscle_up", "reps": 5}]})
        code, out, _ = support.run_script("check_equipment", path, "--data-dir", support.FIXTURE_DATA)
        self.assertEqual(code, 1)
        self.assertIn("층고 제한", out)
        self.assertIn("종료 코드 1", out)

    def test_exit_2_on_invalid_json(self):
        path = support.write_temp_json(self, None, raw="{not json")
        code, out, err = support.run_script("check_equipment", path, "--data-dir", support.FIXTURE_DATA)
        self.assertEqual(code, 2)
        self.assertIn("JSON 형식 오류", err)

    def test_exit_2_json_report(self):
        code, out, _ = support.run_script("check_equipment", "/nonexistent.json",
                                          "--data-dir", support.FIXTURE_DATA, "--json")
        report = json.loads(out)
        self.assertEqual((code, report["exit_code"], report["result"]), (2, 2, None))
        self.assertEqual(report["errors"][0]["code"], "input_error")


if __name__ == "__main__":
    unittest.main()
