"""Read-only projection of operator-verified native host receipts."""
from pathlib import Path
import json
from datetime import datetime, timezone
from ..platform_lock import file_lock, atomic_replace_bytes


def _path(root):
    return Path(root) / 'host-integrations/native-receipts.json'


def _events_path(root):
    return Path(root) / 'host-integrations/native-receipt-events.jsonl'


def _latest_path(root):
    return Path(root) / 'host-integrations/native-receipts-latest.json'


def read_native_receipts(root):
    path = _path(root)
    if not path.exists():
        return []
    if path.is_symlink() or path.stat().st_size > 512 * 1024:
        raise ValueError('native_receipts_unreadable')
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema') != 'ep.host-native-receipts.v1' or not isinstance(data.get('receipts'), list):
        raise ValueError('native_receipts_unreadable')
    rows = []
    for row in data['receipts']:
        if not isinstance(row, dict) or row.get('evidence_kind') != 'native_host':
            continue
        if not row.get('host_id') or not row.get('observed_at') or not row.get('probe_id'):
            continue
        rows.append(dict(row))
    return rows


def append_native_receipt(root, row, *, keep_history=256):
    """Atomically append a verified native receipt and refresh the latest view.

    This is the write-side contract for host bridges.  It keeps an immutable
    JSONL event stream while maintaining the legacy ``native-receipts.json``
    compatibility file and a deduplicated latest projection keyed by
    ``host_id/capability_id/installation_id``.  It never upgrades evidence:
    callers must provide ``evidence_kind=native_host`` and an explicit state.
    """
    if not isinstance(row, dict) or row.get('evidence_kind') != 'native_host':
        raise ValueError('native_receipt_evidence_kind_required')
    required = ('host_id', 'capability_id', 'probe_id', 'observed_at', 'state')
    if any(not str(row.get(key) or '').strip() for key in required):
        raise ValueError('native_receipt_required_field_missing')
    value = dict(row)
    value.setdefault('written_at', datetime.now(timezone.utc).isoformat())
    root = Path(root)
    target = _path(root)
    lock = target.with_suffix('.transaction.lock')
    with file_lock(lock):
        root.joinpath('host-integrations').mkdir(parents=True, exist_ok=True)
        events = _events_path(root)
        previous_events = events.read_text(encoding='utf-8').splitlines() if events.exists() else []
        previous_events.append(json.dumps(value, ensure_ascii=False, sort_keys=True))
        atomic_replace_bytes(events, ('\n'.join(previous_events[-max(1, int(keep_history)):]) + '\n').encode(), check_revision=False)

        history = json.loads(target.read_text(encoding='utf-8')).get('receipts', []) if target.exists() else []
        history.append(value)
        history = history[-max(1, int(keep_history)):]
        atomic_replace_bytes(target, (json.dumps({'schema': 'ep.host-native-receipts.v1', 'receipts': history}, ensure_ascii=False, indent=2) + '\n').encode(), check_revision=False)

        latest = {}
        for item in history:
            key = '/'.join(str(item.get(field) or 'unknown') for field in ('host_id', 'capability_id', 'installation_id'))
            prior = latest.get(key)
            if prior is None or str(item.get('observed_at', '')) >= str(prior.get('observed_at', '')):
                latest[key] = item
        atomic_replace_bytes(_latest_path(root), (json.dumps({'schema': 'ep.host-native-receipts-latest.v1', 'receipts': list(latest.values())}, ensure_ascii=False, indent=2) + '\n').encode(), check_revision=False)
    return value


def read_latest_native_receipts(root):
    path = _latest_path(root)
    if not path.exists():
        history = read_native_receipts(root)
        latest = {}
        for item in history:
            key = '/'.join(str(item.get(field) or 'unknown') for field in ('host_id', 'capability_id', 'installation_id'))
            prior = latest.get(key)
            if prior is None or str(item.get('observed_at', '')) >= str(prior.get('observed_at', '')):
                latest[key] = item
        return list(latest.values())
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema') != 'ep.host-native-receipts-latest.v1' or not isinstance(data.get('receipts'), list):
        raise ValueError('native_receipts_latest_unreadable')
    return [dict(row) for row in data['receipts'] if isinstance(row, dict)]
