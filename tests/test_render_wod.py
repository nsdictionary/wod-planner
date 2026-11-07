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
    footnote_line,
    missing_lines,
    movement_line,
    render_sections,
    scale_line_gaps,
    whiteboard_text,
)

REAL_DRAFT = support.ROOT / "drafts" / "2026-11-09.json"
LINE_RE = re.compile(r"^\d+(\.\d+)?m? [A-Z][A-Za-z0-9\- ]+")   # "17 Shuttle Runs", "250m Row", "8 T2B"
SCALE_LINE_RE = re.compile(r"^[ABC] \d")                          # "A 10 Shuttle Runs / 8 T2B / ..."
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
                         '15 Box Jumps (24/20")')
        self.assertEqual(movement_line({"id": "dumbbell_snatch", "reps": 10, "weights": {"dumbbell": [15, 10]}},
                                       self.data), "10 Dumbbell Snatches (15/10 kg)")
        self.assertEqual(movement_line({"id": "wall_ball", "reps": 20}, self.data), "20 Wall Balls (target ~2.3m)")
        self.assertIsNone(movement_line({"id": "pegboard", "reps": 1}, self.data))

    def test_load_other_than_inches_is_kept_as_is(self):
        self.assertEqual(movement_line({"id": "box_jump", "reps": 10, "load": "60 cm"}, self.data), "10 Box Jumps (60 cm)")
        self.assertEqual(movement_line({"id": "box_jump", "reps": 10, "load": "20in"}, self.data), '10 Box Jumps (20")')

    def test_abbreviation_only_when_registered(self):
        self.assertEqual(movement_line({"id": "toes_to_bar", "reps": 8}, self.data), "8 Toes-to-Bar")
        self.assertEqual(movement_line({"id": "toes_to_bar", "reps": 8}, self.data, abbreviate=True), "8 T2B")
        # 약어가 등록되지 않은 동작은 스케일에서도 이름 그대로 (지어내지 않음)
        self.assertEqual(movement_line({"id": "hanging_knee_raise", "reps": 10}, self.data, abbreviate=True),
                         "10 Hanging Knee Raises")
        self.assertEqual(movement_line({"id": "kettlebell_swing", "reps": 15}, self.data, abbreviate=True),
                         "15 Kettlebell Swings")

    def test_shuttle_name_and_footnote_from_data(self):
        self.assertEqual(movement_line({"id": "shuttle_run", "reps": 13}, self.data), "13 Shuttle Runs")
        self.assertEqual(footnote_line("shuttle_run", self.data), "*1 Shuttle Run = 7.5m x 2")
        self.assertIsNone(footnote_line("box_jump", self.data))
        self.data["equipment"]["space"]["shuttle_run"]["one_way_m"] = None     # 왕복 정보 없으면 거리만
        self.assertEqual(footnote_line("shuttle_run", self.data), "*1 Shuttle Run = 15m")
        del self.data["equipment"]["space"]["shuttle_run"]                    # 근거 없으면 각주 없음
        self.assertIsNone(footnote_line("shuttle_run", self.data))

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
        self.assertEqual(sections[0]["lines"], sections[0]["items"])           # Rx는 동작 한 줄씩
        self.assertEqual(len(sections[0]["lines"]), 2)
        for s in sections:
            self.assertEqual(len(s["items"]), 2)
            for it in s["items"]:
                self.assertRegex(it, LINE_RE)
            for ln in s["lines"]:
                self.assertFalse(ln.rstrip().endswith(("/", "×", "+", ",")))
        for s in sections[1:]:                                                 # 스케일은 레벨별 한 줄
            self.assertEqual(s["lines"], [s["name"][-1] + " " + " / ".join(s["items"])])
            self.assertRegex(s["lines"][0], SCALE_LINE_RE)
        self.assertEqual(sections[1]["lines"], ['A 6 T2B / 12 Box Jumps (20")'])
        self.assertEqual(scale_line_gaps(sections), [])

    def test_whiteboard_layout(self):
        d = base([{"id": "shuttle_run", "reps": 13}, {"id": "toes_to_bar", "reps": 12},
                  {"id": "box_jump", "reps": 12, "load": "24/20 in"}], duration_min=15)
        d["scales"] = {
            "A": [{"id": "shuttle_run", "reps": 10}, {"id": "toes_to_bar", "reps": 8}, {"id": "box_jump", "reps": 10, "load": "20 in"}],
            "B": [{"id": "shuttle_run", "reps": 10}, {"id": "hanging_knee_raise", "reps": 10}, {"id": "step_up", "reps": 12, "load": "20 in"}],
            "C": [{"id": "shuttle_run", "reps": 7}, {"id": "v_up", "reps": 10}, {"id": "step_up", "reps": 10, "load": "20 in"}],
        }
        self.data["movements"]["movements"]["step_up"] = dict(self.data["movements"]["movements"]["box_jump"], display="Step-ups")
        sections, errors = render_sections(d, self.data)
        self.assertEqual(errors, [])
        self.assertEqual(whiteboard_text(d, sections, self.data), "\n".join([
            "WOD - AMRAP 15",
            "",
            "13 Shuttle Runs",
            "12 Toes-to-Bar",
            '12 Box Jumps (24/20")',
            "",
            "Scale",
            "",
            'A 10 Shuttle Runs / 8 T2B / 10 Box Jumps (20")',
            'B 10 Shuttle Runs / 10 Hanging Knee Raises / 12 Step-ups (20")',
            'C 7 Shuttle Runs / 10 V-ups / 10 Step-ups (20")',
            "",
            "*1 Shuttle Run = 7.5m x 2",
        ]))

    def test_scale_line_keeps_weights_distance_and_target(self):
        d = base([{"id": "row", "reps": 250}, {"id": "wall_ball", "reps": 20},
                  {"id": "dumbbell_snatch", "reps": 10, "weights": {"dumbbell": [15, 10]}}])
        d["scales"] = {lv: [{"id": "row", "reps": 200}, {"id": "wall_ball", "reps": 15},
                            {"id": "dumbbell_snatch", "reps": 8, "weights": {"dumbbell": [10, 7]}}] for lv in "ABC"}
        sections, errors = render_sections(d, self.data)
        self.assertEqual(errors, [])
        line = sections[1]["lines"][0]
        self.assertEqual(line, "A 200m Row / 15 Wall Balls (target ~2.3m) / 8 Dumbbell Snatches (10/7 kg)")
        self.assertEqual(scale_line_gaps(sections), [])                        # 괄호 안 /는 구분자가 아님

    def test_scale_line_gap_detected(self):
        sections, _ = render_sections(base(), self.data)
        sections[2]["lines"] = ["B 10 Hanging Knee Raises"]                    # 동작 하나 빠짐
        self.assertEqual(len(scale_line_gaps(sections)), 1)

    def test_scale_missing_movement_is_error_and_not_filled(self):
        d = base()
        d["scales"]["C"] = [{"id": "v_up", "reps": 8}]          # Rx는 2개
        sections, errors = render_sections(d, self.data)
        self.assertEqual(codes(errors), ["scale_movement_count_mismatch"])
        self.assertEqual(sections[-1]["items"], ["8 V-ups"])     # 빠진 동작을 지어내지 않음
        self.assertEqual(sections[-1]["lines"], ["C 8 V-ups"])

    def test_adult_without_scales_is_error(self):
        d = base()
        del d["scales"]
        _, errors = render_sections(d, self.data)
        self.assertEqual(codes(errors), ["scale_missing"])

    def test_truncated_copy_is_detected(self):
        d = base()
        sections, _ = render_sections(d, self.data)
        full = whiteboard_text(d, sections, self.data)
        self.assertEqual(missing_lines(full, d, self.data), [])
        truncated = full.replace(' / 8 Box Jumps (20")', "")
        self.assertEqual(missing_lines(truncated, d, self.data), ['C 8 V-ups / 8 Box Jumps (20")'])
        expanded = full.replace("\nScale\n", "\n")                             # "Scale" 제목 누락도 검출
        self.assertEqual(missing_lines(expanded, d, self.data), ["Scale"])

    def test_missing_footnote_is_detected(self):
        d = base([{"id": "shuttle_run", "reps": 13}, {"id": "box_jump", "reps": 15, "load": "24/20 in"}])
        sections, _ = render_sections(d, self.data)
        full = whiteboard_text(d, sections, self.data)
        self.assertIn("*1 Shuttle Run = 7.5m x 2", full)
        self.assertEqual(missing_lines(full.replace("*1 Shuttle Run = 7.5m x 2", ""), d, self.data),
                         ["*1 Shuttle Run = 7.5m x 2"])


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
        self.assertEqual(result["final_text"], whiteboard_text(result["final_draft"], sections, data))
        self.assertNotIn("Row", result["final_text"])
        lines = result["final_text"].splitlines()
        self.assertIn("17 Shuttle Runs", lines)
        self.assertEqual(sum(ln.startswith(f"{lv} 13 Shuttle Runs / ") for lv in "ABC" for ln in lines), 3)
        self.assertEqual(lines[-1], "*1 Shuttle Run = 7.5m x 2")

    def test_stale_autofix_report_is_not_shown(self):
        data = support.fixture_data()
        d = base()
        report = {"result": {"final_draft": base(duration_min=10), "history": [], "changes": []}}
        _, warnings, result = build(d, data, autofix_report=report)
        self.assertIsNone(result["autofix"])
        self.assertIn("autofix_report_mismatch", codes(warnings))


