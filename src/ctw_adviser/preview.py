"""Identify an unmerged PR #23 inspection deployment at runtime."""
import html
import os
import re

PREVIEW_BRANCH = 'issue-19/character-access'
PREVIEW_LABEL = 'PR #23 preview — unmerged'
SHA = re.compile(r'[0-9a-fA-F]{40}\Z')


def preview_revision(environ=None):
    values = os.environ if environ is None else environ
    branch = values.get('RAILWAY_GIT_BRANCH', '').removeprefix('refs/heads/')
    requested = values.get('CTW_PREVIEW_PR') == '23'
    if not requested and branch != PREVIEW_BRANCH:
        return None
    if branch and branch != PREVIEW_BRANCH:
        raise ValueError('PR #23 preview cannot use another Git branch')
    railway_sha = values.get('RAILWAY_GIT_COMMIT_SHA', '')
    explicit_sha = values.get('CTW_ADVISER_COMMIT', '')
    if railway_sha and explicit_sha and railway_sha.lower() != explicit_sha.lower():
        raise ValueError('preview adviser commit does not match Railway Git commit')
    sha = railway_sha or explicit_sha
    if not SHA.fullmatch(sha):
        raise ValueError('PR #23 preview requires an exact adviser commit SHA')
    return {'label': PREVIEW_LABEL, 'adviser_commit': sha.lower()}


def preview_banner(environ=None):
    revision = preview_revision(environ)
    if revision is None:
        return ''
    sha = revision['adviser_commit']
    return ('<aside class="release-preview" role="status"><strong>' +
            html.escape(revision['label']) + '</strong><br>Adviser commit ' +
            '<a href="https://github.com/OwenTanzer/CTW-adviser/commit/' + sha +
            '"><code>' + sha + '</code></a></aside>')
