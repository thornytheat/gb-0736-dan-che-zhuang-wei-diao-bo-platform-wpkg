from flask import Blueprint

from app.web import stage

bp = Blueprint('capacity', __name__)


@bp.get('/api/capacity')
def show():
    return stage('capacity')
