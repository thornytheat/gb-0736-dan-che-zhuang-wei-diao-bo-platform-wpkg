from flask import Blueprint

from app.web import stage

bp = Blueprint('demand', __name__)


@bp.get('/api/demand')
def show():
    return stage('demand')
