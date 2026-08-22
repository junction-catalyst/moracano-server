import argparse
import csv
import json
import random
import re
import statistics
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch

from moracano_ai.align import forced_align_syllables, load_aligner, load_waveform
from moracano_ai.direction import placeholder_pca_coord
from moracano_ai.features import build_syllables_with_trend, compute_features
from moracano_ai.haptic import build_ahap_pattern
from moracano_ai.labels import generate_labels
from moracano_ai.prosody import load_sound, pitch_contour

MFA = Path("/data/aihub/mfa_work")
LABEL_ZIPS = sorted(Path("/data/aihub/dialect_data/014.한국어_방언_발화_데이터(경상도)").rglob("*라벨링데이터*/*.zip"))
LABEL_ZIP = LABEL_ZIPS[0]
VOWELS = set("ɐɨʌioeuɛ")
MARKERS = re.compile(r"#\S+?#|@\S+|\(\(|\)\)|\{[a-z]+\}")
REPAIR = re.compile(r"(?<!\S)-([가-힣]+)-(?!\S)")
PUNCT = re.compile(r"[.?!,~]")


def clean_prompt(text: str) -> tuple[str, bool]:
    has_marker = bool(MARKERS.search(text))
    text = REPAIR.sub(r"\1", text)
    text = PUNCT.sub("", text)
    return " ".join(text.split()), has_marker


def load_corpus_meta() -> list[dict]:
    with open(MFA / "corpus_meta.csv") as f:
        return list(csv.DictReader(f))


def load_json_utts(stems: set[str]) -> dict:
    utts = {}
    for zp in LABEL_ZIPS:
        with zipfile.ZipFile(zp) as z:
            names = set(z.namelist())
            for stem in stems:
                if f"{stem}.json" not in names:
                    continue
                doc = json.loads(z.read(f"{stem}.json"))
                for u in doc["utterance"]:
                    key = (stem, u["speaker_id"], round(float(u["start"]), 2), round(float(u["end"]), 2))
                    utts[key] = u
    return utts


def parse_textgrid(path: Path) -> dict:
    tiers, current = {}, None
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("name ="):
            current = line.split('"')[1]
            tiers[current] = []
        elif line.startswith("xmin =") and current and tiers[current] is not None and "intervals" not in line:
            xmin = float(line.split("=")[1])
        elif line.startswith("xmax =") and current:
            xmax = float(line.split("=")[1])
        elif line.startswith("text =") and current:
            tiers[current].append((xmin, xmax, line.split('"')[1]))
    return tiers


def is_nucleus(phone: str) -> bool:
    return any(ch in VOWELS for ch in phone)


def syllabify(phones: list[tuple]) -> list[tuple] | None:
    nuclei = [i for i, (_, _, p) in enumerate(phones) if is_nucleus(p)]
    if not nuclei:
        return None
    starts = [0]
    for prev, nxt in zip(nuclei[:-1], nuclei[1:]):
        gap = nxt - prev - 1
        starts.append(nxt if gap <= 1 else prev + 2)
    bounds = starts[1:] + [len(phones)]
    return [(phones[s][0], phones[e - 1][1]) for s, e in zip(starts, bounds)]


def mfa_syllables(tiers: dict) -> tuple[list[str], list[tuple | None]] | None:
    words, phones = tiers["words"], tiers["phones"]
    texts, sylls = [], []
    for ws, we, word in words:
        if not word:
            continue
        inside = [p for p in phones if p[0] >= ws - 1e-6 and p[1] <= we + 1e-6 and p[2]]
        if any(p[2] == "spn" for p in inside):
            # MFA 사전에 없던 어절은 spn(unknown)으로만 정렬돼 음절 경계가 없음: 비교에서만 제외
            segs = [None] * len(word)
        else:
            segs = syllabify(inside)
            if segs is None or len(segs) != len(word):
                return None
        texts.append(word)
        sylls.extend(segs)
    return texts, sylls


