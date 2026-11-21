import io

import pytest

from app.errors import DomainError
from app.modules.intake.service import intake

HEADER = b'event_id,station,kind,occurred_at,received_at,note\n'


# TRAP-02
# TRAP-08
def test_bom_and_leading_zero(snapshot):
    result = snapshot['intake']
    assert result['encoding'] == 'UTF-8 BOM'
    assert (result['events'][0]['id'], result['events'][0]['station']) == ('0001', '001')


# TRAP-03
def test_quoted_multiline_keeps_physical_source_rows(snapshot):
    by_id = {row['id']: row for row in snapshot['intake']['events']}
    assert by_id['0007']['note'] == '值班复核\n补录备注'
    assert (by_id['0007']['line'], by_id['0008']['line']) == (8, 10)
    assert snapshot['intake']['input_rows'] == 61


# TRAP-04
# TRAP-05
def test_segment_header_and_extra_short_rows_are_isolated(snapshot):
    reason = snapshot['intake']['reasons']
    assert reason['REPEATED_HEADER'] == reason['COLUMN_COUNT'] == reason['BLANK_ROW'] == 1
    assert len(snapshot['intake']['events']) == 50


# TRAP-07
def test_sentinel_is_never_zero(snapshot):
    matches = [row['raw'] for row in snapshot['intake']['excluded'] if row['code'] == 'MISSING_FIELD']
    assert matches[0][0] == '0093' and matches[0][3] == '-'


# TRAP-11
def test_offset_duplicate_keeps_earliest_received(snapshot):
    result = snapshot['intake']
    kept, = [row for row in result['events'] if row['id'] == '0002']
    replayed, = [row for row in result['excluded'] if row['code'] == 'DUPLICATE_EVENT']
    assert kept['at'] == '2026-11-20T00:01:00Z'
    assert kept['received_at'] == '2026-11-20T00:01:14Z' and replayed['raw'][0] == '0002'


# TRAP-14
def test_contradictory_duplicates_are_never_counted(snapshot):
    result = snapshot['intake']
    rows = [row for row in result['excluded'] if row['code'] == 'EVENT_CONFLICT']
    assert [(row['raw'][0], row['raw'][1]) for row in rows] == [('0088', '003'), ('0088', '004')]
    assert '0088' not in {row['id'] for row in result['events']}


def test_receipt_delay_does_not_change_event_order(snapshot):
    events = snapshot['intake']['events']
    late, = [row for row in events if row['late']]
    next_event = events[events.index(late) + 1]
    assert (late['id'], late['at'], late['received_at']) == ('0011', '2026-11-20T00:18:00Z', '2026-11-20T00:31:15Z')
    assert next_event['id'] == '0015'


# TRAP-18
def test_three_empty_inputs_have_distinct_errors(shift):
    for raw, code in [(b'', 'EMPTY_FILE'), (b'\r\n \n', 'BLANK_FILE'), (HEADER, 'HEADER_ONLY')]:
        with pytest.raises(DomainError, match=code):
            intake(raw, shift)


# TRAP-01
def test_gb18030_reordered_columns_and_mixed_line_endings(shift):
    raw = ('station,event_id,occurred_at,kind,received_at,note\r\n'
           '001,0001,2026-11-20T00:02:00Z,rent,2026-11-20T00:03:00Z,临时入账\n').encode('gb18030')
    out = intake(raw, shift)
    assert out['encoding'] == 'GB18030' and out['events'][0]['note'] == '临时入账'


def test_bad_upload_reports_source_line_without_publication(client, run_id):
    file = io.BytesIO(HEADER + b'0001,001,return,2026-11-20T00:05:00Z,2026-11-20T00:06:00Z,"unterminated')
    response = client.post('/api/intake', data={'expected': run_id, 'events': (file, 'events.csv')})
    assert (response.status_code, response.json['code'], response.json['details']['line']) == (422, 'BAD_CSV', 2)
    assert client.get('/api/runs').json['manifest']['id'] == run_id
