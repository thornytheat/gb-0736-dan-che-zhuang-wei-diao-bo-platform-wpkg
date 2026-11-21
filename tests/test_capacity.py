import pytest

from app.errors import DomainError
from app.modules.capacity.service import capacity


def test_higher_revision_shadows_day_version(snapshot):
    park = [row for row in snapshot['capacity']['segments'] if row['station'] == '003']
    assert [(row['revision'], row['slots']) for row in park] == [(1, 8), (2, 0), (2, 3), (1, 8)]


def test_adjacent_same_revision_is_half_open(snapshot):
    closed, reduced = [row for row in snapshot['capacity']['segments'] if row['station'] == '003' and row['revision'] == 2]
    assert closed['end'] == reduced['start'] == '2026-11-20T00:45:00Z'
    assert closed['line'] != reduced['line']


# TRAP-25
def test_conflicting_revisions_are_quarantined_together(snapshot):
    cap = snapshot['capacity']
    assert [(row['line'], row['code']) for row in cap['excluded']] == [
        (9, 'CAPACITY_CONFLICT'), (10, 'CAPACITY_CONFLICT'), (11, 'BAD_CAPACITY')]
    [metro] = [row for row in cap['segments'] if row['station'] == '002']
    assert (metro['slots'], metro['revision']) == (7, 1)


def test_gap_stops_replay_with_station_and_boundary(sources, shift):
    lines = sources['capacity'].splitlines(keepends=True)
    with pytest.raises(DomainError, match='CAPACITY_GAP') as caught:
        capacity(b''.join(lines[:3] + lines[4:]), shift)
    assert caught.value.details == {'station': '003', 'at': '2026-11-20T00:00:00Z'}


def test_one_dock_version_does_not_split_other_station(snapshot):
    cap = snapshot['capacity']
    [square] = [row for row in cap['segments'] if row['station'] == '001']
    assert (square['start'], square['end'], square['slots']) == ('2026-11-20T00:00:00Z', '2026-11-20T02:00:00Z', 10)


def test_clips_versions_outside_shift(sources, shift):
    raw = sources['capacity'].replace(b'001,1,2026-11-20T08:00:00+08:00', b'001,1,2026-11-20T07:00:00+08:00', 1)
    result = capacity(raw, shift)
    square = result['segments'][0]
    assert square['start'] == '2026-11-20T00:00:00Z' and square['line'] == 2
