from flask import Blueprint, Response, jsonify, request

from app.config import MAX_INPUT_BYTES
from app.errors import DomainError
from app.manifest import canonical
from app.modules.archive.evidence import evidence
from app.web import store
from . import sample, service

bp = Blueprint('bulletin', __name__)


@bp.get('/api/bulletin')
def show():
    data = service.status(store(), request.args.get('as_of'))
    data['sample_remaining'] = len(sample.remaining(store()))
    return jsonify(data)


@bp.post('/api/bulletin/backfill')
def upload():
    file = request.files.get('events')
    if file is None:
        raise DomainError('UPLOAD_REQUIRED')
    raw = file.stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise DomainError('BODY_TOO_LARGE', 413)
    form = request.form
    return jsonify(service.ingest(store(), form.get('batch_id'), form.get('station'),
                                  form.get('covered_until'), raw))


@bp.post('/api/bulletin/backfill/sample')
def load_sample():
    return jsonify(sample.ingest_next_sample(store()))


@bp.post('/api/bulletin/publish')
def accept():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {'expected', 'as_of', 'mode'}:
        raise DomainError('BAD_REQUEST', fields=['expected', 'as_of', 'mode'])
    if data['expected'] is not None and (not isinstance(data['expected'], str) or not data['expected']):
        raise DomainError('BAD_REQUEST', field='expected')
    if data['mode'] not in ('partial', 'all'):
        raise DomainError('BAD_REQUEST', field='mode')
    if not isinstance(data['as_of'], str) or not data['as_of']:
        raise DomainError('BAD_REQUEST', field='as_of')
    return jsonify(service.publish(store(), data['expected'], data['as_of'], data['mode']))


@bp.post('/api/bulletin/verify')
def recheck():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {'id'} or not isinstance(data['id'], str) or not data['id']:
        raise DomainError('BAD_REQUEST', fields=['id'])
    return jsonify(service.verify(store(), data['id']))


@bp.get('/api/bulletin/<bulletin_id>/evidence.json')
def export(bulletin_id):
    payload = store().load_bulletin(bulletin_id)
    return Response(canonical(evidence(payload)) + '\n', mimetype='application/json',
                    headers={'Content-Disposition':
                             f'attachment; filename="cycle-bulletin-{bulletin_id[:12]}.json"'})
