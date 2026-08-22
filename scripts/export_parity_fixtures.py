import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

sys.path.insert(0, str(Path(__file__).parent))
from validate_alignment import MFA, clean_prompt, load_corpus_meta, load_json_utts, pick_samples  # noqa: E402

from moracano_ai.align import (  # noqa: E402
    ONSET_LAG_SEC,
    align_tokens,
    ctc_log_probs,
    finalize_spans,
    load_aligner,
    load_waveform,
    normalize_prompt,
    prepare_tokens,
    raw_syllable_spans,
)
from moracano_ai.direction import placeholder_pca_coord  # noqa: E402
from moracano_ai.features import build_syllables_with_trend, compute_features, semitone_track  # noqa: E402
from moracano_ai.haptic import build_ahap_pattern  # noqa: E402
from moracano_ai.labels import generate_labels  # noqa: E402
from moracano_ai.prosody import (  # noqa: E402
    glissando_threshold,
    intensity_track,
    load_sound,
    pitch_bounds,
    pitch_contour,
    segment_track,
    slope_per_sec,
    speech_end,
)
from moracano_ai.quant_sim import VARIANTS, apply_variant  # noqa: E402
from moracano_ai.spec import ALIGNMENT_SPEC, PARITY_TOLERANCES  # noqa: E402


def round_list(values, digits: int = 4) -> list:
    return [None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), digits) for v in values]


def export_one(wav_path: Path, prompt_raw: str, out_dir: Path, name: str, model, processor, vocab: dict) -> dict:
    waveform, sr = load_waveform(str(wav_path))
    samples = waveform.squeeze(0).numpy()
    sf.write(out_dir / f"{name}.wav", samples, sr, subtype="PCM_16")

    prompt = normalize_prompt(prompt_raw)
    syllables, tokens = prepare_tokens(prompt, vocab)
    token_ids = [vocab[tok] for _, tok in tokens]
    log_probs = ctc_log_probs(waveform, sr, model, processor)
    frames = align_tokens(log_probs, token_ids, processor.tokenizer.pad_token_id)
    frame_duration = samples.shape[-1] / sr / log_probs.shape[0]
    raw = raw_syllable_spans(syllables, tokens, frames, frame_duration)
    end = speech_end(samples, sr, after=raw[-1]["start"])
    aligned = finalize_spans(raw, samples.shape[-1] / sr, end)

    sound = load_sound(str(out_dir / f"{name}.wav"))
    floor, ceiling = pitch_bounds(sound)
    times, f0 = pitch_contour(sound)
    st = semitone_track(aligned, times, f0)
    int_times, int_values = intensity_track(samples, sr)
    syllables_out = build_syllables_with_trend(aligned, times, f0)
    features = compute_features(aligned, times, f0)
    path_logprob = float(sum(log_probs[f, t].item() for (s, e), t in zip(frames, token_ids) for f in range(s, e)))

    per_syllable = []
    for seg in syllables_out:
        seg_times, values = segment_track(times, st, seg["start"], seg["end"])
        duration = seg["end"] - seg["start"]
        per_syllable.append({**seg, "slope_st_per_sec": round(slope_per_sec(seg_times, values), 3),
                             "glissando_threshold": round(glissando_threshold(duration), 3)})

    return {
        "name": name,
        "wav": f"{name}.wav",
        "wav_sha256": hashlib.sha256((out_dir / f"{name}.wav").read_bytes()).hexdigest(),
        "prompt_raw": prompt_raw,
        "prompt": prompt,
        "syllables": syllables,
        "tokens": [{"syllable_index": i, "jamo": tok, "id": vocab[tok]} for i, tok in tokens],
        "sample_rate": sr,
        "sample_count": int(samples.shape[-1]),
        "num_frames": int(log_probs.shape[0]),
        "frame_duration": frame_duration,
        "frame_argmax": log_probs.argmax(dim=-1).tolist(),
        "path_logprob": round(path_logprob, 3),
        "token_frames": [list(f) for f in frames],
        "syllable_spans_raw": [
            {"text": s["text"], "start": round(s["start"], 4), "end": round(s["end"], 4)} for s in raw
        ],
        "onset_lag_sec": ONSET_LAG_SEC,
        "speech_end": end,
        "syllable_spans_final": aligned,
        "pitch_bounds_hz": [floor, ceiling],
        "f0_times": round_list(times),
        "f0_hz": round_list(f0, 2),
        "f0_reference_hz": round(
            float(np.nanmedian(f0[(times >= aligned[0]["start"]) & (times < aligned[-1]["end"])])), 2
        ),
        "intensity_times": round_list(int_times),
        "intensity_db": round_list(int_values, 2),
        "syllables_with_trend": per_syllable,
        "features": features,
        "labels": generate_labels(features),
        "pca_coord": placeholder_pca_coord(features),
        "haptic_pattern": build_ahap_pattern(syllables_out),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="artifacts/parity/py_fp32")
    ap.add_argument("--model", default=None)
    ap.add_argument("--quant", default="none", choices=VARIANTS)
    ap.add_argument("--wav", action="append", default=[], help="extra fixture as path:prompt")
    ap.add_argument("--aihub", action="store_true", help="include AI-Hub utterances (not redistributable)")
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    model, processor = load_aligner(args.model) if args.model else load_aligner()
    model = apply_variant(model, args.quant)
    vocab = processor.tokenizer.get_vocab()

    jobs = [(Path(p), prompt, Path(p).stem) for p, prompt in (w.split(":", 1) for w in args.wav)]
    if args.aihub:
        rows = pick_samples(load_corpus_meta(), args.n * 6, args.seed)
        utts = load_json_utts({r["stem"] for r in rows})
        for r in rows:
            u = utts.get((r["stem"], r["speaker_id"], round(float(r["start"]), 2), round(float(r["end"]), 2)))
            if u is None:
                continue
            prompt, has_marker = clean_prompt(u["dialect_form"])
            if has_marker or not 3 <= len(normalize_prompt(prompt)) <= 12:
                continue
            jobs.append((MFA / "corpus" / r["band"] / r["spkkey"] / f"{r['utt']}.wav", prompt, r["utt"]))
            if len(jobs) - len(args.wav) >= args.n:
                break

    names = []
    for wav_path, prompt, name in jobs:
        try:
            fixture = export_one(wav_path, prompt, out_dir, name, model, processor, vocab)
        except ValueError as e:
            print(f"skip {name}: {e}")
            continue
        with open(out_dir / f"{name}.json", "w") as f:
            json.dump(fixture, f, ensure_ascii=False)
        names.append(name)

    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    manifest = {
        "model": args.model or ALIGNMENT_SPEC["model"], "quant": args.quant, "git": sha, "fixtures": names,
        "spec": ALIGNMENT_SPEC, "tolerances": PARITY_TOLERANCES,
        "torch": torch.__version__,
    }
    with open(out_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(f"wrote {len(names)} fixtures to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
