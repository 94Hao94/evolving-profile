"""Preparation receipts cannot certify an unexecuted platform or native host."""
import os

REQUIRED=('disabled_tool_denied_stdio','disabled_tool_denied_http','owner_isolation','source_gap')


def build_acceptance_manifest(test_receipts,registry):
    valid=[row for row in test_receipts if isinstance(row,dict)]
    counts=[r.get('provider_calls') for r in valid]
    usage=sum(counts) if counts and all(type(v) is int and v>=0 for v in counts) else None
    missing=[name for name in REQUIRED if not any(r.get('check_id')==name and r.get('status')=='passed' for r in valid)]
    status='not_run' if not valid else 'budget_violation' if usage and usage>0 else 'blocked' if any(r.get('status')=='blocked' for r in valid) else 'failed' if any(r.get('status')=='failed' for r in valid) else 'partial' if missing or usage is None else 'preparation_checks_passed'
    return {'schema':'ep.host-acceptance.v1','registry_revision':registry.get('sha256',registry.get('revision')),
            'status':status,'provider_calls':usage,'missing_checks':missing,'real_host_verified':False,
            # Merely running this classifier on Windows does not execute the
            # platform acceptance checks or turn fixture input into evidence.
            'windows_execution':'not_run',
            'hosts':{row['id']:{'native_host':'unverified','automatic_capture':'unverified'} for row in registry['profiles']},
            'test_receipts':valid,'scope':'preparation_not_full_host_certification'}


def render_matrix(registry,locale):
    zh=locale.startswith('zh');yes='文档支持' if zh else 'Documented';unknown='未知' if zh else 'Unknown'
    lines=[('# 宿主准备矩阵' if zh else '# Host preparation matrix'),'',
        ('注册表修订：' if zh else 'Registry revision: ')+str(registry.get('sha256',registry.get('revision'))),'',
        '| ID | '+('宿主 | 本地 MCP | HTTP MCP | 提问钩子 | 宿主实测' if zh else 'Host | Local MCP | HTTP MCP | Prompt hook | Native host')+' |',
        '| --- | --- | --- | --- | --- | --- |']
    for row in registry['profiles']:
        capabilities=row.get('documented',{})
        cells=[yes if capabilities.get(k) is True else unknown for k in ('mcp_stdio','mcp_http','prompt_hook')]
        label=row.get('labels',{}).get('zh-CN' if zh else 'en',row['id'])
        lines.append('| '+row['id']+' | '+label+' | '+' | '.join(cells)+' | '+('未实测' if zh else 'Unverified')+' |')
    lines+=['',('本表是配方与文档证据，不是当前宿主或 Windows 实测通过。' if zh else 'Recipes and documentary evidence only; not native-host or Windows certification.'),'']
    return '\n'.join(lines)
