"""Refresh derived guidance vectors outside the UserPromptSubmit latency budget."""
from __future__ import annotations

import json
import os
from pathlib import Path
import time

from mcp_runtime import load_repository
from semantic_recall import LocalGuidanceEmbeddingClient, SemanticVectorCache


def main() -> None:
    state_root=Path(os.environ.get('EVOLVING_PROFILE_STATE_ROOT',str(Path.home()/'.evolving-profile')))
    config=state_root/'guidance-v1'/'guidance-v1.json'
    bank=os.environ.get('EVOLVING_PROFILE_GUIDANCE_BANK_ID','personal-memory')
    base=os.environ.get('EVOLVING_PROFILE_SOURCE_API_URL','http://127.0.0.1:12088')
    cache_path=state_root/'guidance-v1'/'semantic-vectors.json'
    repo=load_repository(config)
    units=[unit for unit in repo.active_units() if (unit.get('preference_audit') or {}).get('state') in {'approved','restricted'}]
    client=LocalGuidanceEmbeddingClient(f'{base.rstrip("/")}/v1/default/banks/{bank}/internal/guidance-embeddings',timeout_seconds=20)
    started=time.perf_counter()
    vectors=SemanticVectorCache(cache_path,embed_many=lambda texts:client.embed_many(texts,'document')).document_vectors(units)
    print(json.dumps({'status':'ready','unit_count':len(units),'vector_count':len(vectors),'elapsed_ms':round((time.perf_counter()-started)*1000,1),'cache_path':str(cache_path)}))


if __name__ == '__main__':
    main()
