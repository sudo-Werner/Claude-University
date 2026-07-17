from backend import fsutil


def test_write_text_atomic_creates_and_replaces(tmp_path):
    target = tmp_path / "course.json"
    fsutil.write_text_atomic(target, '{"a": 1}')
    assert target.read_text() == '{"a": 1}'
    fsutil.write_text_atomic(target, '{"a": 2}')
    assert target.read_text() == '{"a": 2}'
    assert list(tmp_path.iterdir()) == [target]  # no .tmp leftover


def test_write_bytes_atomic_creates_and_replaces(tmp_path):
    target = tmp_path / "img.jpg"
    fsutil.write_bytes_atomic(target, b"\xff\xd8\xffabc")
    assert target.read_bytes() == b"\xff\xd8\xffabc"
    fsutil.write_bytes_atomic(target, b"\x89PNGxyz")
    assert target.read_bytes() == b"\x89PNGxyz"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["img.jpg"]  # no .tmp leftover
