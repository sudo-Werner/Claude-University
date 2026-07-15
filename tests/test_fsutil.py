from backend import fsutil


def test_write_text_atomic_creates_and_replaces(tmp_path):
    target = tmp_path / "course.json"
    fsutil.write_text_atomic(target, '{"a": 1}')
    assert target.read_text() == '{"a": 1}'
    fsutil.write_text_atomic(target, '{"a": 2}')
    assert target.read_text() == '{"a": 2}'
    assert list(tmp_path.iterdir()) == [target]  # no .tmp leftover