def pick_samples(rows: list[dict], n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    by_band = defaultdict(list)
    for r in rows:
        by_band[r["band"]].append(r)
    picked = []
    for band, items in by_band.items():
        rng.shuffle(items)
        picked.extend(items[: n // 2])
    return picked


def run_pipeline(wav_path: str, prompt: str, model, processor) -> tuple[dict, dict]:
    timing = {}
    t0 = time.perf_counter()
    waveform, sr = load_waveform(wav_path)
    aligned = forced_align_syllables(waveform, sr, prompt, model, processor)
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    timing["align"] = time.perf_counter() - t0
    t1 = time.perf_counter()
    times, f0 = pitch_contour(load_sound(wav_path))
    syllables = build_syllables_with_trend(aligned, times, f0)
    features = compute_features(aligned, times, f0)
    out = {
        **features,
        "labels": generate_labels(features),
        "pca_coord": placeholder_pca_coord(features),
        "syllables": syllables,
        "haptic_pattern": build_ahap_pattern(syllables),
    }
    timing["prosody"] = time.perf_counter() - t1
    timing["total"] = time.perf_counter() - t0
    return out, timing


def compare(aligned: list[dict], ref: list[tuple | None]) -> dict:
    ext_ends = [b["start"] for b in aligned[1:]] + [aligned[-1]["end"]]
    pairs = [(a, e, r) for a, e, r in zip(aligned, ext_ends, ref) if r is not None]
    return {
        "onset": [a["start"] - r[0] for a, _, r in pairs],
        "offset": [a["end"] - r[1] for a, _, r in pairs],
        "ext_offset": [e - r[1] for _, e, r in pairs],
        "raw_dur": [a["end"] - a["start"] for a, _, _ in pairs],
        "ext_dur": [e - a["start"] for a, e, _ in pairs],
        "ref_dur": [r[1] - r[0] for _, _, r in pairs],
    }


def summarize(values: list[float]) -> str:
    arr = np.abs(np.array(values))
    return (
        f"n={len(arr)} median={np.median(arr) * 1000:.0f}ms mean={arr.mean() * 1000:.0f}ms "
        f"<=50ms={np.mean(arr <= 0.05):.0%} <=100ms={np.mean(arr <= 0.1):.0%}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--out", default="scripts/out")
    ap.add_argument("--model", default=None)
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = pick_samples(load_corpus_meta(), args.n, args.seed)
    utts = load_json_utts({r["stem"] for r in rows})
    model, processor = load_aligner(args.model) if args.model else load_aligner()
    model.to(args.device)
    vocab = processor.tokenizer.get_vocab()

    status = Counter()
    per_utt, all_cmp, timings = [], defaultdict(list), []
    for i, r in enumerate(rows):
        key = (r["stem"], r["speaker_id"], round(float(r["start"]), 2), round(float(r["end"]), 2))
        u = utts.get(key)
        if u is None:
            status["no_json"] += 1
            continue
        prompt, has_marker = clean_prompt(u["dialect_form"])
        wav = MFA / "corpus" / r["band"] / r["spkkey"] / f"{r['utt']}.wav"
        tg = MFA / "aligned" / r["band"] / r["spkkey"] / f"{r['utt']}.TextGrid"
        n_dialect = sum(1 for e in u["eojeolList"] if e["isDialect"])
        rec = {
            "utt": r["utt"], "band": r["band"], "age": r["age"], "sex": r["sex"], "prompt": prompt,
            "has_marker": has_marker, "n_eojeol": len(u["eojeolList"]), "n_dialect": n_dialect,
            "dur": float(r["end"]) - float(r["start"]),
        }
        try:
            result, timing = run_pipeline(str(wav), prompt, model, processor)
        except ValueError as e:
            status["oov" if "vocab" in str(e) else "span_mismatch"] += 1
            rec["error"] = str(e)[:80]
            per_utt.append(rec)
            continue
        status["ok"] += 1
        if i > 0:
            timings.append(timing)
        rec.update({k: result[k] for k in ("avg_pitch", "pitch_slope_end", "avg_duration", "npvi", "speaking_rate")})
        rec["labels"] = result["labels"]
        aligned = result["syllables"]
        ref = mfa_syllables(parse_textgrid(tg)) if tg.exists() else None
        if ref is None:
            status["mfa_unusable"] += 1
        elif "".join(ref[0]) != prompt.replace(" ", "") or len(ref[1]) != len(aligned):
            status["mfa_text_differs"] += 1
        else:
            cmp = compare(aligned, ref[1])
            status["spn_syllables_skipped"] += sum(1 for x in ref[1] if x is None)
            if cmp["onset"]:
                rec["onset_mae"] = float(np.mean(np.abs(cmp["onset"])))
                rec["ext_dur_ratio"] = float(np.sum(cmp["ext_dur"]) / np.sum(cmp["ref_dur"]))
                rec["raw_dur_ratio"] = float(np.sum(cmp["raw_dur"]) / np.sum(cmp["ref_dur"]))
                for k, v in cmp.items():
                    all_cmp[k].extend(v)
                all_cmp["band"].extend([r["band"]] * len(cmp["onset"]))
                all_cmp["dialect"].extend([n_dialect > 0] * len(cmp["onset"]))
        rec["result"] = result
        per_utt.append(rec)

    print("status:", dict(status))
    print("vocab size:", len(vocab))
    if timings:
        for k in ("align", "prosody", "total"):
            vals = [t[k] for t in timings]
            print(f"latency {k}: median={statistics.median(vals):.3f}s mean={statistics.mean(vals):.3f}s "
                  f"max={max(vals):.3f}s (n={len(vals)}, device={args.device})")
        durs = [p["dur"] for p in per_utt if "result" in p][1:]
        print(f"audio duration: median={statistics.median(durs):.2f}s mean={statistics.mean(durs):.2f}s")
    if all_cmp["onset"]:
        print("onset error vs MFA:", summarize(all_cmp["onset"]))
        print("offset error (raw CTC span end):", summarize(all_cmp["offset"]))
        print("offset error (extended to next onset):", summarize(all_cmp["ext_offset"]))
        print(f"syllable duration: MFA mean={np.mean(all_cmp['ref_dur']) * 1000:.0f}ms "
              f"raw CTC span mean={np.mean(all_cmp['raw_dur']) * 1000:.0f}ms "
              f"extended mean={np.mean(all_cmp['ext_dur']) * 1000:.0f}ms")
        band = np.array(all_cmp["band"])
        dia = np.array(all_cmp["dialect"])
        onset = np.array(all_cmp["onset"])
        for name, mask in (("young", band == "young"), ("old", band == "old"),
                           ("has_dialect_eojeol", dia), ("no_dialect_eojeol", ~dia)):
            print(f"  onset error [{name}]:", summarize(list(onset[mask])))
    worst = sorted([p for p in per_utt if "onset_mae" in p], key=lambda p: -p["onset_mae"])[:10]
    print("worst utterances by onset MAE:")
    for p in worst:
        print(f"  {p['onset_mae'] * 1000:.0f}ms {p['utt']} {p['age']}/{p['sex']} "
              f"dialect={p['n_dialect']} {p['prompt']}")
    with open(out_dir / "per_utt.json", "w") as f:
        json.dump(per_utt, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
