import json
import unittest
from pathlib import Path

import support
from support import codes
from autofix import (append_run, autofix, convert_reps, default_ledger_path, ledger_summary, load_ledger,
                     shortage_options)


def run(d, data=None, **kw):
    return autofix(d, data or support.fixture_data(), **kw)


def base(movements, **fields):
    d = {"date": "2026-11-10", "format": "AMRAP", "duration_min": 12, "expected_athletes": 6,
         "movements": movements}
    d.update(fields)
    return d


class NoFixNeededTest(unittest.TestCase):
    def test_clean_draft_passes_without_changes(self):
        errors, _, result = run(base([{"id": "box_jump", "reps": 15}]))
        self.assertEqual(errors, [])
        self.assertEqual((result["status"], result["attempts_used"], result["changed"]), ("passed", 0, False))
        self.assertEqual(result["validation_runs"], 1)

    def test_input_is_not_mutated(self):
        d = base([{"id": "row", "reps": 250}])
        before = json.dumps(d, sort_keys=True)
        run(d)
        self.assertEqual(json.dumps(d, sort_keys=True), before)


class FixThenPassTest(unittest.TestCase):
    def test_shortage_replaced_by_same_pattern_with_distance_conversion(self):
        # 로잉 5대(정확) vs 6명 → 같은 cardio 패턴 셔틀런으로 교체, 250m → 15m × 17회
        errors, warnings, result = run(base([{"id": "row", "reps": 250}, {"id": "box_jump", "reps": 15}]))
        self.assertEqual(errors, [])
        self.assertEqual((result["status"], result["attempts_used"]), ("passed", 1))
        change = result["changes"][0]
        self.assertEqual((change["before"]["id"], change["after"]["id"], change["after"]["reps"]),
                         ("row", "shuttle_run", 17))
        self.assertIn("거리 환산", change["reps_note"])
        self.assertEqual(result["final_draft"]["movements"][0]["id"], "shuttle_run")
        # 추정 수량 경고는 숨기지 않는다
        self.assertIn("quantity_approx", codes(warnings))

    def test_rx_substitution_propagates_to_scales(self):
        # Rx 로잉을 셔틀런으로 바꾸면 스케일의 로잉도 함께 바뀐다 (스케일은 수량 비교를 안 하므로)
        d = base([{"id": "row", "reps": 250}, {"id": "box_jump", "reps": 15}],
                 scales={"A": [{"id": "row", "reps": 200}, {"id": "box_jump", "reps": 12}],
                         "B": [{"id": "row", "reps": 150}, {"id": "v_up", "reps": 10}],
                         "C": [{"id": "v_up", "reps": 5}]})
        errors, _, result = run(d)
        self.assertEqual(errors, [])
        scales = result["final_draft"]["scales"]
        self.assertEqual((scales["A"][0]["id"], scales["A"][0]["reps"]), ("shuttle_run", 13))  # 200m / 15m
        self.assertEqual((scales["B"][0]["id"], scales["B"][0]["reps"]), ("shuttle_run", 10))
        self.assertEqual(len(result["changes"][0]["scale_changes"]), 2)

    def test_blocked_movement_uses_registered_substitute(self):
        errors, _, result = run(base([{"id": "ring_muscle_up", "reps": 5}]))
        self.assertEqual(errors, [])
        self.assertEqual(result["changes"][0]["after"]["id"], "toes_to_bar")
        self.assertEqual(result["changes"][0]["issue_code"], "space_restricted")

    def test_shortage_prefers_exact_enough_substitute(self):
        # T2B: 풀업바 약 8 vs 12명(부족 가능성). 등록 대체 중 Hanging Knee Raise는 같은 풀업바라 탈락,
        # V-up(장비 없음)이 선택된다.
        errors, _, result = run(base([{"id": "toes_to_bar", "reps": 10}], expected_athletes=12))
        self.assertEqual(errors, [])
        change = result["changes"][0]
        self.assertEqual(change["after"]["id"], "v_up")
        rejected = {c["id"]: c for c in change["candidates"]}
        self.assertEqual(rejected["hanging_knee_raise"]["result"], "rejected")

    def test_request_time_limit_is_enforced(self):
        errors, _, result = run(base([{"id": "box_jump", "reps": 15}], duration_min=20, max_workout_min=18))
        self.assertEqual(errors, [])
        self.assertEqual(result["final_draft"]["duration_min"], 18)
        self.assertEqual(result["changes"][0]["issue_code"], "workout_over_request")

    def test_for_time_tc_reduced_with_note(self):
        d = base([{"id": "box_jump", "reps": 15}], format="FOR_TIME", duration_min=None,
                 time_cap_min=40, rounds=3)
        errors, _, result = run(d)
        self.assertEqual(errors, [])
        self.assertEqual(result["final_draft"]["time_cap_min"], 30)
        self.assertIn("추정 불가", result["changes"][0]["note"])

    def test_scale_movement_is_fixed_too(self):
        d = base([{"id": "box_jump", "reps": 15}],
                 scales={"A": [{"id": "ring_muscle_up", "reps": 3}],
                         "B": [{"id": "v_up", "reps": 10}], "C": [{"id": "v_up", "reps": 5}]})
        errors, warnings, result = run(d)
        self.assertEqual(errors, [])
        self.assertEqual(result["changes"][0]["location"], "scales.A[0]")
        self.assertEqual(result["final_draft"]["scales"]["A"][0]["id"], "toes_to_bar")
        self.assertNotIn("scaling_missing", codes(warnings))


