"""Honor explicit navigation review holds before search results leave the API."""
import json
from pathlib import Path


def filter_known_review_holds(rows, review_path=None):
    path=Path(review_path) if review_path else Path.home()/'.evolving-profile/catalog/knowledge-page-review.json'
    try:
        reviews=json.loads(path.read_text(encoding='utf-8')).get('pages',{})
    except (OSError,ValueError,TypeError):
        return rows
    # Unknown external pages retain the upstream search contract. Explicitly
    # held EP pages must not be offered as relevant, usable navigation.
    return [row for row in rows if row.get('id') not in reviews or reviews[row['id']].get('state')=='approved']
