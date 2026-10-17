import copy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from lib.scenario_coverage_store import CoverageStore, freeze_snapshot
from lib.scenario_source_codec import locate_source, open_source_stream, read_source_batch
from test_scenario_source_codec import SID, source


def prepared(tmp_path):
    root,path,_=source(tmp_path)
    loc=locate_source(SID,root)
    permission={'allowed':True,'version':'p1'}
    snapshot=freeze_snapshot(loc,permission)
    store=CoverageStore(tmp_path/'coverage.sqlite3')
    store.create_snapshot(snapshot)
    with open_source_stream(loc,permission=lambda:True) as stream:batch=read_source_batch(stream)
    return store,snapshot,batch,path,permission


def test_structure_complete_does_not_claim_semantic_acceptance(tmp_path):
    store,snapshot,batch,_,permission=prepared(tmp_path)
    result=store.append_source_batch(snapshot['snapshot_id'],batch,expected_version=0,permission=permission)
    assert result['source_manifest_complete'] is True
    assert result['semantic_review_status']=='not_reviewed'
    assert result['unit_count']==4 and result['selected_count']==2
    assert result['external_fact_verified'] is False
    assert store.validate_snapshot(snapshot['snapshot_id'],permission)['valid'] is True


def test_changed_source_permission_or_old_cas_rejected(tmp_path):
    store,snap,batch,path,p=prepared(tmp_path)
    store.append_source_batch(snap['snapshot_id'],batch,expected_version=0,permission=p)
    with pytest.raises(ValueError,match='stale_generation'):
        store.append_source_batch(snap['snapshot_id'],batch,expected_version=0,permission=p)
    assert not store.validate_snapshot(snap['snapshot_id'],{'allowed':False,'version':'p1'})['valid']
    path.write_bytes(path.read_bytes()+b'{}\n')
    assert not store.validate_snapshot(snap['snapshot_id'],p)['valid']
    assert store.read(snap['snapshot_id'])['unit_count']==4


def test_corrupt_unit_hash_or_sequence_never_enters_ledger(tmp_path):
    store,snap,batch,_,p=prepared(tmp_path)
    for key,value in [('text','invented'),('sequence',200),('role','assistant')]:
        bad=copy.deepcopy(batch);bad['units'][2][key]=value
        with pytest.raises(ValueError,match='invalid_source_batch'):
            store.append_source_batch(snap['snapshot_id'],bad,expected_version=0,permission=p)
    assert store.read(snap['snapshot_id'])['unit_count']==0


def test_plain_dict_cannot_impersonate_a_verified_source_batch(tmp_path):
    store,snap,batch,_,p=prepared(tmp_path)
    with pytest.raises(ValueError,match='invalid_source_batch'):
        store.append_source_batch(snap['snapshot_id'],dict(batch),expected_version=0,permission=p)


def test_concurrent_cas_does_not_double_count_units(tmp_path):
    store,snap,batch,_,p=prepared(tmp_path)
    def write(_):
        try:return store.append_source_batch(snap['snapshot_id'],batch,expected_version=0,permission=p)['unit_count']
        except ValueError:return 'stale'
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(write,range(2)))
    assert sorted(map(str,results))==['4','stale']
    assert store.read(snap['snapshot_id'])['unit_count']==4


def test_semantic_budget_identity_survives_plain_to_zstd(tmp_path):
    a=tmp_path/'a';b=tmp_path/'b';a.mkdir();b.mkdir()
    root1,_,_=source(a);root2,_,_=source(b,True)
    store=CoverageStore(tmp_path/'coverage.sqlite3');identities=[]
    for root in [root1,root2]:
        loc=locate_source(SID,root);p={'allowed':True,'version':'p1'};snap=freeze_snapshot(loc,p);store.create_snapshot(snap)
        with open_source_stream(loc,permission=lambda:True) as stream:batch=read_source_batch(stream)
        identities.append(store.append_source_batch(snap['snapshot_id'],batch,expected_version=0,permission=p)['semantic_budget_identity'])
    assert identities[0]==identities[1] and identities[0]
