"""Small, local-only navigation supplied before the Agent chooses deeper reads."""
from __future__ import annotations

from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
import re
from pathlib import Path
import sqlite3

CATEGORY_NAMES = {
    "communication": "沟通与呈现",
    "learning": "学习与理解",
    "reasoning": "分析与决策",
    "collaboration": "执行与协作",
    "delivery": "质量与交付",
}
CATALOG_PATH = Path.home() / ".evolving-profile/catalog/topics.sqlite3"
MAX_CONTEXT_CHARS = 2200


def _clip(value, limit):
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _connect(path):
    # No constructors that create schemas; missing stores must stay missing.
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=0.1)
    db.row_factory = sqlite3.Row
    return db


def _scope(value):
    return re.sub(r'^(?:适用于|所有涉及|涉及|进行|为|在)|(?:的场景[。.]?|场景[。.]?|时[。.]?)$', '', str(value or '')).strip()


def _diverse(rows, limit, text_key):
    """Stable, query-independent preview; no row is excluded from deeper reads."""
    unique={row[text_key]:row for row in sorted(rows,key=lambda row:row['id'],reverse=True) if row.get(text_key)}
    pending=sorted(unique.values(),key=lambda row:row['id']);selected=[];covered=set()
    while pending and len(selected)<limit:
        def tokens(row):
            text=re.sub(r'\s+', '',row[text_key].casefold())
            return {text[i:i+2] for i in range(len(text)-1)} or {text}
        def score(row):
            terms=tokens(row)
            return (len(terms-covered)/max(1,len(terms)), -len(row[text_key]))
        chosen=max(pending,key=score);selected.append(chosen);covered.update(tokens(chosen));pending.remove(chosen)
    return selected


def _preference_index(config_path):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    registry = Path(config["registry"]).expanduser()
    with closing(_connect(registry)) as db:
        db.execute('BEGIN')
        states = dict(db.execute("""
            SELECT coalesce(a.state,'not_reviewed'), count(*) FROM unit_revisions u
            LEFT JOIN unit_audits a USING(unit_id,revision)
            WHERE u.active=1 GROUP BY 1
        """))
        rows = [dict(row) for row in db.execute("""
            SELECT u.unit_id AS id, u.revision,
                json_extract(u.payload_json,'$.primary_category') AS category,
                json_extract(u.payload_json,'$.text') AS text,
                json_extract(u.payload_json,'$.applies_when') AS applies_when
            FROM unit_revisions u JOIN unit_audits a USING(unit_id,revision)
            WHERE u.active=1 AND a.state='approved'
            ORDER BY u.unit_id
        """)]
        model_count = db.execute("SELECT count(*) FROM model_revisions WHERE active=1").fetchone()[0]
    counts = Counter(row["category"] for row in rows)
    dimensions = []
    for category, label in CATEGORY_NAMES.items():
        members=[row for row in rows if row['category']==category]
        scopes=[]
        for row in members:
            conditions=json.loads(row['applies_when'] or '[]')
            if isinstance(conditions,str):conditions=[conditions]
            for condition in conditions:
                scopes.append({'id':row['id'],'scope':_scope(condition)})
        previews=_diverse(scopes,7,'scope')
        examples=[{**row,'clue':_clip(row['text'],44)} for row in _diverse(members,1,'text')]
        dimensions.append({"id":category,"label":label,"count":counts[category],"examples":examples,
                           'scopes':previews,'scope_count':len({row['scope'] for row in scopes})})
    return {
        "status": "available", "approved_count": len(rows), "active_count": sum(states.values()),
        "withheld_count": sum(states.values()) - len(rows), "model_count": model_count,
        "preview_count": sum(len(row["examples"]) for row in dimensions), "dimensions": dimensions,
        "coverage": "all_reviewed_units_considered_diverse_scope_preview_not_exhaustive",
        "freshness": "live_registry_read_each_prompt",
        "revision": sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12],
        "read_more": "Get Preference → read_guidance / read_guidance_unit",
    }


def catalog_freshness(path, metadata, now=None):
    now=now or datetime.now(timezone.utc)
    try:
        state=json.loads(Path(path).with_suffix('.refresh.json').read_text(encoding='utf-8'))
        if not isinstance(state,dict):raise ValueError('invalid_refresh_state')
        checked=datetime.fromisoformat(state['checked_at'])
        age=(now-checked).total_seconds()
        if age < -60 or age>state.get('stale_after_seconds',180):status='stale'
        elif state.get('status')=='failed':status='failed'
        elif state.get('status')=='refreshing':status='refreshing'
        elif state.get('status')!='ready' or state.get('snapshot_revision')!=metadata.get('revision'):status='unknown'
        else:status='checked'
        return {'status':status,'age_seconds':max(0,round(age)), 'checked_at':state['checked_at'],
                'generated_at':metadata.get('generated_at'),'refresh_interval_seconds':state.get('refresh_interval_seconds')}
    except (OSError,ValueError,KeyError,TypeError):return {'status':'unknown'}


