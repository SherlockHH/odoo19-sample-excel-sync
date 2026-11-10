from .constants import EDITABLE, READONLY


def _canonical(value):
    if value is None or value is False:
        return ''
    return value.replace('\r\n', '\n').replace('\r', '\n') if isinstance(value, str) else value


def _index(rows):
    indexed = {}
    for row in rows:
        key = row.get('key')
        if not isinstance(key, str) or not key or key in indexed:
            raise ValueError('Missing or duplicate sample row identifier.')
        indexed[key] = row
    return indexed


def compare_rows(baselines, current_rows, submitted_rows):
    """Field-level three-way comparison; omitted rows never mean deletion."""
    bases, current, incoming = map(_index, (baselines, current_rows, submitted_rows))
    changes = []
    for key, row in incoming.items():
        if key not in bases or key not in current:
            raise ValueError('Unknown or no longer accessible sample row. Export again.')
        base, now = bases[key], current[key]
        for field in READONLY:
            if _canonical(row.get(field)) != _canonical(base.get(field)):
                raise ValueError('An identification/reference column was changed. Export again.')
        for field in EDITABLE:
            old, live, new = (_canonical(r.get(field)) for r in (base, now, row))
            if new == old or new == live:
                continue
            if now.get('cancelled') or now.get('state') == 'Cancelled':
                raise ValueError('Cancelled sample lines cannot be updated.')
            kind = 'conflict' if live != old else 'clear' if not new else 'update'
            changes.append(dict(id=f'{key}:{field}', key=key, field=field,
                                before=old, current=live, incoming=new, kind=kind))
    return changes


def resolve_changes(changes, decisions):
    allowed = {change['id'] for change in changes}
    if set(decisions) - allowed:
        raise ValueError('Unknown preview decision.')
    updates = {}
    for change in changes:
        if change['field'] not in EDITABLE:
            raise ValueError('Unexpected update field.')
        decision = decisions.get(change['id'])
        if decision not in (None, 'apply', 'keep'):
            raise ValueError('Invalid preview choice.')
        if change['kind'] == 'conflict' and not decision:
            raise ValueError('Choose Excel or Odoo for every conflict.')
        if decision == 'keep' or (decision is None and change['kind'] == 'clear'):
            continue
        updates.setdefault(change['key'], {})[change['field']] = change['incoming']
    return updates
