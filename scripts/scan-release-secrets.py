#!/usr/bin/env python3
"""Scan release-owned text without printing credentials or installed vendor examples."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

GENERATED={'.git','.superpowers','node_modules','.venv','.next','standalone','output','__pycache__','.pytest_cache'}
LOCAL_ENV={'.env','.env.local','.env.development.local','.env.production.local','.env.test.local'}
PATTERNS=[('api_key',re.compile(r'(?:sk-|gsk_)[A-Za-z0-9]{12,}')),
    ('cloud_key',re.compile(r'AKIA[0-9A-Z]{16}')),
    ('private_key',re.compile(r'BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY')),
    ('personal_name',re.compile('\u5218\u4e2d\u6d0b')),
    ('personal_bank',re.compile('liuzhongyang'+'-memory-core'))]
if len(Path.home().parts)>1:
    PATTERNS.append(('local_home_path',re.compile(re.escape(str(Path.home())))))


def display_path(path):
    value=str(path)
    for _,pattern in PATTERNS:value=pattern.sub('[redacted]',value)
    return value


def generated(part):
    return part in GENERATED or part.startswith('node_modules.')


def scan(root):
    findings=[];scanned=0;local_env=[]
    git=subprocess.run(['git','-C',str(root),'rev-parse','--show-toplevel'],capture_output=True,text=True)
    tracked=set()
    if git.returncode==0 and Path(git.stdout.strip()).resolve()==root:
        listing=subprocess.run(['git','-C',str(root),'ls-files','-z'],capture_output=True,check=True)
        tracked={Path(p.decode()) for p in listing.stdout.split(b'\0') if p}
        for rel in tracked:
            if rel.name in LOCAL_ENV:findings.append({'path':display_path(rel),'reason':'tracked_local_environment'})
            elif any(generated(part) for part in rel.parts):findings.append({'path':display_path(rel),'reason':'tracked_runtime_artifact'})
    for directory,dirs,names in os.walk(root,followlinks=False):
        source_dirs=[]
        for name in dirs:
            if generated(name):continue
            p=Path(directory)/name
            if p.is_symlink():
                findings.append({'path':display_path(p.relative_to(root)),'reason':'unverified_source_symlink'})
            else:source_dirs.append(name)
        dirs[:]=source_dirs
        for name in names:
            p=Path(directory)/name;rel=p.relative_to(root)
            if generated(name):continue
            if name in LOCAL_ENV and rel not in tracked:
                local_env.append(display_path(rel));continue
            if p.is_symlink():
                findings.append({'path':display_path(rel),'reason':'unverified_source_symlink'});continue
            try:
                if p.stat().st_size>32*1024*1024:
                    findings.append({'path':display_path(rel),'reason':'source_scan_size_limit'});continue
                raw=p.read_bytes()
                if b'\0' in raw:continue
                text=raw.decode('utf-8')
            except UnicodeDecodeError:continue  # Binary assets need separate visual checks.
            except OSError:
                findings.append({'path':display_path(rel),'reason':'source_unreadable'});continue
            scanned+=1
            for number,line in enumerate(text.splitlines(),1):
                for kind,pattern in PATTERNS:
                    if pattern.search(line):findings.append({'path':display_path(rel),'line':number,'reason':kind})
    return {'status':'failed' if findings else 'passed','scanned_text_files':scanned,
        'excluded_local_environment':local_env,'findings':findings,
        'boundary':'release text source only; local env/dependencies/builds excluded; not a binary-asset or dependency vulnerability audit'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True)
    value=scan(parser.parse_args().root.resolve());print(json.dumps(value,ensure_ascii=False))
    print('secret and personal-data scan passed' if value['status']=='passed' else 'secret or personal-data scan failed')
    return 0 if value['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
