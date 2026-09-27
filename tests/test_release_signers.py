"""Exercise real signed tags without using release-owner credentials."""
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd, env=None):
    environment = dict(os.environ if env is None else env)
    environment.pop("SSH_AUTH_SOCK", None)
    return subprocess.run(args, cwd=cwd, env=environment, check=True, capture_output=True, text=True, timeout=30).stdout.strip()


@pytest.fixture
def signed_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run("git", "init", "-q", cwd=repo)
    run("git", "config", "user.name", "Release test", cwd=repo)
    run("git", "config", "user.email", "test@example.invalid", cwd=repo)
    run("git", "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-qm", "fixture", cwd=repo)
    key = tmp_path / "signer"
    run("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key), cwd=repo)
    fingerprint = run("ssh-keygen", "-lf", str(key)+".pub", "-E", "sha256", cwd=repo).split()[1]
    run("git", "-c", "gpg.format=ssh", "-c", f"user.signingkey={key}", "tag", "-s", "v1.0.0", "-m", "fixture", cwd=repo)
    return repo, key, fingerprint


def check(repo, key, fingerprint, tag="v1.0.0"):
    return subprocess.run(["python3", str(ROOT / "scripts/release/verify_tag_signer.py"), "--tag", tag, "--fingerprint", fingerprint, "--public-key", str(key)+".pub"], cwd=repo, capture_output=True, text=True)


def test_ssh_signed_tag_accepts_exact_approved_key(signed_repo):
    repo, key, fingerprint = signed_repo
    assert check(repo, key, fingerprint).returncode == 0


def test_ssh_signed_tag_rejects_wrong_fingerprint(signed_repo):
    repo, key, fingerprint = signed_repo
    assert check(repo, key, "SHA256:unapproved").returncode != 0


def test_ssh_signed_tag_rejects_different_trusted_key(signed_repo, tmp_path):
    repo, key, fingerprint = signed_repo
    other = tmp_path / "other"
    run("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(other), cwd=repo)
    other_fp = run("ssh-keygen", "-lf", str(other)+".pub", "-E", "sha256", cwd=repo).split()[1]
    assert check(repo, other, other_fp).returncode != 0


def test_unsigned_or_lightweight_tags_rejected(signed_repo):
    repo, key, fingerprint = signed_repo
    run("git", "-c", "tag.gpgsign=false", "tag", "-a", "unsigned", "-m", "fixture", cwd=repo)
    run("git", "-c", "tag.gpgsign=false", "tag", "lightweight", cwd=repo)
    assert check(repo, key, fingerprint, "unsigned").returncode != 0
    assert check(repo, key, fingerprint, "lightweight").returncode != 0


def test_openpgp_signed_tag_accepts_exact_approved_key(tmp_path):
    repo = tmp_path / 'pgp-repo'
    repo.mkdir()
    home = tmp_path / 'gnupg'
    home.mkdir(mode=0o700)
    env = {**os.environ, 'GNUPGHOME': str(home)}
    run('gpg', '--batch', '--pinentry-mode', 'loopback', '--passphrase', '', '--quick-generate-key', 'Leafer test <test@example.invalid>', 'ed25519', 'sign', '1d', cwd=repo, env=env)
    keys = run('gpg', '--batch', '--with-colons', '--list-secret-keys', cwd=repo, env=env)
    fingerprint = next(line.split(':')[9] for line in keys.splitlines() if line.startswith('fpr:'))
    public = tmp_path / 'pgp.pub'
    public.write_text(run('gpg', '--armor', '--export', fingerprint, cwd=repo, env=env))
    run('git', 'init', '-q', cwd=repo)
    run('git', 'config', 'user.name', 'Release test', cwd=repo)
    run('git', 'config', 'user.email', 'test@example.invalid', cwd=repo)
    run('git', '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-qm', 'fixture', cwd=repo)
    run('git', '-c', 'gpg.format=openpgp', '-c', f'user.signingkey={fingerprint}', 'tag', '-s', 'v1.0.0', '-m', 'fixture', cwd=repo, env=env)
    result = subprocess.run(['python3', str(ROOT/'scripts/release/verify_tag_signer.py'), '--tag', 'v1.0.0', '--fingerprint', fingerprint, '--public-key', str(public)], cwd=repo, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
