"""Configuration, provenance and atomic report helpers."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

import yaml


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_config(path: str | Path, **overrides) -> dict:
    path = Path(path).resolve()
    cfg = yaml.safe_load(path.read_text())
    if cfg.get('schema_version') != 1:
        raise ValueError('Unsupported integration configuration schema_version')
    for key in ('bench2dex_root', 'asset_root', 'demo_root', 'semantics'):
        value = overrides.get(key)
        cfg[key] = Path(value).expanduser().resolve() if value else (path.parent / cfg[key]).resolve()
    cfg['config_path'] = path
    cfg['config_sha256'] = sha256(path)
    return cfg


def git_identity(root: Path) -> dict:
    def run(*args):
        p = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, timeout=10)
        return p.stdout.strip() if p.returncode == 0 else None
    return {'commit': run('rev-parse', 'HEAD'), 'status': run('status', '--porcelain')}


def atomic_json(path: str | Path, payload: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # No NaN or Infinity in manifests. Replace only after the complete write.
    body = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False, encoding='utf-8') as stream:
        tmp = Path(stream.name)
        stream.write(body)
    os.replace(tmp, path)


def file_receipt(path: Path) -> dict:
    return {'path': str(path), 'status': 'present' if path.is_file() else 'missing',
            'sha256': sha256(path) if path.is_file() else None}
