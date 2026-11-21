from flask import Blueprint, jsonify

from app.modules.archive.service import preview, publish
from app.web import body, stage, store

bp = Blueprint('dispatch', __name__)


@bp.get('/api/dispatch')
def show():
    return stage('dispatch')


@bp.post('/api/dispatch/preview')
def trial():
    data = body('run', 'legs')
    snapshot = preview(store(), data['run'], data['legs'])
    return jsonify(dispatch=snapshot['dispatch'], inventory=snapshot['inventory']['plan'],
                   slots=snapshot['demand']['plan']['slots'])


@bp.post('/api/dispatch/publish')
def accept():
    data = body('expected', 'legs')
    return jsonify(publish(store(), data['expected'], draft=data['legs']))
