import numpy as np

from app.embeddings.cache import load_cache, save_cache


def test_cache_interrupt_checksum_and_model_change(tmp_path):
    path, metadata = tmp_path / "vectors.npy", tmp_path / "vectors.json"
    model = {"name": "fixture", "revision": "1", "dimension": 2}
    rows = [["chunk-1", "hash-1"]]
    vectors = np.array([[0.6, 0.8]], dtype=np.float32)
    save_cache(path, metadata, model, rows, vectors)
    assert np.allclose(load_cache(path, metadata, model)[tuple(rows[0])], vectors[0])
    assert load_cache(path, metadata, {**model, "revision": "2"}) == {}
    path.write_bytes(b"interrupted")
    assert load_cache(path, metadata, model) == {}
    save_cache(path, metadata, model, rows, vectors)
    metadata.write_text("{")
    assert load_cache(path, metadata, model) == {}
