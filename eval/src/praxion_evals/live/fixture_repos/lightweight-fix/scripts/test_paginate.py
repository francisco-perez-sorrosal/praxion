from paginate import page


def test_first_page():
    assert page(list(range(10)), 1, 3) == [0, 1, 2]
