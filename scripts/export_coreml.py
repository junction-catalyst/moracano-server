# coremltools 9.0은 torch<=2.7만 지원하므로 프로젝트 venv(torch 2.13)가 아닌 격리 환경에서 실행한다:
#   uv run --isolated --no-project --with torch==2.7.1 --with transformers==4.46.3 --with coremltools==9.0 \
#     --with "numpy<2.3" --with soundfile python scripts/export_coreml.py --out artifacts/coreml
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import coremltools as ct
import numpy as np
import torch
from coremltools.optimize.coreml import (
    OpLinearQuantizerConfig,
    OpPalettizerConfig,
    OptimizationConfig,
    linear_quantize_weights,
    palettize_weights,
)
from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from moracano_ai.spec import ALIGNMENT_SPEC, PARITY_TOLERANCES  # noqa: E402

SKIP_OPS = ("feature_extractor", "lm_head")


class CTCLogProbs(torch.nn.Module):
    def __init__(self, model: Wav2Vec2ForCTC, normalize: bool):
        super().__init__()
        self.model = model
        self.normalize = normalize

    def forward(self, audio: torch.Tensor) -> torch.Tensor:
        x = audio
        if self.normalize:
            x = (x - x.mean(dim=-1, keepdim=True)) / torch.sqrt(x.var(dim=-1, keepdim=True, unbiased=False) + 1e-7)
        return torch.log_softmax(self.model(x).logits, dim=-1)


def load_traceable(name: str, normalize: bool) -> CTCLogProbs:
    model = Wav2Vec2ForCTC.from_pretrained(name, attn_implementation="eager")
    model.config.layerdrop = 0.0
    model.config.apply_spec_augment = False
    model.eval()
    conv = model.wav2vec2.encoder.pos_conv_embed.conv
    if hasattr(conv, "parametrizations"):
        torch.nn.utils.parametrize.remove_parametrizations(conv, "weight")
    else:
        torch.nn.utils.remove_weight_norm(conv)
    return CTCLogProbs(model, normalize).eval()


def compress(mlmodel, variant: str):
    skip = {name: None for name in ct.optimize.coreml.get_weights_metadata(mlmodel) if any(s in name for s in SKIP_OPS)}
    if variant == "int8":
        cfg = OpLinearQuantizerConfig(mode="linear_symmetric", dtype="int8", granularity="per_channel")
        return linear_quantize_weights(mlmodel, OptimizationConfig(global_config=cfg, op_name_configs=skip))
    if variant == "int4b32":
        cfg = OpLinearQuantizerConfig(mode="linear_symmetric", dtype="int4", granularity="per_block", block_size=32)
        return linear_quantize_weights(mlmodel, OptimizationConfig(global_config=cfg, op_name_configs=skip))
    bits = int(variant[3])
    cfg = OpPalettizerConfig(nbits=bits, mode="kmeans", granularity="per_grouped_channel", group_size=16)
    return palettize_weights(mlmodel, OptimizationConfig(global_config=cfg, op_name_configs=skip))


def dir_size_mb(path: Path) -> float:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) / 1e6


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=ALIGNMENT_SPEC["model"])
    ap.add_argument("--out", default="artifacts/coreml")
    ap.add_argument("--variants", default="fp16,int8", help="comma separated: fp16,int8,int4b32,pal4g16,pal6g16")
    ap.add_argument("--external-norm", action="store_true")
    ap.add_argument("--check-wav", action="append", default=[], help="wav to diff traced vs eager log-probs")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    wrapper = load_traceable(args.model, normalize=not args.external_norm)
    example = torch.randn(1, 64000)
    with torch.no_grad():
        traced = torch.jit.trace(wrapper, example)
        for wav in args.check_wav:
            import soundfile as sf
            data, _ = sf.read(wav, dtype="float32")
            x = torch.from_numpy(data)[None]
            diff = (traced(x) - wrapper(x)).abs().max().item()
            print(f"traced vs eager max abs log-prob diff on {wav}: {diff:.2e}")

    mlmodel = ct.convert(
        traced,
        convert_to="mlprogram",
        inputs=[ct.TensorType("audio", shape=(1, ct.RangeDim(8000, 240000, default=64000)), dtype=np.float32)],
        outputs=[ct.TensorType("log_probs", dtype=np.float32)],
        compute_precision=ct.precision.FLOAT16,
        compute_units=ct.ComputeUnit.ALL,
        minimum_deployment_target=ct.target.iOS18,
    )
    sizes = {}
    for variant in args.variants.split(","):
        packaged = mlmodel if variant == "fp16" else compress(mlmodel, variant)
        path = out / f"KoreanJamoCTC_{variant}.mlpackage"
        shutil.rmtree(path, ignore_errors=True)
        packaged.save(str(path))
        sizes[variant] = round(dir_size_mb(path), 1)
        print(f"{path.name}: {sizes[variant]} MB")

    processor = Wav2Vec2Processor.from_pretrained(args.model)
    with open(out / "vocab.json", "w") as f:
        json.dump(processor.tokenizer.get_vocab(), f, ensure_ascii=False, indent=1)
    spec = {**ALIGNMENT_SPEC, "normalization_inside_model": not args.external_norm,
            "artifact_sizes_mb": sizes, "parity_tolerances": PARITY_TOLERANCES}
    with open(out / "alignment_spec.json", "w") as f:
        json.dump(spec, f, ensure_ascii=False, indent=1)
    with open(out / "sha256sums.txt", "w") as f:
        for p in sorted(out.rglob("*")):
            if p.is_file() and p.suffix != ".txt":
                f.write(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
