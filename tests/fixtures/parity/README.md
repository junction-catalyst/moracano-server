# Parity fixtures

`sample.json` / `sample.wav` are the reference outputs of the Python pipeline for the TTS utterance "뭐라카노"
(schema: see `scripts/export_parity_fixtures.py`). The 40 AI-Hub fixtures live on the GPU server under
`artifacts/parity/py_fp32/` (AI-Hub audio cannot be redistributed); ask for a private copy.

Check a Swift dump against the reference:

    uv run python scripts/compare_parity.py artifacts/parity/py_fp32 <dir with the same *.json schema>

Regenerate after changing the Python pipeline (and re-commit `sample.*`):

    uv run python scripts/export_parity_fixtures.py --wav "tests/fixtures/sample.wav:뭐라카노" --out /tmp/parity
