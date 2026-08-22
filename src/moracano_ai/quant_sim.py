import torch
from torch import nn

# coremltools 가중치 압축 패스를 PyTorch 안에서 흉내 내 MFA 대조 하네스로 정확도 손실을 재기 위한 모듈.
# 특징추출 conv 7개와 CTC 헤드(lm_head)는 합쳐 9MB뿐이고 정확도에 민감해 항상 fp16으로 둔다.
SKIP_PREFIXES = ("wav2vec2.feature_extractor", "lm_head")
VARIANTS = ("none", "fp16", "int8", "pal6g16", "pal4g16", "int4b32")


def compressible_params(model: nn.Module):
    for name, module in model.named_modules():
        if name.startswith(SKIP_PREFIXES) or not isinstance(module, (nn.Linear, nn.Conv1d)):
            continue
        yield name, module.weight


def fake_quantize_channel(weight: torch.Tensor, bits: int) -> torch.Tensor:
    # 출력 채널별 대칭 선형 양자화 (coremltools linear_symmetric / per_channel)
    qmax = 2 ** (bits - 1) - 1
    flat = weight.reshape(weight.shape[0], -1)
    scale = flat.abs().amax(dim=1, keepdim=True).clamp_min(1e-8) / qmax
    return (torch.round(flat / scale).clamp(-qmax, qmax) * scale).reshape(weight.shape)


def fake_quantize_block(weight: torch.Tensor, bits: int, block: int) -> torch.Tensor:
    # 입력 축을 block개씩 묶어 스케일을 따로 두는 방식 (coremltools per_block, iOS 18)
    qmax = 2 ** (bits - 1) - 1
    flat = weight.reshape(weight.shape[0], -1)
    pad = (-flat.shape[1]) % block
    padded = torch.nn.functional.pad(flat, (0, pad)).reshape(flat.shape[0], -1, block)
    scale = padded.abs().amax(dim=2, keepdim=True).clamp_min(1e-8) / qmax
    out = (torch.round(padded / scale).clamp(-qmax, qmax) * scale).reshape(flat.shape[0], -1)[:, : flat.shape[1]]
    return out.reshape(weight.shape)


def kmeans_1d(values: torch.Tensor, k: int, iters: int = 20) -> torch.Tensor:
    centroids = torch.quantile(values, torch.linspace(0, 1, k, device=values.device))
    for _ in range(iters):
        assign = torch.bucketize(values, (centroids[1:] + centroids[:-1]) / 2)
        sums = torch.zeros(k, device=values.device).index_add_(0, assign, values)
        counts = torch.zeros(k, device=values.device).index_add_(0, assign, torch.ones_like(values))
        centroids = torch.where(counts > 0, sums / counts.clamp_min(1), centroids)
    assign = torch.bucketize(values, (centroids[1:] + centroids[:-1]) / 2)
    return centroids[assign]


def fake_palettize(weight: torch.Tensor, bits: int, group: int) -> torch.Tensor:
    # 출력 채널 group개씩 묶어 LUT(2^bits개)를 따로 두는 k-means 팔레타이즈 (coremltools per_grouped_channel)
    flat = weight.reshape(weight.shape[0], -1)
    out = torch.empty_like(flat)
    for start in range(0, flat.shape[0], group):
        chunk = flat[start : start + group]
        out[start : start + group] = kmeans_1d(chunk.reshape(-1), 2**bits).reshape(chunk.shape)
    return out.reshape(weight.shape)


def apply_variant(model: nn.Module, variant: str) -> nn.Module:
    if variant == "none":
        return model
    if variant == "fp16":
        return model.half()
    with torch.no_grad():
        for _, weight in compressible_params(model):
            if variant == "int8":
                weight.copy_(fake_quantize_channel(weight, 8))
            elif variant == "int4b32":
                weight.copy_(fake_quantize_block(weight, 4, 32))
            elif variant == "pal6g16":
                weight.copy_(fake_palettize(weight, 6, 16))
            elif variant == "pal4g16":
                weight.copy_(fake_palettize(weight, 4, 16))
            else:
                raise ValueError(f"unknown variant {variant}")
    # 양자화 가중치도 실제 기기에서는 fp16으로 풀려 계산되므로 활성값 정밀도를 맞춘다
    return model.half()


def pad_to_choices(waveform: torch.Tensor, sample_rate: int, seconds: list[float]) -> torch.Tensor:
    # EnumeratedShapes CoreML 모델을 흉내: 정규화 뒤 0으로 다음 허용 길이까지 채운다. 호출자가 T를 잘라야 함
    target = next((int(s * sample_rate) for s in sorted(seconds) if s * sample_rate >= waveform.shape[-1]), None)
    if target is None:
        return waveform
    return torch.nn.functional.pad(waveform, (0, target - waveform.shape[-1]))
