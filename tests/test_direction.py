from moracano_ai.direction import normalize, placeholder_pca_coord


def test_normalize_midpoint_is_zero():
    assert normalize(200.0, 100.0, 300.0) == 0.0


def test_normalize_clamped_to_range():
    assert normalize(1000.0, 100.0, 300.0) == 1.0
    assert normalize(-1000.0, 100.0, 300.0) == -1.0


def test_placeholder_pca_coord_shape():
    coord = placeholder_pca_coord({"avg_pitch": 200.0, "npvi": 40.0})
    assert len(coord) == 2
    assert all(isinstance(v, float) for v in coord)
