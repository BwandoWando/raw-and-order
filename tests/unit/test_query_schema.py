from raw_and_order.schemas.query import PhotoQuery, SortOrder


def test_filters_only_drops_sort_and_paging() -> None:
    query = PhotoQuery(
        tags=("sea",), sort=SortOrder.CAPTURED_OLDEST, page=3, page_size=99
    )

    assert query.filters_only() == PhotoQuery(tags=("sea",))


def test_equal_filters_compare_equal_whatever_the_page() -> None:
    first = PhotoQuery(text="sunset", page=1)
    later = PhotoQuery(text="sunset", page=5, sort=SortOrder.PROCESSED_NEWEST)

    assert first.filters_only() == later.filters_only()


def test_sort_and_paging_are_not_filters() -> None:
    assert not PhotoQuery(sort=SortOrder.CAPTURED_OLDEST, page=2).has_filters()
    assert PhotoQuery(only_favorites=True).has_filters()
