import json
from pathlib import Path
import tempfile
import unittest
from evolving_profile_api.engine.navigation_review import filter_known_review_holds


class NavigationReviewTest(unittest.TestCase):
    def test_explicit_review_holds_do_not_outrank_relevant_catalog_results(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'review.json'
            path.write_text(json.dumps({'pages':{'held':{'state':'needs_review'},'ok':{'state':'approved'}}}))
            rows=[{'id':'held','name':'Wrong technical page'},{'id':'ok'},{'id':'external'}]
            self.assertEqual([v['id'] for v in filter_known_review_holds(rows,path)],['ok','external'])

    def test_absent_registry_does_not_change_other_installations(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(filter_known_review_holds([{'id':'outside'}],Path(root)/'none'),[{'id':'outside'}])
