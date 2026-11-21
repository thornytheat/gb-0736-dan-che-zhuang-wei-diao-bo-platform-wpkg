from datetime import datetime, timezone

from .errors import DomainError


def instant(value):
    if not isinstance(value, str) or 'T' not in value:
        raise DomainError('BAD_TIME')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.utcoffset() is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise DomainError('BAD_TIME') from None


def stamp(value):
    return value.isoformat().replace('+00:00', 'Z')
