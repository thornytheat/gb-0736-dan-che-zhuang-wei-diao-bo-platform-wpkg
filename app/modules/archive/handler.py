from flask import Blueprint, Response, jsonify

from app.manifest import canonical
from app.modules.archive.evidence import evidence
from app.modules.archive.service import rerun, restore, sample_plan
from app.web import body, selected, store

bp = Blueprint('archive', __name__)


@bp.get('/api/runs')
def show():
    snapshot = selected()
    return jsonify(manifest=snapshot['manifest'], history=store().history(), shift=snapshot['shift'],
                   sample_plan=sample_plan())


@bp.post('/api/runs/rerun')
def restart():
    data = body('expected')
    return jsonify(rerun(store(), data['expected']))


@bp.post('/api/runs/restore')
def rollback():
    data = body('target', 'expected')
    return jsonify(restore(store(), data['target'], data['expected']))


@bp.get('/api/runs/<run_id>/evidence.json')
def export(run_id):
    snapshot = store().load(run_id)
    return Response(canonical(evidence(snapshot)) + '\n', mimetype='application/json',
                    headers={'Content-Disposition': f'attachment; filename="cycle-docks-{run_id[:12]}.json"'})