class UnresolvedTest(unittest.TestCase):
    def test_stops_after_three_attempts(self):
        # 문제 4개: 층고 제한, 미보유 장비, 30분 초과, 로잉 부족 → 3회 수정 후 1개 남음
        d = base([{"id": "ring_muscle_up", "reps": 5}, {"id": "sled_push", "reps": 20},
                  {"id": "row", "reps": 250}], duration_min=35)
        errors, _, result = run(d)
        self.assertEqual((result["status"], result["attempts_used"], result["validation_runs"]),
                         ("unresolved", 3, 4))
        self.assertEqual(codes(errors), ["short"])
        self.assertIn("3회", errors[0]["unresolved_reason"])
        # 앞의 세 문제는 실제로 고쳐졌다
        self.assertEqual([c["issue_code"] for c in result["changes"]],
                         ["space_restricted", "equipment_not_owned", "workout_too_long"])
        self.assertEqual(result["final_draft"]["duration_min"], 30)

    def test_no_candidate_needs_coach_with_evidence_options(self):
        # 12명 로잉: 셔틀런(약 8명)은 부족 가능성, 바이크(rep 단위)는 거리 환산 근거 없음 → 대체 불가
        errors, _, result = run(base([{"id": "row", "reps": 250}], expected_athletes=12))
        self.assertEqual((result["status"], result["attempts_used"]), ("needs_coach", 0))
        e = errors[0]
        reasons = {c["id"]: c["reason"] for c in e["candidates"]}
        self.assertIn("부족 가능성", reasons["shuttle_run"])
        self.assertIn("환산할 근거", reasons["bike_cal"])  # rep 동작이라 m → rep 환산 근거 없음
        opts = {o["option"].split(" ")[0]: o for o in e["operation_options"]}
        self.assertFalse(opts["파트너(2인"]["fits"])          # 동시 6명 > 5대
        heats = next(o for o in e["operation_options"] if "heats" in o)
        self.assertEqual((heats["heats"], heats["concurrent"], heats["fits"]), (3, 4, True))
        stations = next(o for o in e["operation_options"] if o["option"].startswith("스테이션"))
        self.assertIsNone(stations["fits"])                  # 시작 위치 분산은 해결로 보지 않음

    def test_unregistered_movement_is_not_autofixed(self):
        errors, _, result = run(base([{"id": "pegboard_climb", "reps": 3}]))
        self.assertEqual(result["status"], "needs_coach")
        self.assertEqual(codes(errors), ["unregistered_movement"])
        self.assertIn("의도", errors[0]["unresolved_reason"])

    def test_weight_not_owned_without_safe_candidate(self):
        d = base([{"id": "dumbbell_snatch", "reps": 10, "weights": {"dumbbell": [22.5]}}], expected_athletes=12)
        errors, _, result = run(d)
        self.assertEqual(result["status"], "needs_coach")
        self.assertEqual(codes(errors), ["weight_not_owned"])

    def test_max_attempts_zero_only_validates(self):
        errors, _, result = run(base([{"id": "row", "reps": 250}]), max_attempts=0)
        self.assertEqual((result["status"], result["attempts_used"], result["changed"]), ("unresolved", 0, False))
        self.assertEqual(codes(errors), ["short"])


