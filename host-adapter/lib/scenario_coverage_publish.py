"""New navigation contract never upgrades or relaxes legacy v3 acceptance."""
from .scenario_coverage_contract import contract,fingerprint
from .scenario_global_review import valid_global_coverage


def publish_segmented_navigation(snapshot,drafts,coverage,*,expected_generation,store=None,permission=None):
    if not valid_global_coverage(coverage) or coverage.get('status')!='accepted':raise ValueError('coverage_not_accepted')
    if (coverage.get('snapshot_id')!=snapshot.get('snapshot_id') or expected_generation!=snapshot.get('generation')
            or coverage.get('generation')!=expected_generation):raise ValueError('stale_generation')
    if store is None or not store.validate_snapshot(snapshot['snapshot_id'],permission)['valid']:
        raise ValueError('publication_source_or_permission_unverified')
    latest=store.read(snapshot['snapshot_id'])
    if latest['generation']!=expected_generation or not latest['source_manifest_complete']:raise ValueError('stale_generation')
    if drafts.get('schema') not in {None,contract()['navigation_schema']}:raise ValueError('legacy_schema_not_segmented')
    return {'schema':contract()['navigation_schema'],'coverage_contract':contract()['schema'],
        'snapshot_id':snapshot['snapshot_id'],'generation':expected_generation,'coverage':dict(coverage),
        'full_is_navigation_with_coverage_links':True,'has_unread_requirements':bool(coverage['requirement_states']),
        'requires_readback':True,'source_readback':False,'external_fact_verified':False,
        'summary':drafts.get('summary',{}),'draft_sha256':fingerprint(drafts),
        'status':'accepted_navigation_not_external_fact_verification','legacy_v3_acceptance':False}
