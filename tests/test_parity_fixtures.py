import json
import os
import sys
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "parity"
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

# 모델 로드(~20초, HF 캐시 필요)가 들어가므로 기본 테스트에서는 건너뛰고 MORACANO_PARITY_TEST=1일 때만 돈다.
# Python 기준 구현이 바뀌어 커밋된 픽스처와 어긋나면 여기서 잡힌다(Swift 쪽이 보는 기준값이 바뀐 것이므로).
pytestmark = pytest.mark.skipif(not os.environ.get("MORACANO_PARITY_TEST"), reason="set MORACANO_PARITY_TEST=1")


def test_sample_fixture_matches_reference_pipeline(tmp_path):
    from compare_parity import compare_pair
    from export_parity_fixtures import export_one
    from moracano_ai.align import load_aligner
    from moracano_ai.spec import PARITY_TOLERANCES as T

    ref = json.load(open(FIXTURE_DIR / "sample.json"))
    model, processor = load_aligner()
    cand = export_one(FIXTURE_DIR / "sample.wav", ref["prompt_raw"], tmp_path, "sample", model, processor,
                      processor.tokenizer.get_vocab())
    acc = {k: [] for k in ("frame_argmax", "token_exact", "syl_time", "speech_end", "voicing", "f0_median",
                           "intensity", "trend", "labels", "haptic", "feat_pitch_slope_end")}
    acc.update({f"feat_{k}": [] for k in T["feature_rel"]})
    acc["token_maxdiff"] = 0
    compare_pair(ref, cand, acc)
    assert acc["frame_argmax"][0] >= T["frame_argmax_agreement_min"]
    assert acc["token_maxdiff"] <= T["token_start_max_frame_diff"]
    assert all(acc["syl_time"])
    assert acc["labels"] == [True]
