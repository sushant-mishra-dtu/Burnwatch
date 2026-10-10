"""Small shared helpers for Windows-safe BurnWatch provisioning scripts."""
import argparse
import os
from pathlib import Path
import re
import sys
import tempfile

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from tools import contracts

REGION = "ap-south-1"
DEFAULT_ENV = REPO_ROOT / "device" / ".env"


def read_env(path):
    values = {}
    if Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                key, sep, value = line.partition("=")
                if not sep or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key.strip()):
                    raise ValueError(f"Invalid environment entry in {path}")
                values[key.strip()] = value.strip().strip("\"'")
    return values


def atomic_write(path, content):
    """Create the temp file privately before writing, then atomically replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            os.chmod(temporary, 0o600)
            stream.write(content.encode("utf-8"))
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def update_env(path, changes):
    """Keep unrelated keys/comments and never print credential values."""
    read_env(path)  # Refuse malformed input instead of overwriting it.
    for key, value in changes.items():
        if any(character in str(value) for character in "\r\n"):
            raise ValueError(f"Newline in {key}")
    old_lines = Path(path).read_text(encoding="utf-8-sig").splitlines() if Path(path).exists() else []
    lines, written = [], set()
    for line in old_lines:
        key = line.partition("=")[0].strip()
        if key in changes:
            if key not in written:
                lines.append(f"{key}={changes[key]}")
                written.add(key)
        else:
            lines.append(line)
    lines.extend(f"{key}={value}" for key, value in changes.items() if key not in written)
    atomic_write(path, "\n".join(lines) + "\n")


def check_bucket(bucket):
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket):
        raise ValueError("Pass a valid S3 bucket name from the SAM BucketName output")
    return bucket


def session(profile=None):
    import boto3
    return boto3.Session(profile_name=profile, region_name=REGION)


def common_arguments(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--profile", help="AWS setup/admin profile, never the device S3 key")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    return parser
