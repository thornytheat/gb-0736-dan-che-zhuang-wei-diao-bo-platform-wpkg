from flask import current_app, jsonify, request

from .errors import DomainError


def store():
    return current_app.extensions['shift_store']


def selected():
    return store().load(request.args.get('run'))


def stage(name):
    snapshot = selected()
    return jsonify(id=snapshot['manifest']['id'], data=snapshot[name])


def body(*required):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != set(required):
        raise DomainError('BAD_REQUEST', fields=list(required))
    for field in ('expected', 'target', 'run'):
        if field in data and (not isinstance(data[field], str) or not data[field]):
            raise DomainError('BAD_REQUEST', field=field)
    if 'legs' in data and not isinstance(data['legs'], list):
        raise DomainError('BAD_PLAN')
    return data
