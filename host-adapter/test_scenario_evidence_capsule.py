import copy
import pytest
try:
    from lib.scenario_evidence_capsule import build_capsules,restore_capsules
except ImportError:
    build_capsules=restore_capsules=None


def test_capsule_pages_preserve_all_atoms_and_exact_long_conditions():
    assert build_capsules is not None
    rows=[{'atom_id':str(i),'source_quote':'仅草稿，不要发布🙂'*50,'conditions':['if draft'],'unresolved':True} for i in range(3)]
    value=build_capsules({'protocol':'hierarchical_review.v1'},rows,[],[],{'partition_input_tokens':700})
    restored=restore_capsules(value)
    assert restored['atoms']==rows
    assert len(value['pages'])>3
    bad=copy.deepcopy(value);bad['pages'].pop()
    with pytest.raises(ValueError):restore_capsules(bad)


def test_duplicate_owner_is_rejected():
    assert build_capsules is not None
    with pytest.raises(ValueError):build_capsules({},[{'atom_id':'same'},{'atom_id':'same'}],[],[],{'partition_input_tokens':1000})
