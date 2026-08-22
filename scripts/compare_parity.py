import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from moracano_ai.spec import PARITY_TOLERANCES as T  # noqa: E402


def load_dir(path: Path) -> dict:
    return {p.stem: json.load(open(p)) for p in path.glob("*.json") if p.name != "manifest.json"}


def resample_voicing(times: list, values: list, grid: np.ndarray) -> np.ndarray:
    t = np.array(times)
    v = np.array([np.nan if x is None else x for x in values], dtype=float)
    idx = np.clip(np.searchsorted(t, grid), 0, len(t) - 1)
    return ~np.isnan(v[idx])


def rel_close(a: float, b: float, rel: float) -> bool:
    return abs(a - b) <= rel * max(abs(a), abs(b), 1e-9)


def compare_pair(ref: dict, cand: dict, acc: dict) -> None:
    if ref["num_frames"] == cand["num_frames"]:
        same = np.mean(np.array(ref["frame_argmax"]) == np.array(cand["frame_argmax"]))
    else:
        same = 0.0
    acc["frame_argmax"].append(same)
    diffs = [abs(r[0] - c[0]) for r, c in zip(ref["token_frames"], cand["token_frames"])]
    acc["token_exact"] += [d == 0 for d in diffs]
    acc["token_maxdiff"] = max(acc["token_maxdiff"], max(diffs, default=0))
    for r, c in zip(ref["syllable_spans_final"], cand["syllable_spans_final"]):
        acc["syl_time"].append(abs(r["start"] - c["start"]) <= T["syllable_time_sec"])
        acc["syl_time"].append(abs(r["end"] - c["end"]) <= T["syllable_time_sec"])
    if ref["speech_end"] is not None and cand["speech_end"] is not None:
        acc["speech_end"].append(abs(ref["speech_end"] - cand["speech_end"]) <= T["speech_end_sec"])
    grid = np.arange(0, ref["sample_count"] / ref["sample_rate"], 0.01)
    vr = resample_voicing(ref["f0_times"], ref["f0_hz"], grid)
    vc = resample_voicing(cand["f0_times"], cand["f0_hz"], grid)
    acc["voicing"].append(float(np.mean(vr == vc)))
    rt, rf = np.array(ref["f0_times"]), np.array([np.nan if x is None else x for x in ref["f0_hz"]], dtype=float)
    ct, cf = np.array(cand["f0_times"]), np.array([np.nan if x is None else x for x in cand["f0_hz"]], dtype=float)
    for seg in ref["syllable_spans_final"]:
        a = rf[(rt >= seg["start"]) & (rt < seg["end"])]
        b = cf[(ct >= seg["start"]) & (ct < seg["end"])]
        a, b = a[~np.isnan(a)], b[~np.isnan(b)]
        if len(a) >= 3 and len(b) >= 3:
            acc["f0_median"].append(rel_close(np.median(a), np.median(b), T["f0_syllable_median_rel"]))
    ri = np.array(ref["intensity_db"]) - max(ref["intensity_db"])
    ci = np.array(cand["intensity_db"]) - max(cand["intensity_db"])
    n = min(len(ri), len(ci))
    acc["intensity"].append(float(np.median(np.abs(ri[:n] - ci[:n]))))
    for key, rel in T["feature_rel"].items():
        acc[f"feat_{key}"].append(rel_close(ref["features"][key], cand["features"][key], rel))
    rs, cs = ref["features"]["pitch_slope_end"], cand["features"]["pitch_slope_end"]
    acc["feat_pitch_slope_end"].append(
        abs(rs - cs) <= T["pitch_slope_end"]["abs_st_per_sec"] or rel_close(rs, cs, T["pitch_slope_end"]["rel"])
    )
    acc["trend"] += [r["pitch_trend"] == c["pitch_trend"]
                     for r, c in zip(ref["syllables_with_trend"], cand["syllables_with_trend"])]
    acc["labels"].append(sorted(ref["labels"]) == sorted(cand["labels"]))
    rp, cp = ref["haptic_pattern"]["Pattern"], cand["haptic_pattern"]["Pattern"]
    ok = len(rp) == len(cp)
    for r, c in zip(rp, cp):
        if "Event" in r and "Event" in c:
            ok &= abs(r["Event"]["Time"] - c["Event"]["Time"]) <= T["haptic_time_sec"]
            ok &= abs(r["Event"]["EventDuration"] - c["Event"]["EventDuration"]) <= T["haptic_time_sec"]
            ri_ = r["Event"]["EventParameters"][0]["ParameterValue"]
            ci_ = c["Event"]["EventParameters"][0]["ParameterValue"]
            ok &= abs(ri_ - ci_) <= T["haptic_intensity"]
    acc["haptic"].append(ok)


def main(ref_dir: str, cand_dir: str) -> int:
    ref, cand = load_dir(Path(ref_dir)), load_dir(Path(cand_dir))
    common = sorted(set(ref) & set(cand))
    acc = {k: [] for k in ("frame_argmax", "token_exact", "syl_time", "speech_end", "voicing", "f0_median",
                           "intensity", "trend", "labels", "haptic", "feat_pitch_slope_end")}
    acc.update({f"feat_{k}": [] for k in T["feature_rel"]})
    acc["token_maxdiff"] = 0
    for name in common:
        compare_pair(ref[name], cand[name], acc)
    rows = [
        ("frame_argmax agreement", np.mean(acc["frame_argmax"]), T["frame_argmax_agreement_min"]),
        ("token start exact", np.mean(acc["token_exact"]), T["token_start_exact_min"]),
        ("token start max frame diff", -acc["token_maxdiff"], -T["token_start_max_frame_diff"]),
        ("syllable times within 20ms", np.mean(acc["syl_time"]), T["syllable_time_pass_min"]),
        ("speech_end within 25ms", np.mean(acc["speech_end"]) if acc["speech_end"] else 1.0, T["speech_end_pass_min"]),
        ("voicing agreement", np.mean(acc["voicing"]), T["voicing_agreement_min"]),
        ("f0 syllable median within 3%", np.mean(acc["f0_median"]) if acc["f0_median"] else 1.0,
         T["f0_syllable_median_pass_min"]),
        ("intensity median abs diff dB", -float(np.median(acc["intensity"])), -T["intensity_db"]),
        ("trend agreement", np.mean(acc["trend"]), T["trend_agreement_min"]),
        ("labels identical", np.mean(acc["labels"]), T["labels_identical_min"]),
        ("haptic match", np.mean(acc["haptic"]), T["labels_identical_min"]),
    ] + [(f"feature {k}", np.mean(acc[f"feat_{k}"]), 0.95) for k in list(T["feature_rel"]) + ["pitch_slope_end"]]
    failed = 0
    print(f"fixtures compared: {len(common)} (ref {len(ref)}, cand {len(cand)})")
    for name, value, minimum in rows:
        ok = value >= minimum
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'} {name:32s} {abs(value):7.3f} (min {abs(minimum):.3f})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
