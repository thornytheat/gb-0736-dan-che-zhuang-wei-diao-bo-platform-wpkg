from flask import Blueprint

from app.web import stage

bp = Blueprint('inventory', __name__)


@bp.get('/api/inventory')
def show():
    return stage('inventory')
