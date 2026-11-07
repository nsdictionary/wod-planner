import shutil
import tempfile
import unittest
from pathlib import Path

import support
from support import common


class LoadDataTest(unittest.TestCase):
    def test_real_data_loads_and_references_are_valid(self):
        data = common.load_data(support.REAL_DATA)
        self.assertIn("rower", data["equipment"]["equipment"])
        self.assertEqual(data["rules"]["workout_max_min"], 30)

    def test_real_data_has_no_invented_time_values(self):
        # 실제 데이터의 시간 값은 코치 확인 전까지 null이어야 한다 (테스트가 실제 값을 바꾸지 않았는지 확인)
        data = common.load_data(support.REAL_DATA)
        for mid, m in data["movements"]["movements"].items():
            self.assertIsNone(m["time_estimate"], mid)
        self.assertIsNone(data["rules"]["estimation"]["transition_sec_range"])

    def test_fixture_data_loads(self):
        data = common.load_data(support.FIXTURE_DATA)
        self.assertEqual(data["rules"]["estimation"]["transition_sec_range"], {"low": 5, "high": 10})

    def test_missing_data_dir(self):
        with self.assertRaises(common.InputError) as ctx:
            common.load_data("/nonexistent/wod-data")
        self.assertIn("데이터 디렉터리가 없습니다", str(ctx.exception))

    def _copy_fixture(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        dest = Path(tmp.name) / "data"
        shutil.copytree(support.FIXTURE_DATA, dest)
        return dest

    def test_broken_json_reports_location(self):
        d = self._copy_fixture()
        (d / "equipment.json").write_text('{"equipment": {', encoding="utf-8")
        with self.assertRaises(common.InputError) as ctx:
            common.load_data(d)
        self.assertIn("JSON 형식 오류", str(ctx.exception))
        self.assertIn("행", str(ctx.exception))

    def test_rules_without_json_block(self):
        d = self._copy_fixture()
        (d / "rules.md").write_text("# 규칙\n설정 없음\n", encoding="utf-8")
        with self.assertRaises(common.InputError) as ctx:
            common.load_data(d)
        self.assertIn("json 기계 판독 설정 블록이 없습니다", str(ctx.exception))

    def test_broken_reference_is_reported(self):
        d = self._copy_fixture()
        text = (d / "movements.json").read_text(encoding="utf-8").replace('["rower"]', '["rowing_machine"]')
        (d / "movements.json").write_text(text, encoding="utf-8")
        with self.assertRaises(common.InputError) as ctx:
            common.load_data(d)
        self.assertIn("'rowing_machine'가 equipment.json에 없습니다", str(ctx.exception))

    def test_validate_data_rejects_bad_quantity_and_unbased_time(self):
        data = support.fixture_data()
        data["equipment"]["equipment"]["box"]["count"] = {"value": 9, "precision": "about"}
        data["movements"]["movements"]["v_up"]["time_estimate"] = {"sec_per_unit": {"low": 1, "high": 2}}
        errors = common.validate_data(data)
        self.assertTrue(any("box.count.precision" in e for e in errors))
        self.assertTrue(any("근거가 없는 시간 추정치" in e for e in errors))


class ValidateDraftTest(unittest.TestCase):
    def test_valid_example(self):
        d = support.example_draft()
        self.assertEqual(d["format"], "AMRAP")

    def test_collects_all_structural_errors(self):
        bad = {"date": "11/10", "format": "", "duration_min": -1, "expected_athletes": 0,
               "group": "teens",
               "movements": [{"id": "", "reps": 0}, {"id": "row", "reps": 250, "weights": {"dumbbell": []}}]}
        with self.assertRaises(common.InputError) as ctx:
            common.validate_draft(bad)
        msg = str(ctx.exception)
        for expected in ("date:", "format:", "duration_min:", "expected_athletes:", "group:",
                         "movements[0].id", "movements[0].reps", "movements[1].weights.dumbbell"):
            self.assertIn(expected, msg)

    def test_empty_movements(self):
        with self.assertRaises(common.InputError) as ctx:
            common.validate_draft({"format": "AMRAP", "movements": []})
        self.assertIn("movements:", str(ctx.exception))

    def test_top_level_must_be_object(self):
        with self.assertRaises(common.InputError):
            common.validate_draft([1, 2])

    def test_bool_is_not_a_number(self):
        with self.assertRaises(common.InputError):
            common.validate_draft({"format": "AMRAP", "movements": [{"id": "row", "reps": True}]})


class HelperTest(unittest.TestCase):
    def test_fmt_sec(self):
        self.assertEqual(common.fmt_sec(225), "3:45")
        self.assertEqual(common.fmt_sec(362.5), "6:02")

    def test_weight_key_matches_data_keys(self):
        self.assertEqual(common.weight_key(15), "15")
        self.assertEqual(common.weight_key(15.0), "15")
        self.assertEqual(common.weight_key(1.5), "1.5")


if __name__ == "__main__":
    unittest.main()
