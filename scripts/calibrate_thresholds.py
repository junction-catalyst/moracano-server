import json
import sys
from collections import Counter

import numpy as np

from moracano_ai.labels import DEFAULT_THRESHOLDS, generate_labels


def main(paths: list[str]) -> int:
    rows = [p for path in paths for p in json.load(open(path)) if "result" in p]
    print(f"utterances: {len(rows)}")
    for key in ("avg_duration", "npvi", "pitch_slope_end", "speaking_rate", "avg_pitch", "pitch_range"):
        values = np.array([p["result"][key] for p in rows])
        print(f"{key:16s} p50={np.percentile(values, 50):8.3f} p75={np.percentile(values, 75):8.3f} "
              f"p90={np.percentile(values, 90):8.3f} zero={np.mean(values == 0):.0%}")
    labels = Counter(label for p in rows for label in generate_labels(p["result"]))
    print("labels with current thresholds:", {k: f"{v / len(rows):.0%}" for k, v in labels.items()})
    print("current thresholds:", DEFAULT_THRESHOLDS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
