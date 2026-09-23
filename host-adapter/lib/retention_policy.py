"""One explicit-origin policy shared by capture and every batch submitter.

No content keywords, topic guesses, or directory-name heuristics establish origin.
Excluded data remain in local transcripts/queue for audit, never auto-deleted here.
"""
import os


def _path(value):
    return os.path.normpath(os.path.expanduser(str(value))) if value else ''


def retention_exclusion(project, session_ids, config):
    excluded = {_path(value) for value in config.get('retainExcludedCwds', []) if value}
    if _path(project) in excluded:
        return 'configured_project_exclusion'
    ids = str(session_ids).split(',') if isinstance(session_ids, str) else (session_ids or [])
    excluded_sessions = {str(v) for v in config.get('retainExcludedSessionIds', []) if v}
    if any(str(v).strip() in excluded_sessions for v in ids):
        return 'configured_session_exclusion'
    return ''


def allowed_retention_batches(batches, config):
    return [b for b in batches if not retention_exclusion(b.get('project'), b.get('session_ids'), config)]