class HonestReportingTest(unittest.TestCase):
    def test_every_step_records_both_validators(self):
        _, _, result = run(base([{"id": "row", "reps": 250}]))
        for step in result["history"]:
            self.assertEqual(set(step["validation"]), {"simulate", "check_equipment"})
        self.assertEqual({r["script"] for r in result["final_reports"].values()}, {"simulate", "check_equipment"})

    def test_passed_only_when_final_validation_exit_zero(self):
        _, _, result = run(base([{"id": "ring_muscle_up", "reps": 5}]))
        self.assertEqual(result["status"], "passed")
        self.assertTrue(all(r["exit_code"] == 0 for r in result["final_reports"].values()))

    def test_invalid_draft_is_input_error_not_success(self):
        errors, _, result = run({"format": "AMRAP", "movements": []})
        self.assertEqual(result["status"], "input_error")
        self.assertEqual(result["attempts_used"], 0)
        self.assertTrue(errors)

    def test_adult_without_scales_gets_quality_warning(self):
        _, warnings, _ = run(base([{"id": "box_jump", "reps": 15}]))
        self.assertIn("scaling_missing", codes(warnings))
        _, warnings, _ = run(base([{"id": "box_jump", "reps": 15}], group="kids"))
        self.assertNotIn("scaling_missing", codes(warnings))


class HelperTest(unittest.TestCase):
    def test_convert_reps(self):
        data = support.fixture_data()
        self.assertEqual(convert_reps(250, "row", "shuttle_run", data)[0], 17)
        self.assertEqual(convert_reps(10, "toes_to_bar", "v_up", data), (10, None))
        self.assertIsNone(convert_reps(250, "row", "box_jump", data)[0])

    def test_shortage_options_approx_marked(self):
        p = {"issue": {"needed": 12, "have": {"value": 8, "precision": "approx"}}}
        opts = shortage_options(p, {"format": "AMRAP", "duration_min": 12}, support.fixture_data()["rules"])
        heats = next(o for o in opts if "heats" in o)
        self.assertEqual(heats["heats"], 2)
        self.assertIn("추정 수량", heats["evidence"])
        self.assertIn("24분", heats["evidence"])


class CliTest(unittest.TestCase):
    def test_exit_codes_and_out_file(self):
        path = support.write_temp_json(self, base([{"id": "row", "reps": 250}]))
        out = Path(path).with_name("fixed.json")
        code, stdout, _ = support.run_script("autofix", path, "--data-dir", support.FIXTURE_DATA,
                                             "--out", out, "--json")
        report = json.loads(stdout)
        self.assertEqual((code, report["script"], report["result"]["status"]), (0, "autofix", "passed"))
        self.assertEqual(json.loads(out.read_text())["movements"][0]["id"], "shuttle_run")

    def test_exit_1_when_unresolved(self):
        path = support.write_temp_json(self, base([{"id": "row", "reps": 250}], expected_athletes=12))
        code, stdout, _ = support.run_script("autofix", path, "--data-dir", support.FIXTURE_DATA)
        self.assertEqual(code, 1)
        self.assertIn("코치 판단 필요", stdout)

    def test_refuses_to_write_into_wods(self):
        path = support.write_temp_json(self, base([{"id": "box_jump", "reps": 15}]))
        code, _, err = support.run_script("autofix", path, "--data-dir", support.FIXTURE_DATA,
                                          "--out", support.ROOT / "wods" / "2026-11-10.json")
        self.assertEqual(code, 2)
        self.assertIn("wods/", err)
        self.assertFalse((support.ROOT / "wods" / "2026-11-10.json").exists())

    def test_exit_2_on_invalid_draft(self):
        path = support.write_temp_json(self, {"format": "AMRAP", "movements": []})
        code, _, _ = support.run_script("autofix", path, "--data-dir", support.FIXTURE_DATA)
        self.assertEqual(code, 2)