def _bank_index(path):
    with closing(_connect(path)) as db:
        db.execute('BEGIN')
        metadata={}
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='catalog_meta'").fetchone():
            meta=db.execute("SELECT value_json FROM catalog_meta WHERE key='snapshot'").fetchone()
            if meta:metadata=json.loads(meta[0])
            if not isinstance(metadata,dict):raise ValueError('invalid_catalog_metadata')
        count = db.execute("SELECT count(*) FROM topics").fetchone()[0]
        entity_count = db.execute("SELECT count(*) FROM topics WHERE topic_id LIKE 'entity:%'").fetchone()[0]
        searchable_count = db.execute("SELECT count(*) FROM entity_index").fetchone()[0] if db.execute("SELECT 1 FROM sqlite_master WHERE name='entity_index'").fetchone() else None
        manifest_count = db.execute("SELECT count(*) FROM topics WHERE topic_id LIKE 'manifest:%' AND json_extract(payload_json,'$.content_status')='reviewed_navigation_manifest'").fetchone()[0]
        rows = [dict(row) for row in db.execute("""
            SELECT topic_id, substr(json_extract(payload_json,'$.title'),1,80) AS title,
                substr(json_extract(payload_json,'$.overview'),1,300) AS overview, updated_at
                ,json_extract(payload_json,'$.navigation_summary') AS navigation_summary
                ,json_extract(payload_json,'$.source_count') AS source_count
                ,json_extract(payload_json,'$.example_entities') AS example_entities
            FROM topics WHERE topic_id LIKE 'manifest:%'
                AND json_extract(payload_json,'$.content_status')='reviewed_navigation_manifest'
            ORDER BY topic_id LIMIT 12
        """)]
        domain_rows=[{**json.loads(row[1]),'topic_id':row[0]} for row in db.execute("SELECT topic_id,payload_json FROM topics WHERE json_extract(payload_json,'$.level')='L0' ORDER BY topic_id")]
        if domain_rows:
            rows=[{**{key:row.get(key) for key in ('topic_id','title','overview','navigation_summary','source_count','source_count_semantics','memory_count','children','child_previews','fact_types','level')},'updated_at':row.get('refreshed_at')} for row in domain_rows]
            manifest_count=len(rows)
    return {
        "status": "available", "topic_count": count, "entity_count": entity_count, "searchable_entity_count": searchable_count,
        "manifest_count": manifest_count, "topics": rows,
        "hierarchy_coverage":metadata.get('hierarchy_coverage') or {},
        "metadata":metadata,"freshness":catalog_freshness(path,metadata),
        "coverage": "reviewed_manifest_roots_not_exhaustive_bank_coverage",
        "refreshed_at": min((row["updated_at"] for row in rows if row["updated_at"]), default=None),
        "read_more": "catalog_list / catalog_search / catalog_read → recall / research → read_source",
    }


