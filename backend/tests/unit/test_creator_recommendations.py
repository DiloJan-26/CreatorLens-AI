"""Offline source ownership, objective relevance and deterministic intervention regressions."""
from copy import deepcopy
import json
import pytest
from app.insights.semantic_models import CreativeFeatures
from app.insights.semantic_scoring import apply_semantic_scoring
from app.insights.recommendation_engine import (
    build_creator_recommendations, validate_recommendation, RecommendationSubject,
)
from app.insights.recommendation_models import CreatorRecommendationBundle
from app.insights.deterministic_scoring import normalize_metrics
from tests.unit.test_goal_comparison import PROJECT, make_subject, decide


def semantic(slot, labels=None, **changes):
    subject=make_subject(slot,semantic=True,**changes)
    analysis=subject[1].semantic_analysis
    for feature in analysis['features']['features']:
        value=(labels or {}).get(feature['feature'])
        if value is not None:
            feature['value']=value
            feature['status']='unassessable' if value=='unassessable' else 'assessed'
            if value=='unassessable':feature['evidence']=[]
    parsed=CreativeFeatures.model_validate(analysis['features'])
    subject[1].semantic_scoring=apply_semantic_scoring(subject[1].scoring,parsed,analysis['snapshot_id'])
    return subject


def run(a,b=None,objective='balanced'):
    b=b or semantic('content_2')
    decision=decide(a,b,objective)
    return build_creator_recommendations(PROJECT,decision,[a,b]),decision


def contexts(a,b,decision):
    return {item['id']:RecommendationSubject(item,insight,getattr(decision,item['slot']),normalize_metrics(item),True)
        for item,insight in (a,b)}


def test_weak_hook_is_source_bound_specific_and_explainable():
    a=semantic('content_1',{'verbal_hook_clarity':'absent'})
    result,decision=run(a)
    r=result.recommendations[0]
    assert result.status=='ready' and r.target_content_id==a[0]['id']
    assert r.target_slot=='content_1' and r.target_platform=='youtube'
    assert r.category=='opening_hook' and r.priority.score==8 and r.priority.label=='high'
    assert r.evidence and all(e.content_id==a[0]['id'] for e in r.evidence)
    assert 'Compare the current opening' in r.experiment
    assert 'not a probability' in r.priority.explanation
    assert r.comparison.selected_outcome==decision.outcome.value
    assert r.example and r.example.target_content_id==a[0]['id']
    assert 'Why do students get distracted?' in r.example.text
    assert 'A study of habits' not in r.example.text
    assert r.example.method=='deterministic_template'


def test_clear_features_do_not_generate_a_weakness_even_for_loser():
    a=semantic('content_1',views=1000,likes=10,comments=1)
    b=semantic('content_2',views=100000,likes=1000,comments=100)
    result,decision=run(a,b,'reach')
    assert decision.winner_slot=='content_2'
    assert result.status=='no_supported_actions' and result.recommendations==[]
    assert any(f.category=='reach_observation' for f in result.findings)


@pytest.mark.parametrize('state',['pending','failed','unavailable'])
def test_missing_pending_failed_semantics_are_not_weaknesses(state):
    a=make_subject('content_1');a[1].semantic_analysis={'status':state}
    result,_=run(a)
    assert not result.recommendations
    assert any(f.category=='semantic_evidence' and f.status=='not_assessable' for f in result.findings)


def test_music_only_unassessable_opening_is_not_weak():
    a=semantic('content_1',dict(opening_type='other',verbal_hook_clarity='unassessable',
        topic_specificity='unassessable',curiosity_gap='unassessable',audience_benefit='unassessable',
        audience_specificity='unassessable',problem_solution_clarity='unassessable',spoken_cta='unassessable'))
    result,_=run(a)
    assert not result.recommendations


@pytest.mark.parametrize('feature',['topic_specificity','audience_benefit','audience_specificity'])
def test_partial_messaging_has_a_testable_action(feature):
    result,_=run(semantic('content_1',{feature:'partial'}))
    assert len(result.recommendations)==1
    assert result.recommendations[0].signals[0].feature==feature
    assert result.recommendations[0].priority.label=='medium'