class CumulativeAutofixTest(unittest.TestCase):
    """재검증 후에도 render_wod가 최초 수정 전 상태와 이전 수정 내역을 보여 준다 (Phase 4)."""

    def test_rerun_report_shows_cumulative_changes(self):
        from autofix import append_run, ledger_summary
        data = support.fixture_data()
        d = base([{"id": "row", "reps": 250}, {"id": "box_jump", "reps": 15, "load": "24/20 in"}])
        for lv in "ABC":
            d["scales"][lv][0] = {"id": "row", "reps": 200}
        _, _, r1 = autofix(d, data)
        ledger = append_run(None, d, r1)
        _, _, r2 = autofix(r1["final_draft"], data)
        ledger = append_run(ledger, r1["final_draft"], r2)
        r2["ledger"] = ledger_summary(ledger)
        _, warnings, result = build(r1["final_draft"], data, autofix_report={"result": r2})
        a = result["autofix"]
        self.assertEqual(a["attempts_used"], 0)                          # 이번 실행
        self.assertEqual(a["cumulative"]["attempts_total"], 1)           # 누적
        self.assertEqual(a["before"]["problems"], ["short"])
        self.assertEqual(len(a["changes"]), 1)
        self.assertNotIn("autofix_history_manual_edit", codes(warnings))
        self.assertIn('A 13 Shuttle Runs / 12 Box Jumps (20")', result["whiteboard"].splitlines())   # 한 줄 스케일 형식 유지

    def test_report_without_ledger_still_works(self):
        data = support.fixture_data()
        _, _, r1 = autofix(base(), data)
        _, _, result = build(base(), data, autofix_report={"result": r1})
        self.assertIsNone(result["autofix"]["cumulative"])


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
        good.write_text(whiteboard_text(base(), sections, data))
        bad.write_text(whiteboard_text(base(), sections, data).replace(' / 8 Box Jumps (20")', ""))
        common = [path, "--data-dir", support.FIXTURE_DATA, "--total", "60",
                  "--block", "warmup=12", "--block", "boxing=15", "--block", "briefing=5",
                  "--block", "wod=18", "--block", "cooldown=10", "--interval", "boxing=4x3/1", "--json"]
        code, out, _ = support.run_script("render_wod", *common, "--check-text", good)
        report = json.loads(out)
        self.assertEqual((code, report["result"]["text_check"]["complete"]), (0, True))
        code, out, _ = support.run_script("render_wod", *common, "--check-text", bad)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["result"]["text_check"]["missing_lines"], ['C 8 V-ups / 8 Box Jumps (20")'])

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
        lines = text.splitlines()
        rx_lines = [ln for ln in lines if LINE_RE.match(ln)]
        self.assertEqual(len(rx_lines), len(draft["movements"]))               # Rx는 한 번만
        self.assertEqual(lines.count("Scale"), 1)
        for level in "ABC":
            scale_lines = [ln for ln in lines if ln.startswith(f"{level} ")]
            self.assertEqual(len(scale_lines), 1)                              # 레벨별 한 줄
            self.assertEqual(scale_lines[0].count(" / "), len(draft["scales"][level]) - 1)
        self.assertEqual(scale_line_gaps(result["sections"]), [])
        if any(m["id"] == "shuttle_run" for m in draft["movements"]):
            self.assertIn("*1 Shuttle Run = 7.5m x 2", lines)


if __name__ == "__main__":
    unittest.main()
