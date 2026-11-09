#!/usr/bin/env python3
"""Explicit optional launch; importing this module never starts a listener."""
import argparse
import json
from pathlib import Path
from lib.host_integration.http_transport import create_governed_http_app


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings',type=Path,required=True)
    parser.add_argument('--port',type=int,default=12080)
    args=parser.parse_args();settings=json.loads(args.settings.read_text())
    app=create_governed_http_app(settings)
    import uvicorn
    uvicorn.run(app,host=settings.get('bind_host','127.0.0.1'),port=args.port,log_level='warning')


if __name__=='__main__':main()