@pytest.mark.parametrize('opening,expected',[('problem',True),('story',False),('question',False)])
def test_problem_framing_is_not_forced_on_every_format(opening,expected):
    result,_=run(semantic('content_1',{'opening_type':opening,'problem_solution_clarity':'partial'}))
    assert bool(result.recommendations)==expected
    if expected:assert result.recommendations[0].category=='problem_solution'


@pytest.mark.parametrize('spoken,description,expected',[
    ('clear','clear',None),('clear','absent','description'),('absent','clear','transcript'),
])
def test_cta_source_types_and_optional_purpose_guard(spoken,description,expected):
    result,_=run(semantic('content_1',{'spoken_cta':spoken,'description_cta':description}))
    if expected:
        r=result.recommendations[0]
        assert r.category=='cta_strategy' and {e.source_type for e in r.evidence}=={expected}
        assert 'optional' in r.recommended_change
    else:assert not result.recommendations


def test_cta_no_purpose_context_is_only_information():
    result,_=run(semantic('content_1',{'opening_type':'story','spoken_cta':'absent'}))
    assert not result.recommendations
    assert any(f.category=='spoken_cta_context' for f in result.findings)


def test_partial_transcript_cannot_establish_absence():
    a=semantic('content_1',{'spoken_cta':'absent'})
    a[1].semantic_analysis['evidence_complete']=False
    result,_=run(a)
    assert not result.recommendations


def test_partial_supported_feature_can_survive_unavailable_composite():
    a=semantic('content_1',{'verbal_hook_clarity':'partial','topic_specificity':'unassessable',
        'curiosity_gap':'unassessable','audience_specificity':'unassessable','audience_benefit':'unassessable',
        'problem_solution_clarity':'unassessable','spoken_cta':'unassessable','description_cta':'unassessable','evidence_coverage':'partial'})
    a[1].semantic_analysis['evidence_complete']=False
    result,decision=run(a,objective='creative_quality')
    assert decision.outcome.value=='incomparable'  # Creative masks differ; individual evidence still applies.
    assert len(result.recommendations)==1 and result.recommendations[0].evidence_status=='partial'
    assert result.recommendations[0].priority.score==5


@pytest.mark.parametrize('damage',['id','cross_content','excerpt','timestamp','transcript_revision','snapshot','policy','platform'])
def test_invalid_or_stale_semantic_sources_are_withheld(damage):
    a=semantic('content_1',{'verbal_hook_clarity':'absent'})
    analysis=a[1].semantic_analysis
    ref=next(f for f in analysis['features']['features'] if f['feature']=='verbal_hook_clarity')['evidence'][0]
    if damage=='id':ref['evidence_id']='invented'
    elif damage=='cross_content':ref['content_id']='video-content_2'
    elif damage=='excerpt':ref['excerpt']='invented spoken quote'
    elif damage=='timestamp':ref['end_time']=100.
    elif damage=='transcript_revision':a[0]['transcript_evidence']['revision']='corrected'
    elif damage=='snapshot':analysis['snapshot_id']='other-snapshot'
    elif damage=='policy':analysis['creative_policy']='unsupported'
    else:analysis['evidence_sources'][0]['platform']='facebook'
    result,_=run(a)
    assert not result.recommendations


@pytest.mark.parametrize('objective',['reach','engagement','creative_quality','balanced'])
def test_all_objectives_preserve_identity_and_canonical_decisions(objective):
    a=semantic('content_1',{'verbal_hook_clarity':'partial'})
    b=semantic('content_2')
    original=decide(a,b,objective).model_dump(mode='json')
    result,decision=run(a,b,objective)
    assert decision.model_dump(mode='json')==original
    assert result.selected_objective.value==objective
    assert len(result.recommendations)==1
    r=result.recommendations[0]
    assert r.target_content_id==a[0]['id']
    assert r.comparison.selected_outcome==decision.outcome.value


