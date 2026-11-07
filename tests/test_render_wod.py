import copy
import json
import re
import unittest
from pathlib import Path

import support
from support import codes
from autofix import autofix
from render_wod import (
    STATUS_MARK,
    build,
    header_line,
    missing_lines,
    movement_line,
    render_sections,
    whiteboard_text,
)

REAL_DRAFT = support.ROOT / "drafts" / "2026-11-09.json"
LINE_RE = re.compile(r"^\d+(\.\d+)?m? [A-Z][A-Za-z\- ]+")   # "17 Shuttle Runs", "250m Row"
SCALES = {"A": [{"id": "toes_to_bar", "reps": 6}, {"id": "box_jump", "reps": 12, "load": "20 in"}],
          "B": [{"id": "hanging_knee_raise", "reps": 10}, {"id": "box_jump", "reps": 10, "load": "20 in"}],
          "C": [{"id": "v_up", "reps": 8}, {"id": "box_jump", "reps": 8, "load": "20 in"}]}


def base(movements=None, **fields):
    d = {"date": "2026-11-10", "format": "AMRAP", "duration_min": 12, "expected_athletes": 6,
         "movements": movements or [{"id": "toes_to_bar", "reps": 10}, {"id": "box_jump", "reps": 15, "load": "24/20 in"}],
         "scales": copy.deepcopy(SCALES)}
    d.update(fields)
    return d


class MovementLineTest(unittest.TestCase):
    def setUp(self):
        self.data = support.fixture_data()

    def test_units_load_weights_target(self):
        self.assertEqual(movement_line({"id": "row", "reps": 250}, self.data), "250m Row")
        self.assertEqual(movement_line({"id": "box_jump", "reps": 15, "load": "24/20 in"}, self.data),
                         "15 Box Jumps (24/20 in)")
        self.assertEqual(movement_line({"id": "dumbbell_snatch", "reps": 10, "weights": {"dumbbell": [15, 10]}},
                                       self.data), "10 Dumbbell Snatches (15/10 kg)")
        self.assertEqual(movement_line({"id": "wall_ball", "reps": 20}, self.data), "20 Wall Balls (target ~2.3m)")
        self.assertIsNone(movement_line({"id": "pegboard", "reps": 1}, self.data))

    def test_headers(self):
        self.assertEqual(header_line({"format": "AMRAP", "duration_min": 15}), "WOD - AMRAP 15")
        self.assertEqual(header_line({"format": "FOR_TIME", "rounds": 3, "time_cap_min": 18}),
                         "WOD - 3 Rounds For Time (TC 18)")
        self.assertEqual(header_line({"format": "FOR_TIME", "rounds": 1, "time_cap_min": 10}),
                         "WOD - For Time (TC 10)")


class CompletenessTest(unittest.TestCase):
    def setUp(self):
        self.data = support.fixture_data()

    def test_every_movement_rendered_with_name_and_count(self):
        sections, errors = render_sections(base(), self.data)
        self.assertEqual(errors, [])
        self.assertEqual([s["name"] for s in sections], ["Rx", "Scale A", "Scale B", "Scale C"])
        for s in sections:
            self.assertEqual(len(s["lines"]), 2)
            for ln in s["lines"]:
                self.assertRegex(ln, LINE_RE)
                self.assertFalse(ln.rstrip().endswith(("/", "×", "+", ",")))

    def test_scale_missing_movement_is_error_and_not_filled(self):
        d = base()
        d["scales"]["C"] = [{"id": "v_up", "reps": 8}]          # Rx는 2개
        sections, errors = render_sections(d, self.data)
        self.assertEqual(codes(errors), ["scale_movement_count_mismatch"])
        self.assertEqual(sections[-1]["lines"], ["8 V-ups"])     # 빠진 동작을 지어내지 않음

    def test_adult_without_scales_is_error(self):
        d = base()
        del d["scales"]
        _, errors = render_sections(d, self.data)
        self.assertEqual(codes(errors), ["scale_missing"])

    def test_truncated_copy_is_detected(self):
        d = base()
        sections, _ = render_sections(d, self.data)
        full = whiteboard_text(d, sections)
        self.assertEqual(missing_lines(full, d, self.data), [])
        truncated = full.replace("8 Box Jumps (20 in)", "8")
        self.assertEqual(missing_lines(truncated, d, self.data), ["8 Box Jumps (20 in)"])


