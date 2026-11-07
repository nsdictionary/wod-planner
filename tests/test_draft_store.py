import json
import tempfile
import unittest
from pathlib import Path

import support
from support import codes
from common import CODE_LEN, sha256_json
from draft_store import commit, status

A = {"date": "2026-11-10", "format": "AMRAP", "duration_min": 12, "movements": [{"id": "box_jump", "reps": 15}]}
B = dict(A, duration_min=14)


class DraftStoreTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.draft = self.dir / "2026-11-10.json"
        self.cand = self.dir / "2026-11-10.candidate.json"

    def put_candidate(self, d):
        self.cand.write_text(json.dumps(d), encoding="utf-8")

    def test_first_commit_creates_draft(self):
        self.put_candidate(A)
        errors, _, r = commit(self.dir, "2026-11-10")
        self.assertEqual((errors, r["action"]), ([], "created"))
        self.assertEqual(json.loads(self.draft.read_text()), A)
        self.assertEqual(r["approval_code"], sha256_json(A)[:CODE_LEN])
        self.assertFalse(self.cand.exists())

    def test_existing_draft_not_overwritten_by_default(self):
        self.draft.write_text(json.dumps(A))
        before = self.draft.read_text()
        self.put_candidate(B)
        errors, _, r = commit(self.dir, "2026-11-10")
        self.assertEqual(codes(errors), ["draft_exists"])
        self.assertEqual(r["action"], "refused")
        self.assertEqual(self.draft.read_text(), before)
        self.assertTrue(self.cand.exists())                               # 후보도 남아 있음 (코치 선택 대기)

    def test_identical_candidate_is_noop(self):
        self.draft.write_text(json.dumps(A))
        self.put_candidate(A)
        errors, _, r = commit(self.dir, "2026-11-10")
        self.assertEqual((errors, r["action"]), ([], "unchanged"))

    def test_keep_existing_discards_candidate(self):
        self.draft.write_text(json.dumps(A))
        self.put_candidate(B)
        errors, _, r = commit(self.dir, "2026-11-10", keep_existing=True)
        self.assertEqual((errors, r["action"]), ([], "kept_existing"))
        self.assertEqual(json.loads(self.draft.read_text()), A)
        self.assertFalse(self.cand.exists())

    def test_new_version_preserves_old_draft_and_ledger(self):
        self.draft.write_text(json.dumps(A))
        ledger = self.dir / "2026-11-10.history.json"
        ledger.write_text('{"schema": "autofix-ledger/1", "runs": []}')
        self.put_candidate(B)
        errors, _, r = commit(self.dir, "2026-11-10", new_version=True)
        self.assertEqual((errors, r["action"]), ([], "new_version"))
        self.assertEqual(json.loads(self.draft.read_text()), B)
        v1 = self.dir / "versions" / "2026-11-10.v1.json"
        self.assertEqual(json.loads(v1.read_text()), A)                    # 복구 가능
        self.assertTrue((self.dir / "versions" / "2026-11-10.v1.history.json").exists())
        self.assertFalse(ledger.exists())                                  # 새 초안은 새 원장으로 시작
        _, _, st = status(self.dir, "2026-11-10")
        self.assertEqual(st["approval_code"], sha256_json(B)[:CODE_LEN])
        self.assertEqual([(v["version"], v["approval_code"]) for v in st["versions"]],
                         [(1, sha256_json(A)[:CODE_LEN])])
        # 두 번째 새 버전 → v2
        self.put_candidate(dict(A, duration_min=10))
        commit(self.dir, "2026-11-10", new_version=True)
        self.assertEqual([v["version"] for v in status(self.dir, "2026-11-10")[2]["versions"]], [1, 2])

    def test_candidate_date_must_match(self):
        self.put_candidate(dict(A, date="2026-11-11"))
        with self.assertRaises(support.common.InputError):
            commit(self.dir, "2026-11-10")

    def test_cli_refusal_exit_1(self):
        self.draft.write_text(json.dumps(A))
        self.put_candidate(B)
        code, out, _ = support.run_script("draft_store", "commit", "2026-11-10", "--drafts-dir", self.dir)
        self.assertEqual(code, 1)
        self.assertIn("덮어쓰지 않았습니다", out)
        self.assertEqual(json.loads(self.draft.read_text()), A)


if __name__ == "__main__":
    unittest.main()
