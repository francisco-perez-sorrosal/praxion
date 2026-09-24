from foo import __doc__ as doc


def test_docstring():
    assert doc == "Return the answer."
