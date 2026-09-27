"""Publication requires live, independently authored, exact-identity evidence."""
import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('leafer_dependency_lock_tests', ROOT/'scripts/ci/verify_dasops_release_lock.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_pending_publication_is_rejected():
    lock = module.load_lock(ROOT/'release/DEPENDENCY_LOCK.json')
    lock['publication'] = {'status': 'blocked', 'reason': 'isolated negative test'}
    with pytest.raises(ValueError, match='not publication-eligible'):
        module.require_publication_eligible(lock)


def test_eligible_string_does_not_replace_bound_evidence():
    lock = module.load_lock(ROOT/'release/DEPENDENCY_LOCK.json')
    lock['publication'] = {'status': 'eligible', 'reason': 'isolated evidence-free test'}
    with pytest.raises(ValueError, match='exact DASOps release identity'):
        module.require_publication_eligible(lock)


APPROVAL_ISSUE = 'https://github.com/security-review/release-policy/issues/7'
APPROVAL_API = 'https://api.github.com/repos/security-review/release-policy/issues/comments/'


def _fixture():
    lock = module.load_lock(ROOT/'release/DEPENDENCY_LOCK.json')
    identity = copy.deepcopy(lock['identity'])
    lock['publication']['status'] = 'eligible'
    lock['publication']['evidence'] = {
        'releaseIdentity': identity,
        'githubRelease': 'https://github.com/AzzCraft/dasops/releases/tag/v1.0.0',
        'validationRun': 'https://github.com/AzzCraft/dasops/actions/runs/123',
        'approval': APPROVAL_ISSUE + '#issuecomment-456',
        'signature': {'status': 'historical-unsigned-exception', 'exceptionId': 'DASOPS-100-EXC',
                      'approval': APPROVAL_ISSUE + '#issuecomment-456'},
    }
    statement = {'schemaVersion': 'das-leafer.dasops-exception.v1', 'component': 'dasops',
                 'version': '1.0.0', 'tag': identity['tag'], 'tagObject': identity['tagObject'],
                 'targetCommit': identity['targetCommit'], 'exceptionId': 'DASOPS-100-EXC',
                 'scope': 'historical-unsigned-tag-only', 'approver': 'independent-reviewer',
                 'approvalIssue': APPROVAL_ISSUE}
    import json
    responses = {
        APPROVAL_API + '456': {'html_url': APPROVAL_ISSUE + '#issuecomment-456',
            'issue_url': 'https://api.github.com/repos/security-review/release-policy/issues/7',
            'user': {'login': 'independent-reviewer'}, 'author_association': 'MEMBER',
            'created_at': '2026-09-27T00:00:00Z', 'updated_at': '2026-09-27T00:00:00Z',
            'body': json.dumps(statement)},
        module.DASOPS_API + 'releases/tags/v1.0.0': {'html_url': lock['publication']['evidence']['githubRelease'],
            'tag_name': 'v1.0.0', 'draft': False, 'published_at': '2026-09-27T01:00:00Z'},
        module.DASOPS_API + 'actions/runs/123': {'html_url': lock['publication']['evidence']['validationRun'],
            'repository': {'full_name': 'AzzCraft/dasops'}, 'head_sha': identity['targetCommit'],
            'workflow_id': 789, 'status': 'completed', 'conclusion': 'success'},
    }
    kwargs = {'fetch': responses.__getitem__, 'resolve_tag': lambda _identity: (identity['tagObject'], identity['targetCommit']),
              'approved_approvers': {'independent-reviewer'}, 'validation_workflow_id': 789, 'approval_issue_url': APPROVAL_ISSUE}
    return lock, responses, kwargs


def test_independently_authenticated_exact_exception_shape_is_accepted():
    lock, _, kwargs = _fixture()
    module.require_publication_eligible(lock, **kwargs)


@pytest.mark.parametrize('mutate', [
    lambda lock, records, kwargs: lock['publication']['evidence'].update(releaseIdentity={**lock['identity'], 'targetCommit': 'f'*40}),
    lambda lock, records, kwargs: lock['publication']['evidence']['signature'].update(status='verified', fingerprint='not-real'),
    lambda lock, records, kwargs: lock['publication']['evidence'].update(approval='https://github.com/example/not-approved/issues/7'),
    lambda lock, records, kwargs: records[APPROVAL_API + '456']['user'].update(login='publisher'),
    lambda lock, records, kwargs: records[APPROVAL_API + '456'].update(updated_at='2026-09-28T00:00:00Z'),
    lambda lock, records, kwargs: records[module.DASOPS_API + 'releases/tags/v1.0.0'].update(draft=True),
    lambda lock, records, kwargs: records[module.DASOPS_API + 'actions/runs/123'].update(conclusion='failure'),
    lambda lock, records, kwargs: records[module.DASOPS_API + 'actions/runs/123'].update(head_sha='f'*40),
    lambda lock, records, kwargs: kwargs.update(resolve_tag=lambda _identity: ('f'*40, 'f'*40)),
])
def test_fabricated_or_unrelated_evidence_is_rejected(mutate):
    lock, records, kwargs = _fixture()
    mutate(lock, records, kwargs)
    with pytest.raises(ValueError):
        module.require_publication_eligible(lock, **kwargs)


def test_missing_protected_independent_approver_fails_closed():
    lock, _, kwargs = _fixture()
    kwargs['approved_approvers'] = set()
    with pytest.raises(ValueError, match='protected independent approver'):
        module.require_publication_eligible(lock, **kwargs)


def test_private_issue_without_read_token_fails_before_network(monkeypatch):
    lock, _, kwargs = _fixture()
    kwargs.pop('fetch')
    monkeypatch.delenv('DASOPS_APPROVAL_TOKEN', raising=False)
    with pytest.raises(ValueError, match='DASOPS_APPROVAL_TOKEN'):
        module.require_publication_eligible(lock, **kwargs)


def test_publication_suite_accepts_an_eligible_repository_lock(tmp_path):
    """The real release approval transition must not invalidate unit tests."""
    import json
    import os
    import shutil
    import subprocess
    import sys

    for relative in ("tests/test_dependency_publication.py", "scripts/ci/verify_dasops_release_lock.py"):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    raw = json.loads((ROOT / "release/DEPENDENCY_LOCK.json").read_text())
    raw["publication"] = _fixture()[0]["publication"]
    destination = tmp_path / "release/DEPENDENCY_LOCK.json"
    destination.parent.mkdir()
    destination.write_text(json.dumps(raw))
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    for key in ("DASOPS_APPROVAL_TOKEN", "DASOPS_APPROVED_APPROVERS", "DASOPS_VALIDATION_WORKFLOW_ID", "DASOPS_APPROVAL_ISSUE_URL"):
        environment.pop(key, None)
    result = subprocess.run([sys.executable, "-m", "pytest", "tests/test_dependency_publication.py", "-q", "-p", "no:cacheprovider", "-k", "not test_publication_suite_accepts_an_eligible_repository_lock"], cwd=tmp_path, env=environment, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
