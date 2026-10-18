"""One native rollout-location contract for active and archived sources."""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path


def session_roots(root):
    root=Path(root).expanduser()
    # The sibling archive belongs to Codex's documented directory layout,
    # not to arbitrary user-selected folders.
    roots=[root]
    if root.name=='sessions':roots.append(root.parent/'archived_sessions')
    return list(dict.fromkeys(roots))


def session_paths(root,session_id,*,max_compare_bytes=16*1024*1024):
    if type(max_compare_bytes) is not int or max_compare_bytes<1:
        raise ValueError('source_comparison_budget_must_be_positive_integer')
    sid=str(uuid.UUID(str(session_id)))
    paths=[]
    compressed=[]
    for location in session_roots(root):
        if location.is_dir():
            paths.extend(sorted(location.rglob(f'rollout-*-{sid}.jsonl')))
            compressed.extend(sorted(location.rglob(f'rollout-*-{sid}.jsonl.zst')))
    paths=list(dict.fromkeys(paths))
    if compressed:
        # A filename is a presence clue, not an authenticated native identity.
        # Do not claim absence or choose a conflicting plain copy without
        # bounded decompression and content-equivalence validation.
        return {'status':'source_compressed_unavailable','paths':list(dict.fromkeys(paths+compressed)),
                'coverage':{'partial':True,'source_presence':'compressed_file_present_unverified',
                            'source_identity':'unknown','scan_complete':False,
                            'reason':'compressed_source_readback_not_supported'}}
    if not paths:return {'status':'source_missing','paths':[]}
    if len(paths)>8:return {'status':'too_many_source_files','paths':paths}
    for path in paths:
        try:
            with path.open('rb') as stream:
                first=stream.readline(1024*1024+1)
            header=json.loads(first)
        except OSError:
            return {'status':'source_incomplete','paths':paths}
        except (ValueError,UnicodeError):
            # Active legacy files may begin with a partial append; the
            # incremental reader retains its old checkpoint/empty behavior.
            # An archive must carry a complete native identity header.
            if path.is_relative_to(Path(root).expanduser().parent/'archived_sessions'):
                return {'status':'source_incomplete','paths':paths}
            continue
        if isinstance(header,dict) and header.get('type')=='session_meta':
            payload=header.get('payload')
            if not isinstance(payload,dict) or payload.get('id')!=sid:
                return {'status':'source_identity_mismatch','paths':paths}
        elif path.is_relative_to(Path(root).expanduser().parent/'archived_sessions'):
            return {'status':'source_identity_mismatch','paths':paths}
    if len(paths)>1:
        digests=[]
        remaining=max_compare_bytes
        try:
            for path in paths:
                digest=hashlib.sha256()
                with path.open('rb') as stream:
                    while True:
                        if remaining<=0:
                            if stream.tell()<path.stat().st_size:
                                return {'status':'source_comparison_incomplete','paths':paths,
                                        'coverage':{'partial':True,'scan_complete':False,
                                                    'reason':'duplicate_comparison_budget_exhausted'}}
                            break
                        block=stream.read(min(1024*1024,remaining))
                        if not block:break
                        digest.update(block);remaining-=len(block)
                digests.append(digest.digest())
        except OSError:
            return {'status':'source_incomplete','paths':paths}
        if len(set(digests))!=1:return {'status':'source_ambiguous','paths':paths}
    return {'status':'ready','paths':paths[:1],'duplicate_copy_count':len(paths)-1}