class AutofixOutputTest(unittest.TestCase):
    def test_final_text_matches_fixed_draft(self):
        data = support.fixture_data()
        d = base([{"id": "row", "reps": 250}, {"id": "box_jump", "reps": 15, "load": "24/20 in"}])
        for lv in "ABC":
            d["scales"][lv][0] = {"id": "row", "reps": 200}
        _, _, result = autofix(d, data)
        self.assertEqual(result["status"], "passed")
        sections, errors = render_sections(result["final_draft"], data)
        self.assertEqual(errors, [])
        self.assertEqual(result["final_text"], whiteboard_text(result["final_draft"], sections))
        self.assertNotIn("Row", result["final_text"])
        self.assertIn("17 Shuttle Runs (15m = 1 rep)", result["final_text"])
        self.assertEqual(result["final_text"].count("13 Shuttle Runs (15m = 1 rep)"), 3)

    def test_stale_autofix_report_is_not_shown(self):
        data = support.fixture_data()
        d = base()
        report = {"result": {"final_draft": base(duration_min=10), "history": [], "changes": []}}
        _, warnings, result = build(d, data, autofix_report=report)
        self.assertIsNone(result["autofix"])
        self.assertIn("autofix_report_mismatch", codes(warnings))


class SummaryTest(unittest.TestCase):
    def setUp(self):
        self.data = support.fixture_data()

    def test_passed_only_for_code_checks_and_coach_items_separate(self):
        errors, _, result = build(base(), self.data)
        self.assertEqual(errors, [])
        statuses = {c["item"]: c["status"] for c in result["checks"]}
        self.assertEqual(statuses["스케일 장비 수량"], "not_checked")
        self.assertEqual(statuses["수업 시간 합계"], "not_checked")
        self.assertEqual(statuses["완주 가능성"], "estimated")   # fixture에는 시간 데이터가 있음
        for c in result["checks"]:
            self.assertIn(c["status"], STATUS_MARK)
            self.assertTrue(c["source"])
        self.assertTrue(any("자극" in x for x in result["coach_review"]))
        self.assertFalse(any("자극" in c["item"] for c in result["checks"]))

    def test_details_are_complete_sentences(self):
        _, _, result = build(base(), self.data)
        for c in result["checks"]:
            self.assertRegex(c["detail"], r"[.)]$", c["item"])

    def test_render_error_fails_summary(self):
        d = base()
        d["scales"]["B"] = d["scales"]["B"][:1]
        errors, _, result = build(d, self.data)
        self.assertIn("scale_movement_count_mismatch", codes(errors))
        item = next(c for c in result["checks"] if c["item"].startswith("화이트보드"))
        self.assertEqual(item["status"], "failed")


class CliTest(unittest.TestCase):
    def test_check_text_and_class_args(self):
        path = support.write_temp_json(self, base())
        good = Path(path).with_name("good.txt")
        bad = Path(path).with_name("bad.txt")
        data = support.fixture_data()
        sections, _ = render_sections(base(), data)
        good.write_text(whiteboard_text(base(), sections))
        bad.write_text(whiteboard_text(base(), sections).replace("8 Box Jumps (20 in)", "8"))
        common = [path, "--data-dir", support.FIXTURE_DATA, "--total", "60",
                  "--block", "warmup=12", "--block", "boxing=15", "--block", "briefing=5",
                  "--block", "wod=18", "--block", "cooldown=10", "--interval", "boxing=4x3/1", "--json"]
        code, out, _ = support.run_script("render_wod", *common, "--check-text", good)
        report = json.loads(out)
        self.assertEqual((code, report["result"]["text_check"]["complete"]), (0, True))
        code, out, _ = support.run_script("render_wod", *common, "--check-text", bad)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["result"]["text_check"]["missing_lines"], ["8 Box Jumps (20 in)"])

    def test_block_without_total_is_input_error(self):
        path = support.write_temp_json(self, base())
        code, _, _ = support.run_script("render_wod", path, "--data-dir", support.FIXTURE_DATA, "--block", "wod=18")
        self.assertEqual(code, 2)


@unittest.skipUnless(REAL_DRAFT.exists(), "drafts/2026-11-09.json 없음 (drafts/는 git 제외)")
class RealDraftTest(unittest.TestCase):
    """실제 data/와 실제 초안으로 최종 출력이 완전한지 확인한다."""

    def test_real_draft_output_complete(self):
        draft = json.loads(REAL_DRAFT.read_text(encoding="utf-8"))
        data = support.common.load_data(support.REAL_DATA)
        errors, _, result = build(draft, data)
        self.assertEqual([e for e in errors if e["source"] == "render_wod"], [])
        text = result["whiteboard"]
        self.assertEqual(missing_lines(text, draft, data), [])
        expected = len(draft["movements"]) + sum(len(v) for v in draft["scales"].values())
        movement_lines = [ln for ln in text.splitlines() if LINE_RE.match(ln)]
        self.assertEqual(len(movement_lines), expected)
        for level in "ABC":
            self.assertIn(f"Scale {level}", text.splitlines())


if __name__ == "__main__":
    unittest.main()
