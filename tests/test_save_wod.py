import json
import os
import tempfile
import unittest
from pathlib import Path

import support
from support import codes
from autofix import append_run, autofix, default_ledger_path
from common import CODE_LEN, atomic_write_text, dump_json, sha256_json
from save_wod import check, save

CLEAN = {"date": "2026-11-10", "format": "AMRAP", "duration_min": 12, "expected_athletes": 6,
         "movements": [{"id": "box_jump", "reps": 15, "load": "24/20 in"}],
         "scales": {lv: [{"id": "box_jump", "reps": 10, "load": "20 in"}] for lv in "ABC"}}


class SaveBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.drafts = self.root / "drafts"
        self.wods = self.root / "wods"
        self.drafts.mkdir()
        self.data = support.fixture_data()

    def write_draft(self, draft, name="2026-11-10.json"):
        p = self.drafts / name
        p.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
        return p

    def code(self, draft):
        return sha256_json(draft)[:CODE_LEN]


class RefuseTest(SaveBase):
    def test_wrong_or_missing_approval_code_is_refused(self):
        p = self.write_draft(CLEAN)
        for bad in ("", "yes", "approved", "0" * CODE_LEN):
            errors, _, result = save(p, self.wods, self.data, bad, "저장")
            self.assertIn("draft_code_mismatch", codes(errors))
            self.assertFalse(result["saved"])
        self.assertFalse(self.wods.exists())

    def test_approved_field_in_json_is_not_approval(self):
        d = dict(CLEAN, approved=True, approved_by="coach")
        p = self.write_draft(d)
        errors, _, _ = save(p, self.wods, self.data, "", "저장")
        self.assertIn("draft_code_mismatch", codes(errors))
        self.assertFalse(self.wods.exists())

    def test_coach_message_required(self):
        p = self.write_draft(CLEAN)
        with self.assertRaises(support.common.InputError):
            save(p, self.wods, self.data, self.code(CLEAN), "  ")

    def test_validation_failure_blocks_save(self):
        d = dict(CLEAN, duration_min=35)                                # 30분 초과
        p = self.write_draft(d)
        errors, _, _ = save(p, self.wods, self.data, self.code(d), "저장")
        self.assertIn("validation_failed", codes(errors))
        self.assertFalse((self.wods / "2026-11-10.json").exists())

    def test_unresolved_exact_shortage_blocks_save(self):
        d = dict(CLEAN, movements=[{"id": "row", "reps": 250}],
                 scales={lv: [{"id": "row", "reps": 200}] for lv in "ABC"})   # 로잉 5대(정확) vs 6명
        p = self.write_draft(d)
        errors, _, result = check(p, self.wods, self.data)
        self.assertIn("unresolved_shortage", codes(errors))
        self.assertFalse(result["saveable"])
        errors, _, _ = save(p, self.wods, self.data, self.code(d), "저장")
        self.assertIn("validation_failed", codes(errors))
        self.assertFalse(self.wods.exists())

    def test_warnings_need_explicit_acceptance_code(self):
        d = dict(CLEAN, movements=[{"id": "toes_to_bar", "reps": 10}],
                 scales={lv: [{"id": "v_up", "reps": 10}] for lv in "ABC"})   # 풀업바 약 8(추정) 경고
        p = self.write_draft(d)
        _, warnings, info = check(p, self.wods, self.data)
        self.assertTrue(warnings)
        self.assertTrue(info["warnings_code"])
        errors, _, _ = save(p, self.wods, self.data, self.code(d), "저장")
        self.assertIn("warnings_not_accepted", codes(errors))
        errors, _, _ = save(p, self.wods, self.data, self.code(d), "저장", accept_warnings="deadbeef0000")
        self.assertIn("warnings_not_accepted", codes(errors))
        self.assertFalse(self.wods.exists())
        errors, _, result = save(p, self.wods, self.data, self.code(d), "경고 확인, 저장",
                                 accept_warnings=info["warnings_code"])
        self.assertEqual(errors, [])
        rec = json.loads((self.wods / "2026-11-10.json").read_text())
        self.assertEqual(rec["approval"]["accepted_warnings_code"], info["warnings_code"])
        self.assertEqual(len(rec["approval"]["accepted_warnings"]), len(warnings))

    def test_draft_changed_after_approval_is_refused(self):
        p = self.write_draft(CLEAN)
        approved = check(p, self.wods, self.data)[2]["approval_code"]
        changed = dict(CLEAN, duration_min=14)
        self.write_draft(changed)                                        # 승인 뒤 초안 변경
        errors, _, _ = save(p, self.wods, self.data, approved, "저장")
        self.assertIn("draft_code_mismatch", codes(errors))
        self.assertFalse(self.wods.exists())


