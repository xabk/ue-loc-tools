"""Paging through a Crowdin listing.

The client defaults its page size to 25 and resolves `limit = limit or
page_size`, so a listing called without a limit returns the first 25 rows and
says nothing about the rest. The projects here hold 6 to 80 files, so the tail
was being dropped silently: a file past the 25th could not be found by name,
and a directory past the 25th was created again instead of reused.
"""

import pytest

from libraries.crowdin import PAGE_LIMIT, fetch_all_pages


def pages(*sizes):
    """A fetch that serves rows from one flat list, and records its requests."""
    total = sum(sizes)
    rows = [{'data': {'id': i, 'name': f'file{i}.po'}} for i in range(total)]
    calls = []

    def fetch(offset, limit):
        calls.append((offset, limit))
        return {'data': rows[offset : offset + limit]}

    return fetch, calls, rows


def test_a_short_listing_takes_one_request():
    fetch, calls, rows = pages(3)

    assert fetch_all_pages(fetch) == rows
    assert calls == [(0, PAGE_LIMIT)]


def test_an_empty_listing_is_an_empty_list():
    fetch, calls, _ = pages(0)

    assert fetch_all_pages(fetch) == []
    assert calls == [(0, PAGE_LIMIT)]


def test_nothing_is_lost_past_the_first_page():
    fetch, calls, rows = pages(PAGE_LIMIT, 7)

    got = fetch_all_pages(fetch)

    assert got == rows
    assert len(got) == PAGE_LIMIT + 7
    assert calls == [(0, PAGE_LIMIT), (PAGE_LIMIT, PAGE_LIMIT)]


def test_a_listing_that_is_exactly_one_page_long_still_terminates():
    """A full page cannot be told from a full-and-there-is-more page, so it
    costs one extra request that comes back empty."""
    fetch, calls, rows = pages(PAGE_LIMIT)

    assert fetch_all_pages(fetch) == rows
    assert calls == [(0, PAGE_LIMIT), (PAGE_LIMIT, PAGE_LIMIT)]


def test_several_full_pages_are_all_collected():
    fetch, calls, rows = pages(PAGE_LIMIT, PAGE_LIMIT, 1)

    assert fetch_all_pages(fetch) == rows
    assert len(calls) == 3


def test_the_limit_asked_for_is_never_left_to_the_client_default():
    """Passing no limit is the whole defect: the client fills in 25."""
    fetch, calls, _ = pages(PAGE_LIMIT, 1)

    fetch_all_pages(fetch)

    assert all(limit == PAGE_LIMIT for _, limit in calls)
    assert PAGE_LIMIT > 25


# --- responses that are not a listing


def test_a_response_without_data_is_handed_back():
    """Callers report the raw response, so it has to survive intact."""
    error = {'error': {'code': 404, 'message': 'Not found'}}

    assert fetch_all_pages(lambda offset, limit: error) is error


def test_something_that_is_not_a_dict_is_handed_back():
    assert fetch_all_pages(lambda offset, limit: None) is None


def test_an_error_on_a_later_page_is_handed_back_too():
    rows = [{'data': {'id': i}} for i in range(PAGE_LIMIT)]
    error = {'error': 'gone'}

    def fetch(offset, limit):
        return {'data': rows} if offset == 0 else error

    assert fetch_all_pages(fetch) is error


# --- the shape the callers rely on


def test_rows_keep_the_envelope_the_callers_index_into():
    """get_file_ID reads entry['data']['name'], so the wrapper stays on."""
    fetch, _, _ = pages(2)

    got = fetch_all_pages(fetch)

    assert got[0]['data']['name'] == 'file0.po'


@pytest.mark.parametrize('count', [26, 80])
def test_a_project_bigger_than_the_old_cap_comes_back_whole(count):
    """Satisfactory has 59 files and Fellowship 80. Both used to come back
    as 25."""
    fetch, _, rows = pages(count)

    got = fetch_all_pages(fetch)

    assert len(got) == count
    assert got[-1] == rows[-1]
