import json
import tempfile
import unittest
from datetime import date as Date
from pathlib import Path

import support
from support import codes
from recent_wods import recent


def record(day, movements, fmt="AMRAP", minutes=12):
    return {"schema": "wod-record/1", "date": day, "approved_at": f"{day}T20:00:00+09:00",
            "wod": {"date": day, "format": fmt, "duration_min": minutes,
                    "movements": [{"id": m, "reps": 10} for m in movements]}}


class RecentBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.wods = Path(tmp.name) / "wods"
        self.wods.mkdir()
        self.data = support.fixture_data()

    def put(self, day, rec=None, raw=None, name=None):
        p = self.wods / (name or f"{day}.json")
        p.write_text(raw if raw is not None else json.dumps(rec), encoding="utf-8")

    def run_recent(self, ref="2026-11-10", days=7, draft=None):
        return recent(self.wods, Date.fromisoformat(ref), days, self.data, draft)


class WindowTest(RecentBase):
    def test_no_records(self):
        errors, warnings, r = self.run_recent()
        self.assertEqual((errors, r["records"], r["no_records"]), ([], [], True))
        _, _, r = recent(self.wods / "missing", Date(2026, 11, 10), 7, self.data)
        self.assertTrue(r["no_records"])

    def test_seven_day_window_and_future_excluded(self):
        self.put("2026-11-02", record("2026-11-02", ["row"]))            # 8일 전 → 기간 밖
        self.put("2026-11-03", record("2026-11-03", ["bike_cal"]))         # 7일 전 → 포함
        self.put("2026-11-09", record("2026-11-09", ["box_jump"]))       # 어제
        self.put("2026-11-10", record("2026-11-10", ["toes_to_bar"]))    # 기준일 당일 → same_day
        self.put("2026-11-12", record("2026-11-12", ["wall_ball"]))      # 미래 → 제외
        errors, warnings, r = self.run_recent()
        self.assertEqual(errors, [])
        self.assertEqual([x["date"] for x in r["records"]], ["2026-11-09", "2026-11-03"])   # 최신순
        self.assertEqual(r["excluded_future"], ["2026-11-12"])
        self.assertEqual(r["same_day"]["date"], "2026-11-10")
        self.assertEqual(r["older_count"], 1)
        self.assertIn("future_records_excluded", codes(warnings))
        self.assertIn("same_day_record_exists", codes(warnings))
        self.assertEqual(r["records"][0]["format"], "AMRAP")
        self.assertEqual(r["records"][0]["workout_min"], 12)
        self.assertEqual(r["records"][0]["patterns"], ["legs"])

    def test_archive_subfolder_ignored(self):
        (self.wods / "archive").mkdir()
        (self.wods / "archive" / "2026-11-09.x.json").write_text("{}")
        _, warnings, r = self.run_recent()
        self.assertEqual((r["records"], warnings), ([], []))


class CorruptTest(RecentBase):
    def test_corrupt_incomplete_and_unknown_files_are_warned(self):
        self.put("2026-11-08", raw="{not json")
        self.put("2026-11-07", {"date": "2026-11-07"})                  # wod 없음
        self.put("2026-11-06", record("2026-11-05", ["row"]))            # 파일명 ≠ date
        self.put(None, raw="WOD - AMRAP 12", name="2026-11-05.txt")      # 예전 텍스트 형식
        self.put("2026-11-04", record("2026-11-04", ["pegboard"]))       # 미등록 동작
        _, warnings, r = self.run_recent()
        c = codes(warnings)
        for code in ("record_unreadable", "record_incomplete", "record_date_mismatch",
                     "unrecognized_file", "record_unknown_movement"):
            self.assertIn(code, c)
        self.assertEqual([x["date"] for x in r["records"]], ["2026-11-06", "2026-11-04"])


class RepeatTest(RecentBase):
    def test_repeats_warned_but_not_blocking(self):
        self.put("2026-11-07", record("2026-11-07", ["box_jump", "row"]))
        self.put("2026-11-08", record("2026-11-08", ["box_jump", "bike_cal"]))
        self.put("2026-11-09", record("2026-11-09", ["wall_ball"]))
        draft = support.draft([{"id": "box_jump", "reps": 15}])
        errors, warnings, r = self.run_recent(draft=draft)
        self.assertEqual(errors, [])                                     # 경고만, 금지 아님
        c = codes(warnings)
        self.assertIn("movement_repeated", c)
        self.assertIn("pattern_repeated", c)                              # legs 3회
        self.assertIn("draft_movement_recent", c)
        self.assertIn("draft_pattern_recent", c)                          # 어제 wall_ball = legs
        self.assertEqual(r["movement_counts"]["box_jump"], 2)
        self.assertEqual(r["draft_overlap"]["latest_date"], "2026-11-09")


class CliTest(RecentBase):
    def test_cli_json_and_bad_date(self):
        self.put("2026-11-09", record("2026-11-09", ["row"]))
        code, out, _ = support.run_script("recent_wods", "--date", "2026-11-10", "--wods-dir", self.wods,
                                          "--data-dir", support.FIXTURE_DATA, "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["result"]["records"][0]["date"], "2026-11-09")
        code, out, _ = support.run_script("recent_wods", "--date", "2026-11-20", "--wods-dir", self.wods,
                                          "--data-dir", support.FIXTURE_DATA)
        self.assertIn("최근 기록 없음", out)
        code, _, _ = support.run_script("recent_wods", "--date", "11/10", "--wods-dir", self.wods,
                                        "--data-dir", support.FIXTURE_DATA)
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