def build_navigation_map(config_path, policy, *, catalog_path=None):
    """No prompt relevance filter, network, embeddings, or full source reads."""
    lanes = {}
    for name, allowed, loader in (
        ("preferences", policy.get("guidance_memory_policy") != "forbidden", lambda: _preference_index(config_path)),
        ("bank", policy.get("history_allowed", True) and "catalog" not in policy.get("denied_tools", []),
         lambda: _bank_index(catalog_path or CATALOG_PATH)),
    ):
        if not allowed:
            lanes[name] = {"status": "forbidden"}
            continue
        try:
            lanes[name] = loader()
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError) as exc:
            lanes[name] = {"status": "unavailable", "error": type(exc).__name__}
    snapshot = {"schema": "evolving-profile.entry-navigation.v2", "boundary": "navigation_only",
                "bank_query_count": 0, "model_calls": 0, **lanes}
    lines = ["轻量地图：导航线索，不是事实或行动指令。先看可用范围，再决定深读；未列出不能排除相关内容。"]
    prefs = lanes["preferences"]
    corpus_map=bool(lanes['bank'].get('hierarchy_coverage'))
    if prefs["status"] == "available":
        lines.append(f"偏好：每轮读当前库，已审阅 {prefs['approved_count']} 条均参与场景选样，展示为部分场景；未审阅/失效 {prefs['withheld_count']} 条不展示；融合模型 {prefs['model_count']} 个。版本 {prefs['revision']}。")
        for row in prefs["dimensions"]:
            scopes=' / '.join(_clip(item['scope'],18 if corpus_map else 22) for item in row['scopes'])
            example=row['examples'][0]['clue'] if row['examples'] else ''
            lines.append(f"{row['label']} {row['count']} 条｜{scopes or '暂无已审阅条目'}"+(f"；例：{example}" if example and not corpus_map else ''))
        lines.append("偏好下钻：Get Preference；使用前读完整条件/例外，deferred 用 read_guidance/read_guidance_unit 补读。")
    else:
        lines.append("偏好索引：本轮禁止读取。" if prefs["status"] == "forbidden" else "偏好索引：不可用，不代表没有偏好。")
    bank = lanes["bank"]
    if bank["status"] == "available":
        meta=bank['metadata'];fresh=bank['freshness']
        status={'checked':'已核对源版本','refreshing':'正在更新，旧图仍可读','failed':'更新失败，沿用旧图','stale':'核对已过期','unknown':'更新状态未知'}[fresh['status']]
        lines.append(f"Bank：{bank['entity_count']} 个实体在轻量预览；{bank['searchable_entity_count'] or '未知'} 个可按名称查目录；{bank['manifest_count']} 个主题。{status}；距核对 {fresh.get('age_seconds','未知')} 秒。")
        coverage=bank.get('hierarchy_coverage') or {}
        if coverage:
            lines.append(f"全库导航：{coverage.get('indexed_memory_count',0)}/{coverage.get('total_memory_count',0)}条记录已归组，{coverage.get('unassigned_memory_count',0)}条待整理；跨领域计数有重叠，摘要样本检查不等于逐条语义核实。")
            lines.append('以下每个domain入口用catalog_read进入L1子主题；L1提供问题、别名及L2来源ID。')
        elif meta.get('semantic_status')=='fresh_with_pending_changes':lines.append('模型摘要已审阅，最近新增资料排队整理；结构目录仍可查，历史缺口可直接 recall/research。')
        elif meta.get('semantic_status')!='ready':lines.append('模型语义目录待更新或已超时；结构目录仍可查，历史缺口可直接 recall/research。')
        outside=meta.get('recent_outside_manifests') or []
        if outside and not corpus_map:
            lines.append('主题外近期有源更新的对象（可直接 recall/research）：'+'、'.join(_clip(row.get('title'),22) for row in outside[:4]))
        shown = 0
        root_clue_limit=40
        if corpus_map and bank['topics']:
            available=MAX_CONTEXT_CHARS-len(escape('\n'.join(lines),quote=False))-300
            overhead=sum(len(str(r['topic_id']))+len(_clip(r['title'],18))+len(f"；{r.get('memory_count',0)}条/{len(r.get('children') or [])}个L1")+4 for r in bank['topics'])
            root_clue_limit=max(12,min(60,(available-overhead)//len(bank['topics'])))
        for row in bank["topics"]:
            question = str(row.get("overview") or '').replace("可导航问题：", "").strip().lstrip("- ").split("\n")[0]
            title = _clip(row["title"], 40) + ("（EP）" if row["topic_id"] == "manifest:architecture" else "")
            clue=row.get('navigation_summary') or question
            sources=f"；样本≥{row['source_count']}文档" if row.get('source_count') else '；未配到样本'
            line = f"{_clip(row['topic_id'], 48)}｜{title}：{_clip(clue, 34)}{sources}"
            if corpus_map:
                line=f"{row['topic_id']}｜{_clip(row['title'],18)}：{_clip(clue,root_clue_limit)}；{row.get('memory_count',0)}条/{len(row.get('children') or [])}个L1"
            # Reserve room for the deeper-read route, coverage warning and tags.
            if not corpus_map and len(escape('\n'.join([*lines, line]), quote=False)) > MAX_CONTEXT_CHARS - 380:
                break
            lines.append(line)
            shown += 1
        bank['shown_manifest_count'] = shown
        if shown < bank['manifest_count']:
            lines.append(f"本页主题 {shown}/{bank['manifest_count']}；其余用 catalog_list 翻页。未列出不代表没有。")
        lines.append("Bank 下钻：catalog_list/search/read；具体缺口 recall，多对象/时间线 research，结论 read_source 核实。目录工具未枚举时可直接查 recall/research。")
    else:
        lines.append("Bank 地图：本轮禁止读取。" if bank["status"] == "forbidden" else "Bank 地图：不可用，不代表 Bank 为空。")
    lines.append("示例没列出、目录没命中均不等于不存在；地图不证明偏好已采用或历史已召回。")
    body = escape("\n".join(lines), quote=False)
    context = '<evolving_profile_navigation_map mode="local_index_before_agent_choice">\n' + body + '\n</evolving_profile_navigation_map>'
    snapshot["context_chars"] = len(context)
    snapshot['context_text'] = context
    return context, snapshot
