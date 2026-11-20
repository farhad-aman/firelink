import firelink


def test_version_is_a_dotted_string():
    parts = firelink.__version__.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)
