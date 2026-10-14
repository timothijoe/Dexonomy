"""Verify a pinned selected download against immutable official Hub identities."""
from pathlib import Path
import hashlib
import json

from .common import sha256


def verify_resources(manifest, asset_root, demo_root):
    data = json.loads(Path(manifest).read_text())
    if data.get('schema_version') != 1:
        raise ValueError('Unsupported resource manifest schema')
    roots = {'assets': Path(asset_root), 'demos': Path(demo_root)}
    rows = []
    for group, receipt in data['resources'].items():
        for file in receipt['files']:
            rel = Path(file['path'])
            if rel.is_absolute() or '..' in rel.parts:
                raise ValueError('Resource receipt contains an unsafe relative path')
            path = roots[group] / rel
            row = {'group': group, 'path': str(rel), 'status': 'missing'}
            if path.is_file():
                if file['hash_type'] == 'sha256':
                    digest = sha256(path)
                elif file['hash_type'] == 'git_blob_sha1':
                    h = hashlib.sha1()
                    h.update(f'blob {path.stat().st_size}\0'.encode())
                    with path.open('rb') as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                            h.update(chunk)
                    digest = h.hexdigest()
                else:
                    raise ValueError('Unknown resource hash type')
                row.update(status='verified' if digest == file['hash'] else 'hash_mismatch', actual_hash=digest)
            rows.append(row)
    return {'schema_version': 1, 'verified': all(r['status'] == 'verified' for r in rows), 'files': rows,
            'sources': {key: {'repo_id': item['repo_id'], 'revision': item['revision']} for key, item in data['resources'].items()},
            'note': 'Official source identity verified independently of simulator acceptance'}
