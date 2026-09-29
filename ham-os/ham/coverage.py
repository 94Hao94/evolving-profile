from __future__ import annotations
def receipt(required,covered):
 required=list(required); covered=list(dict.fromkeys(covered)); missing=[x for x in required if x not in covered]
 return {'schema':'ham.coverage_receipt.v1','required_dimensions':required,'covered_dimensions':covered,'missing_dimensions':missing,'coverage_status':'complete' if not missing else 'incomplete'}
