"""Durable, hash-chained action journal (append-only file, unique record ids).

Unlike the in-memory deque, records survive restarts and edits/deletions/reordering
are detectable with verify(). It detects tampering; keep the folder outside the
writable authority of any governed coding agent when deploying.
"""
import hashlib, json, os, threading, time, uuid
from pathlib import Path

GENESIS = '0' * 64
_lock = threading.Lock()


class AuditError(Exception):
    pass


def _digest(entry):
    return hashlib.sha256(json.dumps(entry, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _path(root):
    return Path(root) / 'audit' / 'actions.jsonl'


def record(root, event, **fields):
    path = _path(root)
    with _lock:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            prev = GENESIS
            if path.exists():
                lines = [l for l in path.read_text(encoding='utf-8').splitlines() if l.strip()]
                if lines: prev = json.loads(lines[-1])['hash']
            entry = {'id': uuid.uuid4().hex, 'at_unix': time.time(), 'event': str(event)[:40], 'prev': prev}
            entry.update({k: (v if isinstance(v, (int, float, bool)) or v is None else str(v)[:200]) for k, v in fields.items()})
            entry['hash'] = _digest(entry)
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.write(fd, (json.dumps(entry, sort_keys=True) + '\n').encode()); os.fsync(fd)
            finally:
                os.close(fd)
            return entry['id']
        except (OSError, ValueError, KeyError) as exc:
            raise AuditError('audit_unavailable') from exc


def verify(root):
    path = _path(root)
    if not path.exists(): return True, 'empty'
    prev = GENESIS
    try:
        for n, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if not line.strip(): continue
            entry = json.loads(line); claimed = entry.pop('hash', None)
            if entry.get('prev') != prev or claimed != _digest(entry): return False, f'broken at record {n}'
            prev = claimed
    except (OSError, ValueError, AttributeError):
        return False, 'unreadable'
    return True, 'intact'
