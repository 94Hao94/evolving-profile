#!/usr/bin/env python3
"""Preview or explicitly project verified product metadata into one selected state root."""
import argparse,hashlib,json,re,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'guidance'))
from ep_platform_lock import file_lock,atomic_replace_bytes

def digest(raw):return hashlib.sha256(raw).hexdigest()
def project(source,state,*,apply=False,expected=None):
    source=Path(source);state=Path(state).absolute();target=state/'config/release-manifest.json'
    version=(source/'VERSION').read_text().strip()
    payload=(source/'config/release-manifest.json').read_bytes();manifest=json.loads(payload)
    if not re.fullmatch(r'\d+\.\d+\.\d+',version) or not isinstance(manifest,dict) or manifest.get('product_version')!=version:
        raise ValueError('release_manifest_version_mismatch')
    if target.is_symlink():raise ValueError('symlink_target_rejected')
    before=target.read_bytes() if target.exists() else None
    report={'status':'preview','product_version':version,'target':str(target),
        'before_sha256':digest(before) if before is not None else None,'source_sha256':digest(payload)}
    if not apply:return report
    if expected is None:raise ValueError('explicit_expected_revision_required')
    wanted=None if expected=='absent' else expected
    with file_lock(target.with_name('release-projection.transaction.lock')):
        if target.is_symlink():raise ValueError('symlink_target_rejected')
        before=target.read_bytes() if target.exists() else None
        actual=digest(before) if before is not None else None
        if actual!=wanted:raise ValueError('revision_conflict')
        backup=None
        if before is not None:
            backup=target.with_name('release-manifest.backup-'+uuid.uuid4().hex+'.json')
            atomic_replace_bytes(backup,before)
        after=atomic_replace_bytes(target,payload,expected_sha256=wanted)
    return {**report,'status':'applied','after_sha256':after,'backup':str(backup) if backup else None,
        'authority':'verified_source_VERSION_and_release_manifest','other_configuration_changed':False}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root',type=Path,required=True)
    parser.add_argument('--apply',action='store_true');parser.add_argument('--expected-sha256')
    args=parser.parse_args()
    try:
        print(json.dumps(project(ROOT,args.state_root,apply=args.apply,expected=args.expected_sha256),indent=2));return 0
    except (OSError,ValueError):
        print(json.dumps({'status':'failed','reason':'projection_rejected_or_unavailable','state_changed':'inspect_selected_target'}));return 2
if __name__=='__main__':raise SystemExit(main())
