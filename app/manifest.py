import hashlib
import json
from datetime import datetime, timezone

from .clock import stamp
from .config import RULE_VERSION, ZONE


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def manifest(sources, legs, elapsed_ms):
    inputs = {name: {'sha256': digest(raw), 'bytes': len(raw)} for name, raw in sources.items()}
    identity = {'inputs': inputs, 'rule_version': RULE_VERSION, 'plan': legs}
    return dict(identity, id=digest(canonical(identity).encode()), zone=ZONE,
                generated_at=stamp(datetime.now(timezone.utc)), elapsed_ms=elapsed_ms)