class LedgerTest(unittest.TestCase):
    """수정 이력 원장: 재검증해도 이전 수정 기록이 사라지지 않는다."""

    def setUp(self):
        self.data = support.fixture_data()
        self.d = base([{"id": "row", "reps": 250}, {"id": "box_jump", "reps": 15}])

    def test_rerun_keeps_previous_changes_and_original(self):
        _, _, r1 = run(self.d, self.data)
        ledger = append_run(None, self.d, r1, at="2026-11-07T10:00:00+09:00")
        _, _, r2 = run(r1["final_draft"], self.data)                     # 이미 고친 초안 재검증
        self.assertEqual(r2["attempts_used"], 0)
        ledger = append_run(ledger, r1["final_draft"], r2, at="2026-11-07T10:05:00+09:00")
        self.assertEqual(ledger["original_draft"], self.d)               # 최초 초안 보존
        self.assertEqual([r["run"] for r in ledger["runs"]], [1, 2])
        self.assertEqual(len(ledger["runs"][0]["changes"]), 1)           # 1차 수정 기록 유지
        self.assertEqual(ledger["runs"][0]["before"]["problems"], ["short"])
        self.assertEqual(ledger["runs"][1]["changes"], [])
        self.assertTrue(ledger["runs"][1]["input_matches_previous_output"])
        s = ledger_summary(ledger)
        self.assertEqual((s["runs"], s["attempts_total"], s["chain_intact"]), (2, 1, True))
        self.assertEqual(s["first_before"]["problems"], ["short"])
        self.assertEqual(s["changes"][0]["run"], 1)
        self.assertNotEqual(s["original_sha256"], s["current_sha256"])

    def test_manual_edit_between_runs_is_flagged(self):
        _, _, r1 = run(self.d, self.data)
        ledger = append_run(None, self.d, r1)
        edited = dict(r1["final_draft"], duration_min=10)
        _, _, r2 = run(edited, self.data)
        ledger = append_run(ledger, edited, r2)
        s = ledger_summary(ledger)
        self.assertFalse(s["chain_intact"])
        self.assertEqual(s["manual_edits_between_runs"], [2])

    def test_cli_appends_ledger_and_refuses_corrupt_one(self):
        path = support.write_temp_json(self, self.d)
        args = [path, "--data-dir", support.FIXTURE_DATA, "--out", path, "--json"]
        support.run_script("autofix", *args)
        code, out, _ = support.run_script("autofix", *args)              # 같은 파일 재검증
        rep = json.loads(out)["result"]
        self.assertEqual(code, 0)
        self.assertEqual((rep["attempts_used"], rep["ledger"]["runs"], rep["ledger"]["attempts_total"]), (0, 2, 1))
        ledger_path = default_ledger_path(path)
        self.assertEqual(load_ledger(ledger_path)["original_draft"]["movements"][0]["id"], "row")
        ledger_path.write_text("{broken")
        code, _, err = support.run_script("autofix", *args)
        self.assertEqual(code, 2)
        self.assertEqual(ledger_path.read_text(), "{broken")             # 손상 원장 덮어쓰지 않음

    def test_ledger_of_other_date_refused(self):
        _, _, r1 = run(self.d, self.data)
        ledger = append_run(None, self.d, r1)
        path = support.write_temp_json(self, ledger)
        with self.assertRaises(support.common.InputError):
            load_ledger(path, "2026-12-01")

    def test_no_out_no_ledger(self):
        path = support.write_temp_json(self, self.d)
        code, out, _ = support.run_script("autofix", path, "--data-dir", support.FIXTURE_DATA, "--json")
        self.assertIsNone(json.loads(out)["result"]["ledger"])
        self.assertFalse(default_ledger_path(path).exists())


if __name__ == "__main__":
    unittest.main()
