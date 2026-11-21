from flask import Blueprint, jsonify, request

from app.config import MAX_INPUT_BYTES
from app.errors import DomainError
from app.modules.archive.service import publish
from app.web import stage, store

bp = Blueprint('intake', __name__)


@bp.get('/api/intake')
def show():
    return stage('intake')


@bp.post('/api/intake')
def upload():
    file = request.files.get('events')
    if file is None:
        raise DomainError('UPLOAD_REQUIRED')
    expected = request.form.get('expected')
    if not expected:
        raise DomainError('BAD_REQUEST', field='expected')
    raw = file.stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise DomainError('BODY_TOO_LARGE', 413)
    return jsonify(publish(store(), expected, events=raw))
