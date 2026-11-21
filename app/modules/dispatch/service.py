from app.modules.replay.service import replay
from .compare import compare
from .constraints import validate_plan


def evaluate(shift, events, capacity, base, draft):
    legs = validate_plan(shift, draft)
    result = replay(shift, events, capacity, legs)
    return result, {'legs': legs, 'comparison': compare(shift, base, result),
                    'movements': [row for row in result['timeline'] if row['kind'] in {'load', 'unload'}]}