class SaveTest(SaveBase):
    def test_save_after_approval_writes_record(self):
        p = self.write_draft(CLEAN)
        info = check(p, self.wods, self.data)[2]
        self.assertTrue(info["saveable"])
        errors, warnings, result = save(p, self.wods, self.data, info["approval_code"], "확정, 저장해 주세요",
                                        accept_warnings=info["warnings_code"])
        self.assertEqual(errors, [])
        self.assertTrue(result["saved"])
        path = self.wods / "2026-11-10.json"
        rec = json.loads(path.read_text())
        self.assertEqual(rec["schema"], "wod-record/1")
        self.assertEqual(rec["date"], "2026-11-10")
        self.assertEqual(rec["wod"], CLEAN)
        self.assertEqual(rec["approval"]["draft_sha256"], sha256_json(CLEAN))
        self.assertEqual(rec["approval"]["coach_message"], "확정, 저장해 주세요")
        self.assertRegex(rec["approved_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")
        self.assertEqual(result["approved_at"], rec["approved_at"])
        self.assertIn("A 10 Box Jumps", rec["whiteboard"])
        self.assertTrue(rec["validation"]["checks"])
        self.assertEqual(rec["summary"]["patterns"], ["legs"])
        self.assertEqual([f.name for f in self.wods.iterdir()], ["2026-11-10.json"])   # 임시 파일 안 남음

    def test_full_sha_also_accepted(self):
        p = self.write_draft(CLEAN)
        info = check(p, self.wods, self.data)[2]
        errors, _, _ = save(p, self.wods, self.data, sha256_json(CLEAN), "저장",
                            accept_warnings=info["warnings_code"])
        self.assertEqual(errors, [])

    def test_same_date_not_overwritten_and_replace_needs_record_code(self):
        p = self.write_draft(CLEAN)
        info = check(p, self.wods, self.data)[2]
        save(p, self.wods, self.data, info["approval_code"], "저장", accept_warnings=info["warnings_code"])
        path = self.wods / "2026-11-10.json"
        original = path.read_text()

        new = dict(CLEAN, duration_min=14)
        self.write_draft(new)
        info2 = check(p, self.wods, self.data)[2]
        self.assertIsNotNone(info2["existing_record"])
        errors, _, _ = save(p, self.wods, self.data, info2["approval_code"], "저장",
                            accept_warnings=info2["warnings_code"])
        self.assertIn("record_exists", codes(errors))
        errors, _, _ = save(p, self.wods, self.data, info2["approval_code"], "저장",
                            accept_warnings=info2["warnings_code"], replace_existing="0" * CODE_LEN)
        self.assertIn("record_exists", codes(errors))
        self.assertEqual(path.read_text(), original)

        errors, _, result = save(p, self.wods, self.data, info2["approval_code"], "기존 기록 바꿔서 저장",
                                 accept_warnings=info2["warnings_code"],
                                 replace_existing=info2["existing_record"]["record_code"])
        self.assertEqual(errors, [])
        self.assertEqual(json.loads(path.read_text())["wod"]["duration_min"], 14)
        archived = list((self.wods / "archive").iterdir())
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0].read_text(), original)               # 이전 기록 보존

    def test_record_includes_autofix_history(self):
        d = dict(CLEAN, movements=[{"id": "row", "reps": 250}],
                 scales={lv: [{"id": "row", "reps": 200}] for lv in "ABC"})
        _, _, r1 = autofix(d, self.data)
        p = self.write_draft(r1["final_draft"])
        ledger = append_run(None, d, r1, at="2026-11-07T10:00:00+09:00")
        atomic_write_text(default_ledger_path(p), dump_json(ledger), overwrite=True)
        info = check(p, self.wods, self.data)[2]
        self.assertEqual(info["autofix_history"]["attempts_total"], 1)
        save(p, self.wods, self.data, info["approval_code"], "저장", accept_warnings=info["warnings_code"])
        rec = json.loads((self.wods / "2026-11-10.json").read_text())
        self.assertEqual(rec["autofix"]["original_draft"], d)
        self.assertFalse(rec["autofix"]["stale"])
        self.assertEqual(rec["autofix"]["summary"]["changes"][0]["before"]["id"], "row")

    def test_atomic_write_no_clobber(self):
        path = self.root / "x.json"
        atomic_write_text(path, "a")
        with self.assertRaises(FileExistsError):
            atomic_write_text(path, "b")
        self.assertEqual(path.read_text(), "a")
        self.assertEqual(os.listdir(self.root).count("x.json"), 1)
        self.assertFalse([f for f in os.listdir(self.root) if f.endswith(".tmp")])


