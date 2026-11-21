from app.manifest import canonical, digest
from app.reasons import REASONS


def evidence(snapshot):
    payload = dict(snapshot, reason_labels=REASONS)
    return {'evidence_sha256': digest(canonical(payload).encode()), 'evidence': payload}
