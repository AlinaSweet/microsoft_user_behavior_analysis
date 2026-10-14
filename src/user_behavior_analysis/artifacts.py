"""Small Git artifacts and content fingerprints for external large data."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

from .runtime import ROOT

SMALL_FILE_LIMIT = 10 * 1024 * 1024


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def register(path, name, kind, recipe, share_location=None, root=ROOT):
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', name):
        raise ValueError('Manifest name must use lowercase letters, numbers, underscores or hyphens')
    path = Path(path)
    if not path.is_absolute():
        path = root / path
    if not path.is_file():
        raise FileNotFoundError(path)
    logical = path.absolute()
    displayed = str(logical.relative_to(root)) if logical.is_relative_to(root) else path.name
    payload = {
        'name': name, 'kind': kind, 'project_path': displayed,
        'size_bytes': path.stat().st_size, 'sha256': sha256_file(path),
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'reproduction_or_origin': recipe,
        'share_location': share_location,
        'distribution_status': 'location_recorded' if share_location else 'local_only',
        'data_file_in_git': (subprocess.run(['git', 'ls-files', '--error-unmatch', str(logical)], cwd=root, capture_output=True).returncode == 0),
    }
    output = root / 'data/catalog' / f'{name}.json'
    write_json(output, payload)
    return output, payload


def check_git_files(root=ROOT):
    result = subprocess.run(['git', 'ls-files', '-z'], cwd=root, check=True, capture_output=True)
    names = [part.decode('utf-8') for part in result.stdout.split(b'\0') if part]
    issues = []
    for name in names:
        path = root / name
        if not path.exists():
            issues.append(f'Tracked file is missing: {name}')
            continue
        if path.is_symlink():
            issues.append(f'Local symbolic link must not be tracked: {name}')
        if path.stat().st_size > SMALL_FILE_LIMIT:
            issues.append(f'Tracked file exceeds 10 MiB: {name}')
        if any(name.startswith(prefix) for prefix in ('data/raw/', 'data/interim/', 'data/processed/')) and path.name != '.gitkeep':
            issues.append(f'Large data directory must not be tracked: {name}')
    return {'tracked_file_count': len(names), 'small_file_limit_bytes': SMALL_FILE_LIMIT, 'issues': issues}