def test_tie_does_not_default_to_content_two_and_winner_can_have_weakness():
    a=semantic('content_1',{'verbal_hook_clarity':'partial'})
    b=semantic('content_2',{'verbal_hook_clarity':'partial'})
    result,decision=run(a,b,'reach')
    assert decision.outcome.value=='tie'
    assert {r.target_slot for r in result.recommendations}=={'content_1','content_2'}
    a[0]['views']=20000
    a=semantic('content_1',{'verbal_hook_clarity':'partial'},views=20000)
    result,decision=run(a,b,'reach')
    assert decision.winner_slot=='content_1' and any(r.target_slot=='content_1' for r in result.recommendations)


def test_cross_platform_does_not_produce_metric_action_or_legacy_fallback():
    a=make_subject('content_1')
    b=make_subject('content_2',platform='facebook',reactions=100,shares=20)
    result,decision=run(a,b,'engagement')
    assert decision.outcome.value=='incomparable' and not result.recommendations
    assert any(f.category=='engagement_observation' and f.status=='incomparable' for f in result.findings)


def test_dopamine_reach_and_engagement_targets_use_owned_evidence():
    a=semantic('content_1',{'verbal_hook_clarity':'partial'},views=34021,likes=485,comments=8,title='First dopamine explanation')
    b=semantic('content_2',views=1527222,likes=18876,comments=308,title='Second dopamine explanation')
    result,decision=run(a,b,'reach')
    assert decision.winner_slot=='content_2' and result.recommendations[0].target_content_id==a[0]['id']
    assert 'Second dopamine explanation' not in result.recommendations[0].model_dump_json()
    result,decision=run(a,b,'engagement')
    metric=next(r for r in result.recommendations if r.category=='engagement_opportunity')
    assert decision.winner_slot=='content_1' and metric.target_content_id==b[0]['id']
    assert metric.priority.score==5 and metric.basis=='comparative_opportunity'
    assert {(e.content_id,e.role) for e in metric.evidence}=={(b[0]['id'],'target'),(a[0]['id'],'comparison_context')}
    assert all(e.excerpt is None and e.start_time is None for e in metric.evidence)


@pytest.mark.parametrize('views,likes,comments',[(4,4,0),(999,10,0),(10000,None,20),(10000,100,None)])
def test_small_or_missing_engagement_is_information_without_action(views,likes,comments):
    result,_=run(make_subject('content_1',views=views,likes=likes,comments=comments),
        make_subject('content_2',views=1000000,likes=4000,comments=0),'engagement')
    assert not result.recommendations


def test_missing_creator_size_does_not_create_efficiency_improvement():
    result,_=run(semantic('content_1',subscriber_count=None))
    assert not result.recommendations
    assert any(f.category=='efficiency_observation' and f.status=='not_assessable' for f in result.findings)


def test_overlapping_opening_rules_merge_without_extra_priority():
    result,_=run(semantic('content_1',dict(verbal_hook_clarity='absent',topic_specificity='partial',audience_benefit='partial',audience_specificity='partial')))
    assert result.detected_candidates==4 and result.merged_candidates==3
    assert len(result.recommendations)==1
    r=result.recommendations[0]
    assert len(r.signals)==4 and r.priority.score==8
    assert len({e.model_dump_json() for e in r.evidence})==len(r.evidence)


def test_stable_limits_priority_and_determinism():
    labels=dict(opening_type='problem',verbal_hook_clarity='absent',problem_solution_clarity='partial',spoken_cta='absent')
    a,b=semantic('content_1',labels),semantic('content_2',labels)
    result,decision=run(a,b)
    assert len(result.recommendations)==5 and result.omitted_by_display_limit==1
    assert [r.priority.score for r in result.recommendations]==sorted([r.priority.score for r in result.recommendations],reverse=True)
    assert all(sum(r.target_content_id==item[0]['id'] for r in result.recommendations)<=3 for item in (a,b))
    again=build_creator_recommendations(PROJECT,decision,[b,a])
    assert result.model_dump(mode='json')==again.model_dump(mode='json')
    assert CreatorRecommendationBundle.model_validate_json(result.model_dump_json())==result


