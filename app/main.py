import os
import sqlite3

from flask import Flask, jsonify, render_template
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from .config import MAX_INPUT_BYTES
from .errors import DomainError
from .modules.archive.handler import bp as archive
from .modules.archive.service import seed
from .modules.capacity.handler import bp as capacity
from .modules.demand.handler import bp as demand
from .modules.dispatch.handler import bp as dispatch
from .modules.intake.handler import bp as intake
from .modules.inventory.handler import bp as inventory
from .modules.replay.handler import bp as replay
from .reasons import REASONS
from .store import Store


def create_app(path=None):
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=MAX_INPUT_BYTES + 32 * 1024)
    db = Store(path or os.getenv('CYCLE_DB', 'var/shift.sqlite3'))
    app.extensions['shift_store'] = db
    seed(db)
    for blueprint in (intake, capacity, replay, demand, dispatch, inventory, archive):
        app.register_blueprint(blueprint)

    @app.errorhandler(DomainError)
    def domain_error(error):
        return jsonify(code=error.code, message=REASONS[error.code], details=error.details), error.status

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_):
        return domain_error(DomainError('BODY_TOO_LARGE', 413))

    @app.errorhandler(BadRequest)
    def bad_request(_):
        return domain_error(DomainError('BAD_REQUEST', 400))

    @app.errorhandler(sqlite3.Error)
    def storage_error(error):
        app.logger.error('班次存储失败', exc_info=error)
        return domain_error(DomainError('STORE_UNAVAILABLE', 503))

    @app.get('/')
    def home():
        return render_template('workbench.html', reasons=REASONS)

    @app.get('/health')
    def health():
        return jsonify(status='ok', run=db.active())

    return app
