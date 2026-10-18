#!/usr/bin/env python3
"""Read-only, local evidence checks. Never authorizes or certifies task completion."""
import argparse
import datetime as dt
import hashlib
import json
from decimal import Decimal, DecimalException
import os
import re
import stat
import sys

LIMIT = 1024 * 1024
UTC = dt.timezone.utc


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('timestamp must be a string')
    value = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('timestamp must include a timezone')
    try:
        return value.astimezone(UTC)
    except OverflowError as error:
        raise ValueError('timestamp outside supported UTC range') from error


def safe_read(root, name):
    """Walk from a caller-selected root using directory descriptors, never symlinks."""
    if not isinstance(name, str) or not name or '\\' in name or '\x00' in name:
        raise ValueError('invalid artifact path')
    parts = name.split('/')
    if any(p in ('', '.', '..') or p.startswith('SENSITIVE_') or p == 'knowledge_base'
           or p.startswith('.') for p in parts):
        raise ValueError('unsafe or excluded artifact path')
    # POSIX O_NOFOLLOW/dir_fd are required: unsupported platforms fail closed.
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory)
        with os.fdopen(fd, 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError('artifact must be a regular file')
            data = stream.read(LIMIT + 1)
            if len(data) > LIMIT:
                raise ValueError('artifact exceeds 1 MiB limit')
            return data
    finally:
        os.close(directory)


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('non-finite JSON number')
    def exact_decimal(value):
        try:
            number = Decimal(value)
        except DecimalException as error:
            raise ValueError('decimal outside supported range') from error
        if not number.is_finite():
            raise ValueError('non-finite JSON number')
        return number
    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant,
                      parse_float=exact_decimal)


def validate(manifest):
    if not isinstance(manifest, dict) or set(manifest) != {
            'version', 'task', 'recorded_at', 'valid_until', 'criteria'}:
        raise ValueError('unexpected or missing manifest fields')
    if type(manifest['version']) is not int or manifest['version'] != 1:
        raise ValueError('unsupported version')
    if not isinstance(manifest['task'], str) or not manifest['task'].strip():
        raise ValueError('task must be nonempty')
    start, end = timestamp(manifest['recorded_at']), timestamp(manifest['valid_until'])
    if end <= start:
        raise ValueError('valid_until must follow recorded_at')
    criteria = manifest['criteria']
    if not isinstance(criteria, list) or not 1 <= len(criteria) <= 100:
        raise ValueError('require 1–100 criteria')
    ids = set()
    for item in criteria:
        if not isinstance(item, dict):
            raise ValueError('criterion must be an object')
        kind = item.get('kind')
        fields = {'id', 'claim', 'kind'}
        if kind == 'artifact_sha256':
            fields |= {'path', 'sha256'}
        elif kind == 'json_equals':
            fields |= {'path', 'sha256', 'pointer', 'expected'}
        elif kind != 'human_review':
            raise ValueError('unsupported check kind')
        if set(item) != fields:
            raise ValueError('unexpected or missing criterion fields')
        for key in ('id', 'claim'):
            if not isinstance(item[key], str) or not item[key].strip():
                raise ValueError('criterion id and claim must be nonempty')
        if item['id'] in ids:
            raise ValueError('duplicate criterion id')
        ids.add(item['id'])
        if kind != 'human_review':
            if not isinstance(item['path'], str):
                raise ValueError('path must be a string')
            if not isinstance(item['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', item['sha256']):
                raise ValueError('sha256 must be 64 lowercase hex characters')
        if kind == 'json_equals':
            pointer = item['pointer']
            if not isinstance(pointer, str) or (pointer and not pointer.startswith('/')) or re.search(r'~(?![01])', pointer):
                raise ValueError('invalid JSON pointer')
    return start, end


def pointer_value(value, pointer):
    for part in pointer.split('/')[1:] if pointer else []:
        part = part.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not re.fullmatch('0|[1-9][0-9]*', part):
                raise ValueError('invalid array index')
            value = value[int(part)]
        elif isinstance(value, dict):
            value = value[part]
        else:
            raise ValueError('pointer traverses scalar')
    return value


def equal_json(left, right):
    # JSON booleans are not numbers, unlike Python's True == 1.
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(equal_json(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(equal_json(a, b) for a, b in zip(left, right))
    return left == right


def check(manifest, root, now):
    start, end = validate(manifest)
    rows = []
    for item in manifest['criteria']:
        row = {'id': item['id'], 'claim': item['claim'], 'kind': item['kind']}
        if not start <= now < end:
            row.update(status='unknown', reason='outside declared evidence window')
        elif item['kind'] == 'human_review':
            row.update(status='human_review_required', reason='claim requires a separate reviewer')
        else:
            try:
                data = safe_read(root, item['path'])
                digest = hashlib.sha256(data).hexdigest()
                row.update(path=item['path'], observed_sha256=digest, bytes=len(data))
                if digest != item['sha256']:
                    row.update(status='mismatch', reason='artifact identity differs')
                elif item['kind'] == 'artifact_sha256':
                    row.update(status='artifact_identity_matched', reason='bytes match; claim not evaluated')
                else:
                    value = pointer_value(strict_json(data), item['pointer'])
                    if equal_json(value, item['expected']):
                        row.update(status='recorded_value_matched', reason='local record matches; underlying event not verified')
                    else:
                        row.update(status='mismatch', reason='recorded value differs')
            except (OSError, ValueError, KeyError, IndexError, UnicodeError, RecursionError):
                # Do not emit contents, OS paths outside root, or arbitrary error text.
                row.update(status='unknown', reason='artifact unavailable, unsafe, or malformed')
        rows.append(row)
    return {'version': 1, 'task': manifest['task'], 'checked_at': now.isoformat(),
            'scope': 'local artifact observations only', 'task_acceptance': 'not_assessed',
            'authorization': 'not_assessed', 'criteria': rows}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, help='reviewer-selected evidence directory')
    parser.add_argument('--manifest', required=True, help='relative JSON path within root')
    args = parser.parse_args(argv)
    try:
        data = safe_read(args.root, args.manifest)
        report = check(strict_json(data), args.root, dt.datetime.now(UTC))
        report['manifest_sha256'] = hashlib.sha256(data).hexdigest()
        print(json.dumps(report, indent=2, allow_nan=False))
        return 1 if any(r['status'] in ('unknown', 'mismatch') for r in report['criteria']) else 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        print(json.dumps({'error': 'invalid or unreadable manifest', 'task_acceptance': 'not_assessed', 'authorization': 'not_assessed'}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