@pytest.mark.parametrize('damage',['target','slot','project','evidence_id','source_owner','role','revision','quote','causal','example_target','comparison'])
def test_final_validation_rejects_identity_leakage_fabrication_and_claims(damage):
    a,b=semantic('content_1',{'verbal_hook_clarity':'absent'}),semantic('content_2')
    result,decision=run(a,b)
    r=result.recommendations[0].model_copy(deep=True)
    if damage=='target':r.target_content_id=b[0]['id']
    elif damage=='slot':r.target_slot='content_2'
    elif damage=='project':r.project_id='other'
    elif damage=='evidence_id':r.evidence[0].evidence_id='invented'
    elif damage=='source_owner':r.evidence[0].content_id=b[0]['id']
    elif damage=='role':r.evidence[0].role='comparison_context'
    elif damage=='revision':r.evidence[0].input_revision='old'
    elif damage=='quote':r.evidence[0].excerpt='invented'
    elif damage=='causal':r.recommended_change='This opening caused viewer drop-off and will increase views.'
    elif damage=='example_target':r.example.target_content_id=b[0]['id']
    else:r.comparison.selected_outcome='invented_outcome'
    with pytest.raises(ValueError):validate_recommendation(r,contexts(a,b,decision),decision)


def test_metric_evidence_cannot_be_edited_into_another_value():
    a,b=make_subject('content_1',likes=10),make_subject('content_2',likes=300)
    result,decision=run(a,b,'engagement')
    r=result.recommendations[0].model_copy(deep=True)
    r.evidence[0].metric_values['views']=999999
    with pytest.raises(ValueError):validate_recommendation(r,contexts(a,b,decision),decision)


def test_input_revision_change_after_decision_is_fail_closed():
    a,b=semantic('content_1',{'verbal_hook_clarity':'absent'}),semantic('content_2')
    decision=decide(a,b)
    a[0]['views']=33333
    result=build_creator_recommendations(PROJECT,decision,[a,b])
    assert not result.recommendations
    assert any('omitted' in note for note in result.limitations)


def test_null_example_and_legacy_independence_serialization():
    a=semantic('content_1',{'topic_specificity':'partial'})
    before=deepcopy(a[1].scoring.model_dump(mode='json'))
    result,_=run(a)
    data=json.loads(result.model_dump_json())
    assert data['recommendations'][0]['example'] is None
    assert data['policy_version']=='creator-recommendations-1.0.0'
    assert a[1].scoring.model_dump(mode='json')==before


@pytest.mark.parametrize('status',['invalid','unavailable','not_assessable'])
def test_invalid_current_transcript_state_is_not_trusted(status):
    a=semantic('content_1',{'verbal_hook_clarity':'absent'})
    a[0]['transcript_evidence']['status']=status
    result,_=run(a)
    assert not result.recommendations


def test_translated_evidence_is_not_silently_original_language():
    a=semantic('content_1',{'verbal_hook_clarity':'absent'})
    a[0]['transcript_evidence']['provenance']['caption_kind']='translated'
    result,_=run(a)
    assert not result.recommendations


def test_semantic_snapshot_changed_after_decision_is_not_used():
    a,b=semantic('content_1',{'verbal_hook_clarity':'absent'}),semantic('content_2')
    decision=decide(a,b)
    a[1].semantic_analysis['snapshot_id']='corrected-snapshot'
    a[1].semantic_scoring.semantic_snapshot_id='corrected-snapshot'
    result=build_creator_recommendations(PROJECT,decision,[a,b])
    assert not result.recommendations
    assert any('changed after' in f.observation for f in result.findings)


def test_one_content_missing_still_allows_owned_individual_advice():
    a=semantic('content_1',{'verbal_hook_clarity':'partial'})
    from app.insights.comparison_engine import build_goal_comparison
    decision=build_goal_comparison(PROJECT,a[0],None,a[1],None,'balanced')
    result=build_creator_recommendations(PROJECT,decision,[a,(None,None)])
    assert len(result.recommendations)==1 and result.recommendations[0].target_content_id==a[0]['id']
    assert result.recommendations[0].comparison.selected_outcome=='insufficient_evidence'
