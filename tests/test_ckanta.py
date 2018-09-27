from ckanta import get_version



def test_version():
    value = get_version()
    assert value not in ('', None)

    parts = list(map(lambda p: int(p), value.split('.')))
    assert parts is not None and len(parts) == 3
