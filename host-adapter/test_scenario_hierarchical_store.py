import pytest
try:
    from lib.scenario_hierarchical_store import HierarchicalStore
except ImportError:HierarchicalStore=None


def test_store_cas_keeps_versions_and_scope_and_permissions(tmp_path):
    assert HierarchicalStore is not None
    store=HierarchicalStore(tmp_path/'graph.sqlite')
    b={'scope':{'session_id':'s'},'permission':{'allowed':True,'version':'p'},'snapshot_id':'one'}
    saved=store.save_generation(b,{'nodes':{},'coverage':{'target_complete':False}},expected_version=0)
    assert saved['version']==1
    with pytest.raises(ValueError):store.save_generation(b,{},expected_version=0)
    assert store.load_current(b['scope'],b['permission'])['binding']['snapshot_id']=='one'
    with pytest.raises(ValueError):store.load_current(b['scope'],{'allowed':False})
    with pytest.raises(ValueError):store.load_current({'session_id':'other'},b['permission'])


def test_symlink_store_is_rejected(tmp_path):
    assert HierarchicalStore is not None
    link=tmp_path/'link';link.symlink_to(tmp_path/'outside')
    with pytest.raises(ValueError):HierarchicalStore(link)
