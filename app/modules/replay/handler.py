from flask import Blueprint

from app.web import stage

bp = Blueprint('replay', __name__)


@bp.get('/api/replay')
def show():
    return stage('replay')
