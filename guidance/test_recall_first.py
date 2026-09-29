import sys
from pathlib import Path
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).parent))
from selector import get_task_guidance

def unit(uid,text,condition,category='delivery',state='approved'):
    return dict(id=uid,revision='v1',text=text,applies_when=[condition],exceptions=['当前要求优先'],scope={},primary_category=category,preference_audit={'state':state},evidence_refs=[{'quote':(uid+'原话')*1000}])

class Repo:
    def __init__(self,units):self.units=units
    def active_units(self):return self.units
    def active_models(self):return []
    def active_revision(self):return 'r1'

def request(text,context=''):
    return {'task':{'objective':text,'current_user_message':text,'context_summary':context,'phase':'execute'},'loaded':[],'memory_policy':'allowed'}

class RecallFirstTests(unittest.TestCase):
    def test_preference_candidate_limit_is_applied_before_packet_budget(self):
        rows=[unit(f'preference-{index}',f'当前任务相关协作规则 {index}', '当前任务相关协作规则') for index in range(10)]
        result=get_task_guidance(Repo(rows), {**request('当前任务相关协作规则'), 'max_candidates': 3})
        self.assertEqual(len(result['included']), 3)
        self.assertEqual(result['budget']['candidate_limit'], 3)
        self.assertEqual(result['preference_candidates'][0]['status'], 'candidate_requires_agent_judgment')

    def test_narrow_business_rule_cannot_enter_unrelated_cleanup_by_shared_verb(self):
        visit=unit('visit',"删除客户拜访统计中的去重客户日。",'客户拜访统计、签到计数及排名')
        result=get_task_guidance(Repo([visit]),request('旧的那个超大备份删除就行了','前一项任务：备份文件占用过大。'))
        self.assertEqual(result['included'],[])

    def test_non_continuation_context_does_not_select_previous_topic(self):
        explain=unit('explain','困难内容提供例子并解释英文术语。','知识解释与陌生术语学习','learning')
        req=request('检查本机哪些历史项目、缓存和备份待删除','前一项活动任务：解释Lark是什么。')
        req['task']['continuation']=False
        self.assertEqual(get_task_guidance(Repo([explain]),req)['included'],[])

    def test_conditional_preference_needs_current_task_evidence(self):
        ppt=unit('ppt','PPT交付前逐页检查排版。','制作汇报型PPT')
        self.assertEqual(get_task_guidance(Repo([ppt]),request('检查网站按钮'))['included'],[])
        self.assertEqual([r['id'] for r in get_task_guidance(Repo([ppt]),request('制作汇报型PPT'))['included']],['ppt'])
    def test_runtime_tool_failure_selects_recovery_guidance(self):
        recovery=unit('recover','当关键验证工具失败时，先修复该工具；替代验证不得写成原工具已通过。','工具故障与验收恢复','delivery')
        req=request('继续处理当前工作')
        req['task']['phase']='understand'
        req['task']['runtime_events']=[{'capability':'computer_use','failure':'get_state_timeout','occurrence':3,'required_for':'visual_interaction_acceptance'}]
        result=get_task_guidance(Repo([recovery]),req)
        self.assertEqual([item['id'] for item in result['included']],['recover'])

    def test_selector_unions_semantic_candidate_with_lexical_candidates(self):
        row=unit('verify','修复后必须在真实页面逐项点击验证。','网页功能验收')
        vectors={
            '把这次改动在浏览器里一个个操作确认': [1.0, 0.0],
            '修复后必须在真实页面逐项点击验证。 网页功能验收': [0.98, 0.02],
        }
        req=request('把这次改动在浏览器里一个个操作确认')
        req['_semantic_embed_many']=lambda texts:[vectors[text] for text in texts]
        result=get_task_guidance(Repo([row]),req)
        self.assertEqual([item['id'] for item in result['included']],['verify'])
        self.assertEqual(result['included'][0]['selection_reason']['semantic']['source'],'semantic')

    def test_selector_delivers_a_semantic_backfill_before_low_value_lexical_overflow(self):
        lexical=unit('lexical','修改文件时保持格式一致。','文件修改')
        semantic=unit('semantic','修复后必须在真实页面逐项点击验证。','网页功能验收')
        vectors={
            '把这次修改在浏览器里一个个操作确认': [1.0,0.0],
            '修改文件时保持格式一致。 文件修改': [0.0,1.0],
            '修复后必须在真实页面逐项点击验证。 网页功能验收': [0.99,0.02],
        }
        req=request('把这次修改在浏览器里一个个操作确认')
        req['_semantic_embed_many']=lambda texts:[vectors[text] for text in texts]
        result=get_task_guidance(Repo([lexical,semantic]),req)
        self.assertEqual(result['included'][0]['id'],'semantic')

    def test_selector_exposes_semantic_candidate_with_unmentioned_condition_for_agent_judgment(self):
        row=unit('windows','Windows 版本必须支持 U 盘便携运行。','Light Memory 产品的 Windows 版本开发与部署')
        vectors={
            '优化当前记忆系统的选择算法': [1.0, 0.0],
            'Windows 版本必须支持 U 盘便携运行。 Light Memory 产品的 Windows 版本开发与部署': [0.98, 0.02],
        }
        req=request('优化当前记忆系统的选择算法')
        req['_semantic_embed_many']=lambda texts:[vectors[text] for text in texts]
        result=get_task_guidance(Repo([row]),req)
        self.assertEqual([item['id'] for item in result['included']],['windows'])
        self.assertIn('named_condition_unmentioned',result['included'][0]['selection_reason']['applicability_risks'])

    def test_lexical_selector_rejects_unmentioned_named_platform_condition(self):
        row=unit('windows','记忆系统召回功能在 Light Memory 的 Windows 版本中必须支持 U 盘便携运行。','Light Memory 产品的 Windows 版本开发与部署')
        self.assertEqual(get_task_guidance(Repo([row]),request('核查当前记忆系统的选择和召回'))['included'],[])

    def test_semantic_backfill_does_not_inject_document_rules_into_arithmetic(self):
        chart=unit('chart','图表中的关键数字不能留空。','需要展示指标或图表时')
        word=unit('word','Word 表格使用固定行距。','Word 文档表格排版时')
        vectors={
            '17乘以23等于多少？':[1.0,0.0],
            '图表中的关键数字不能留空。 需要展示指标或图表时':[0.85,0.527],
            'Word 表格使用固定行距。 Word 文档表格排版时':[0.84,0.543],
        }
        req=request('17乘以23等于多少？')
        req['_semantic_embed_many']=lambda texts:[vectors[text] for text in texts]
        self.assertEqual(get_task_guidance(Repo([chart,word]),req)['included'],[])

    def test_semantic_backfill_honors_explicit_ppt_negation(self):
        ppt=unit('ppt','PPT 修改前建立结构化清单。','文档修订、PPT制作与附表修改')
        web=unit('web','修复网站后在真实页面逐项点击。','网页功能修复与验收')
        vectors={
            '网站按钮点击没反应，查原因并修好，别给我做PPT。':[1.0,0.0],
            'PPT 修改前建立结构化清单。 文档修订、PPT制作与附表修改':[0.99,0.01],
            '修复网站后在真实页面逐项点击。 网页功能修复与验收':[0.98,0.02],
        }
        req=request('网站按钮点击没反应，查原因并修好，别给我做PPT。')
        req['_semantic_embed_many']=lambda texts:[vectors[text] for text in texts]
        result=get_task_guidance(Repo([ppt,web]),req)
        self.assertNotIn('ppt',[row['id'] for row in result['included']])
        self.assertIn('web',[row['id'] for row in result['included']])

    def test_specialized_web_guidance_does_not_leak_into_ppt_delivery(self):
        web=unit('web','网页按钮修复后逐项点击。','网页与桌面界面验收')
        ppt=unit('ppt','PPT 交付前逐页检查排版。','PPT和视觉文档验收')
        result=get_task_guidance(Repo([web,ppt]),request('生成给客户看的PPT，交付前逐页检查排版和术语。'))
        self.assertEqual([row['id'] for row in result['included']],['ppt'])

    def test_procurement_visual_rule_requires_procurement_context(self):
        tender=unit('tender','招投标演示必须逐条截图。','招投标演示或验收')
        explain=unit('explain','困难知识使用直观例子解释。','知识解释','learning')
        result=get_task_guidance(Repo([tender,explain]),request('解释贝叶斯更新，用直观例子。'))
        self.assertNotIn('tender',[row['id'] for row in result['included']])

    def test_trivial_translation_and_number_sort_can_return_no_preference(self):
        rows=[unit('writing','正式对外说明使用自然中文。','正式文档写作'),unit('decision','建议按推荐度排序。','决策建议')]
        self.assertEqual(get_task_guidance(Repo(rows),request('把 hello 翻译成中文，只要两个字。'))['included'],[])
        self.assertEqual(get_task_guidance(Repo(rows),request('换个话题，把3、1、2从小到大排序。'))['included'],[])

    def test_near_duplicate_guidance_does_not_consume_multiple_packet_slots(self):
        rows=[
            unit('first','PPT视觉检查是否逐页以及检查轮数，按当次任务要求执行。','PPT视觉检查'),
            unit('second','PPT视觉检查的范围、是否逐页和轮数必须依据当前任务，不得默认增加。','PPT视觉检查'),
        ]
        for row in rows:row['evidence_refs']=[{'quote':'你不用每次都默认逐页检查，具体任务会另行说明。'}]
        result=get_task_guidance(Repo(rows),request('生成PPT并逐页检查排版。'))
        self.assertEqual(len(result['included']),1)

    def test_education_specific_ppt_rule_requires_education_context(self):
        higher_ed=unit('higher-ed','高校AI项目的PPT需要结合历史课程命名。','高校教学项目PPT交付')
        generic=unit('generic','PPT交付前逐页检查排版。','PPT视觉检查')
        result=get_task_guidance(Repo([higher_ed,generic]),request('生成给普通客户看的PPT，逐页检查排版。'))
        self.assertEqual([row['id'] for row in result['included']],['generic'])

    def test_observability_page_rule_requires_observability_context(self):
        timeline=unit('timeline','观察页时间线默认折叠并倒序显示。','记忆状态观察页')
        web=unit('web','网页按钮修复后做真实点击验收。','网页功能修复')
        result=get_task_guidance(Repo([timeline,web]),request('网站按钮没反应，查原因并修好。'))
        self.assertNotIn('timeline',[row['id'] for row in result['included']])

    def test_generic_verification_intent_does_not_activate_unrelated_high_risk_planning(self):
        planning=unit('planning','复杂或高风险任务开始前形成完整验证计划。','复杂或高风险任务')
        web=unit('web','网页修复后进行真实点击验收。','网页功能修复')
        result=get_task_guidance(Repo([planning,web]),request('修复这个网站按钮，并在完成后验收。'))
        self.assertEqual([row['id'] for row in result['included']],['web'])

    def test_named_product_and_diagram_rules_do_not_leak_into_generic_web_fix(self):
        named=unit('named','WorkBuddy连接页使用高密度图谱。','WorkBuddy或HiSite连接管理')
        diagram=unit('diagram','链路图和布局图不能遮挡。','复杂链路图视觉检查')
        web=unit('web','网页修复后进行真实点击验收。','网页功能修复')
        result=get_task_guidance(Repo([named,diagram,web]),request('修复这个网站按钮，并在完成后验收。'))
        self.assertEqual([row['id'] for row in result['included']],['web'])

    def test_plain_language_decision_question_selects_recommendation_guidance(self):
        decision=unit('decision','分析问题后按推荐度给出明确建议。','提供建议与决策支持')
        proactive=unit('proactive','完成一轮修改后主动寻找遗漏、冲突和更好的方案。','阶段性结果完成后')
        result=get_task_guidance(Repo([decision,proactive]),request('只给结论，一句话：方案A成本低但风险高，选不选？'))
        self.assertEqual([row['id'] for row in result['included']],['decision'])

    def test_diagnosis_only_request_excludes_visual_change_preferences(self):
        visual=unit('visual','网页按钮点击后必须提供动画反馈。','网页应用交互设计')
        diagnosis=unit('diagnosis','页面故障先核对进程、日志和触发时序。','软件故障诊断')
        query='先别动代码，只诊断这次页面闪一下后任务停止的原因。'
        vectors={query:[1.0,0.0], '网页按钮点击后必须提供动画反馈。 网页应用交互设计':[0.99,0.01], '页面故障先核对进程、日志和触发时序。 软件故障诊断':[0.98,0.02]}
        req=request(query);req['_semantic_embed_many']=lambda texts:[vectors[text] for text in texts]
        result=get_task_guidance(Repo([visual,diagnosis]),req)
        self.assertEqual([row['id'] for row in result['included']],['diagnosis'])

    def test_semantic_cache_reuses_same_revision_and_invalidates_changed_revision(self):
        from semantic_recall import SemanticVectorCache
        calls=[]
        with tempfile.TemporaryDirectory() as temporary:
            cache=SemanticVectorCache(Path(temporary)/'vectors.json',embed_many=lambda texts: calls.append(texts) or [[1.0,0.0] for _ in texts])
            first=unit('verify','修复后在真实页面逐项点击验证','网页功能验收')
            self.assertEqual(cache.document_vector(first),[1.0,0.0])
            self.assertEqual(cache.document_vector(first),[1.0,0.0])
            changed={**first,'revision':'v2'}
            cache.document_vector(changed)
        self.assertEqual(calls,[['修复后在真实页面逐项点击验证 网页功能验收'],['修复后在真实页面逐项点击验证 网页功能验收']])

    def test_semantic_cache_fills_all_missing_revisions_in_one_batch(self):
        from semantic_recall import SemanticVectorCache
        calls=[]
        with tempfile.TemporaryDirectory() as temporary:
            cache=SemanticVectorCache(Path(temporary)/'vectors.json',embed_many=lambda texts:calls.append(texts) or [[1.0,0.0] for _ in texts])
            vectors=cache.document_vectors([unit('first','页面逐项验证','网页验收'),unit('second','保留当前底稿','文件修改')])
        self.assertEqual(vectors,[[1.0,0.0],[1.0,0.0]])
        self.assertEqual(calls,[['页面逐项验证 网页验收','保留当前底稿 文件修改']])

    def test_semantic_candidates_recall_a_paraphrased_obligation(self):
        from semantic_recall import semantic_candidates
        rows=[
            unit('verify','修复后必须在真实页面逐项点击验证，不能只看接口返回。','网页功能验收'),
            unit('unrelated','Windows 版本应支持 U 盘便携部署。','Light Memory Windows 开发'),
        ]
        vectors={
            '把这次改动在浏览器里一个个操作确认': [1.0,0.0],
            '修复后必须在真实页面逐项点击验证，不能只看接口返回。 网页功能验收': [0.98,0.02],
            'Windows 版本应支持 U 盘便携部署。 Light Memory Windows 开发': [0.0,1.0],
        }
        result=semantic_candidates(rows,'把这次改动在浏览器里一个个操作确认',embed=lambda text:vectors[text])
        self.assertEqual([item['unit']['id'] for item in result],['verify'])
        self.assertEqual(result[0]['reason']['source'],'semantic')

    def test_semantic_candidates_keep_only_the_relative_head_not_all_positive_vectors(self):
        from semantic_recall import semantic_candidates
        rows=[unit('first','first','condition'),unit('second','second','condition'),unit('weak','weak','condition')]
        vectors={'query':[1.0,0.0],'first condition':[1.0,0.0],'second condition':[0.99,0.141],'weak condition':[0.94,0.341]}
        result=semantic_candidates(rows,'query',embed=lambda text:vectors[text])
        self.assertEqual([item['unit']['id'] for item in result],['first','second'])

    def test_semantic_match_cannot_override_explicit_project_condition(self):
        from semantic_recall import semantic_candidates
        target=unit('windows','交付时确保 Windows 版本支持 U 盘便携运行。','Light Memory 产品的 Windows 版本开发与部署')
        target['scope']={'project_ids':['light-memory']}
        vectors={
            '优化当前记忆系统的选择算法': [1.0,0.0],
            '交付时确保 Windows 版本支持 U 盘便携运行。 Light Memory 产品的 Windows 版本开发与部署': [0.99,0.01],
        }
        result=semantic_candidates([target],'优化当前记忆系统的选择算法',embed=lambda text:vectors[text],task={'project_ids':[]})
        self.assertEqual(result,[])

    def test_generic_reaudit_preserves_source_review_of_same_revision(self):
        from audit_active_preferences import audit_unit
        row=unit('verified','检查真实交互，而非只看后端接口','网页验收')
        row['preference_audit']['audit']={'state':'approved','review_kind':'source_checked_manual','reason':'verified user turns'}
        self.assertEqual(audit_unit(row)['state'],'approved')

    def test_negative_output_request_does_not_enable_ppt_formatting(self):
        u=unit('ppt','PPT制作使用逐页排版规则','PPT制作')
        self.assertEqual(get_task_guidance(Repo([u]),request('没让你做PPT，只说思路'))['included'],[])

    def test_requested_policy_background_is_not_overridden_by_old_slide_style(self):
        u=unit('old-style','汇报开篇直接展示效果，删除冗余的政策背景页。','方案文档制作')
        self.assertEqual(get_task_guidance(Repo([u]),request('撰写申报书的政策背景与必要性'))['included'],[])

    def test_pagination_never_repeats_an_item_or_loses_conditions(self):
        rows=[unit('u'+str(i),'修改文档保持一致'+str(i),'文件修改') for i in range(12)]
        repo=Repo(rows);req={**request('修改预算附表，保持各文件一致'),'max_candidates':6};seen=[]
        for _ in range(20):
            page=get_task_guidance(repo,req,char_budget=1900)
            seen += [u['id'] for u in page['included']]
            if not page['next_cursor']:break
            req={**req,'cursor':page['next_cursor']}
        self.assertEqual(len(seen),12)
        self.assertEqual(len(set(seen)),12)

    def test_budget_adjustment_receives_consistency_without_same_wording(self):
        rows=[unit('sync','正文与预算附表保持一致。','多文件联动修改')]
        result=get_task_guidance(Repo(rows),request('各期费用重新分配，申报材料的附件一起更新'))
        self.assertEqual([u['id'] for u in result['included']],['sync'])

    def test_keeps_conditions_without_copying_long_evidence_into_first_packet(self):
        rows=[unit('base','以用户修改稿为权威底稿，仅作必要修订。','用户修改文件后继续修订'),unit('sync','正文与预算附表保持一致。','多文件联动修改')]
        result=get_task_guidance(Repo(rows),request('基于我改好的文件调整预算，附表也一起改'))
        self.assertEqual({u['id'] for u in result['included']},{'base','sync'})
        self.assertEqual(result['included'][0]['exceptions'],['当前要求优先'])

    def test_compact_candidate_exposes_bounded_source_manifest(self):
        row=unit('priority','当前 Prompt 优先，记忆只作参考。','使用长期记忆')
        row['evidence_refs']=[{'memory_id':'m1','document_id':'d1','chunk_id':'c1','stored_role':'user','origin':'user_direct','quote':'PRIVATE ORIGINAL'}]
        result=get_task_guidance(Repo([row]),request('核对记忆与当前 Prompt 的优先关系'))
        self.assertEqual(result['included'][0]['evidence_manifest'][0]['memory_id'],'m1')
        self.assertNotIn('PRIVATE ORIGINAL',str(result['included'][0]))

    def test_chinese_explanation_does_not_require_english_word(self):
        row=unit('starter:explanation-and-unfamiliar-terms','难内容举例说明；陌生英文才提供全称音标。','知识解释与陌生术语学习','learning')
        self.assertIn(row['id'],[u['id'] for u in get_task_guidance(Repo([row]),request('这个因果机制我没明白，讲个例子'))['included']])

    def test_keeps_unsafe_lifecycle_and_forbidden_memory_out(self):
        rows=[unit('old','修改文档保持一致','文件修改',state='superseded'),unit('pending','修改文档保持一致','文件修改',state='needs_review')]
        self.assertEqual(get_task_guidance(Repo(rows),request('修改文档'))['included'],[])
        req=request('修改文档');req['memory_policy']='forbidden'
        self.assertEqual(get_task_guidance(Repo([unit('ok','修改文档保持一致','文件修改')]),req)['included'],[])

    def test_new_topic_does_not_activate_old_document_conditions(self):
        rows=[unit('doc','遵循文档模板格式','文档修改'),unit('explain','难懂的概念用例子解释','解释陌生概念','learning')]
        result=get_task_guidance(Repo(rows),request('换个话题，解释潮汐原理','修改申报书预算附表'))
        self.assertNotIn('doc',[u['id'] for u in result['included']])