class IntegrityNotApprovalTest(SaveBase):
    def test_record_states_approval_is_not_proven(self):
        p = self.write_draft(CLEAN)
        info = check(p, self.wods, self.data)[2]
        self.assertEqual(info["draft_code"], info["approval_code"])
        save(p, self.wods, self.data, info["draft_code"], "저장", accept_warnings=info["warnings_code"])
        a = json.loads((self.wods / "2026-11-10.json").read_text())["approval"]
        self.assertEqual(a["method"], "agent_reported")
        self.assertFalse(a["coach_message_verified"])
        self.assertIn("증명하지 않는다", a["note"])
        self.assertEqual(a["draft_code"], info["draft_code"])

    def test_code_is_derivable_from_draft_alone(self):
        # 한계 문서화: 초안 코드는 초안만 있으면 계산된다 → 사람 승인 증명이 될 수 없다
        p = self.write_draft(CLEAN)
        self.assertEqual(check(p, self.wods, self.data)[2]["draft_code"], sha256_json(CLEAN)[:CODE_LEN])


class CliTest(SaveBase):
    def test_cli_requires_approve_and_never_touches_real_wods(self):
        p = self.write_draft(CLEAN)
        code, _, err = support.run_script("save_wod", "save", p, "--wods-dir", self.wods,
                                          "--data-dir", support.FIXTURE_DATA, "--coach-message", "저장")
        self.assertEqual(code, 2)                                        # argparse: --draft-code 필수
        code, out, _ = support.run_script("save_wod", "check", p, "--wods-dir", self.wods,
                                          "--data-dir", support.FIXTURE_DATA, "--json")
        info = json.loads(out)["result"]
        self.assertEqual(code, 0)
        args = ["save", p, "--wods-dir", self.wods, "--data-dir", support.FIXTURE_DATA, "--json",
                "--draft-code", info["draft_code"], "--coach-message", "저장"]
        if info["warnings_code"]:
            args += ["--accept-warnings", info["warnings_code"]]
        code, out, _ = support.run_script("save_wod", *args)
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["result"]["saved"])
        code, _, _ = support.run_script("save_wod", *args)
        self.assertEqual(code, 1)                                        # 같은 날짜 두 번째 저장 거부
        legacy = [a if a != "--draft-code" else "--approve" for a in args]
        code, out, _ = support.run_script("save_wod", *legacy)          # 예전 인자 이름도 같은 뜻
        self.assertIn("record_exists", [e["code"] for e in json.loads(out)["errors"]])
        self.assertFalse((support.ROOT / "wods" / "2026-11-10.json").exists())


if __name__ == "__main__":
    unittest.main()
