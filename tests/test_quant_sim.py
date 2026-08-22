import torch

from moracano_ai.quant_sim import fake_palettize, fake_quantize_block, fake_quantize_channel, pad_to_choices


def test_fake_quantize_channel_keeps_shape_and_bounds_error():
    weight = torch.randn(8, 16)
    out = fake_quantize_channel(weight, 8)
    assert out.shape == weight.shape
    step = weight.abs().amax(dim=1, keepdim=True) / 127
    assert ((out - weight).abs() <= step / 2 + 1e-6).all()


def test_fake_quantize_block_handles_non_multiple_width():
    weight = torch.randn(4, 50)
    out = fake_quantize_block(weight, 4, 32)
    assert out.shape == weight.shape
    assert len(torch.unique(out[0, :32])) <= 15


def test_fake_palettize_limits_unique_values_per_group():
    weight = torch.randn(32, 64)
    out = fake_palettize(weight, 4, 16)
    for start in range(0, 32, 16):
        assert len(torch.unique(out[start : start + 16])) <= 16


def test_pad_to_choices_pads_to_next_length_only():
    wave = torch.ones(1, 16000 * 3)
    assert pad_to_choices(wave, 16000, [2, 4]).shape[-1] == 16000 * 4
    assert pad_to_choices(wave, 16000, [2]).shape[-1] == 16000 * 3
