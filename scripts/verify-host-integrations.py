#!/usr/bin/env python3
"""Offline host preparation suite. Never installs hosts or calls providers."""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--collect-only',action='store_true')
    args=parser.parse_args()
    tests=sorted(str(p.relative_to(root)) for p in (root/'host-adapter').glob('test_host_integration_*.py'))
    tests+=['host-adapter/test_governed_mcp_http.py','guidance/test_ep_platform_lock.py',
            'scripts/test_ep_host_cli.py','scripts/test_host_acceptance_manifest.py']
    env={**os.environ,'PYTHONPATH':os.pathsep.join(str(root/p) for p in ('host-adapter','guidance','controller','ham-os')),
         'EVOLVING_PROFILE_GUIDANCE_SRC':str(root/'guidance'),'PYTHONDONTWRITEBYTECODE':'1'}
    command=[sys.executable,'-m','pytest','-q',*tests]
    if args.collect_only:command.append('--collect-only')
    return subprocess.run(command,cwd=root,env=env).returncode


if __name__=='__main__':raise SystemExit(main())
