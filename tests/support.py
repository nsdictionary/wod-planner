"""테스트 공통 도우미. 실제 data/는 읽기만 하고, 계산 검증은 tests/fixtures/data/의 가상 값으로 한다."""

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"
FIXTURE_DATA = FIXTURES / "data"
REAL_DATA = ROOT / "data"
EXAMPLE_DRAFT = FIXTURES / "drafts" / "plan_example_amrap.json"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import common  # noqa: E402

_fixture_cache = None


def fixture_data():
    """픽스처 데이터의 복사본 (테스트에서 마음대로 수정해도 됨)."""
    global _fixture_cache
    if _fixture_cache is None:
        _fixture_cache = common.load_data(FIXTURE_DATA)
    return copy.deepcopy(_fixture_cache)


def example_draft(**overrides):
    draft = json.loads(EXAMPLE_DRAFT.read_text(encoding="utf-8"))
    draft.update(overrides)
    return common.validate_draft(draft)


def draft(movements, **fields):
    base = {"date": "2026-11-10", "format": "AMRAP", "duration_min": 12, "expected_athletes": 12,
            "movements": movements}
    base.update(fields)
    return common.validate_draft(base)


def codes(issues):
    return [i["code"] for i in issues]


def write_temp_json(test, obj, raw=None):
    """임시 파일에 JSON(또는 raw 문자열)을 쓰고 경로를 돌려준다. 테스트 종료 시 삭제."""
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    path = Path(tmp.name) / "draft.json"
    path.write_text(raw if raw is not None else json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return path


def run_script(name, *args):
    """스크립트를 별도 프로세스로 실행 → (종료 코드, stdout, stderr)."""
    proc = subprocess.run([sys.executable, str(SCRIPTS / f"{name}.py"), *map(str, args)],
                          capture_output=True, text=True, cwd=ROOT)
    return proc.returncode, proc.stdout, proc.stderr
