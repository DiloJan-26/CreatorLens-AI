"""Objective policy regressions using real normalization and synthetic validated semantic sources."""
from copy import deepcopy
import json
from types import SimpleNamespace
import pytest
from app.insights.comparison_engine import build_goal_comparison
from app.insights.comparison_models import ComparisonDecision, ComparisonObjective
from app.insights.deterministic_scoring import calculate_scoring
from app.insights.semantic_evidence import build_semantic_input, parse_features
from app.insights.semantic_models import FEATURES
from app.insights.semantic_scoring import apply_semantic_scoring

PROJECT='comparison-fixture'
CREATIVE=dict(hook_clarity=5,problem_solution_clarity=5,caption_strength=5,cta_strength=5,audience_specificity=5)

def make_subject(slot, *, semantic=False, **changes):
    item=dict(id='video-'+slot,project_id=PROJECT,slot=slot,platform='youtube',views=10000,likes=100,comments=20,
        subscriber_count=1000,duration_seconds=12,title='A study of habits',description='Subscribe for more.',
        upload_date='2026-01-01',captured_at='2026-02-01T00:00:00Z',transcript_source='captions',
        transcript_evidence={'status':'valid','revision':'rev-'+slot,'provenance':{'original_audio_language':'en','transcript_language':'en','caption_track_language':'en','caption_kind':'original'}})
    item.update(changes)
    base=calculate_scoring(item,CREATIVE,hook_assessable=True)
    insight=SimpleNamespace(slot=slot,platform=item['platform'],scoring=base,semantic_analysis={'status':'unavailable'},semantic_scoring=None)
    if semantic:
        segments=[dict(segment_index=0,start_time=0.,end_time=4.,text='Why do students get distracted?'),
            dict(segment_index=1,start_time=4.,end_time=8.,text='Students can use a timed break to focus.'),
            dict(segment_index=2,start_time=8.,end_time=12.,text='The problem is distraction; try a break and subscribe.')]
        ctx=build_semantic_input(PROJECT,item,segments)
        features=[]
        for name in FEATURES:
            kind='opening' if name in {'opening_type','verbal_hook_clarity','topic_specificity','curiosity_gap'} else 'description' if name=='description_cta' else 'transcript'
            source=next(s for s in ctx['sources'] if s['source_type']==kind)
            features.append(dict(feature=name,value='question' if name=='opening_type' else 'clear',status='assessed',
                evidence=[dict(evidence_id=source['id'],content_id=item['id'],slot=slot,excerpt=source['text'],start_time=source['start_time'],end_time=source['end_time'])]))
        payload=dict(schema_version='creative-features-1.0.0',project_id=PROJECT,content_id=item['id'],slot=slot,input_revision=ctx['input_revision'],features=features)
        parsed=parse_features(json.dumps(payload),ctx)
        snapshot='snapshot-'+slot
        insight.semantic_analysis=dict(status='ready',snapshot_id=snapshot,input_revision=ctx['input_revision'],features=parsed.model_dump(mode='json'),
            evidence_sources=ctx['sources'],evidence_complete=ctx['complete'],creative_policy='semantic-creative-1.0.0',schema_version='creative-features-1.0.0',prompt_version='1.0.0',model_id='mock-configured-model')
        insight.semantic_scoring=apply_semantic_scoring(base,parsed,snapshot)
    return item,insight


def decide(left,right,objective='balanced'):
    return build_goal_comparison(PROJECT,left[0],right[0],left[1],right[1],objective)


def test_dopamine_objectives_keep_reach_and_engagement_distinct():
    a=make_subject('content_1',views=34021,likes=485,comments=8,subscriber_count=None)
    b=make_subject('content_2',views=1527222,likes=18876,comments=308,subscriber_count=None)
    reach=decide(a,b,'reach');engagement=decide(a,b,'engagement')
    assert reach.outcome=='content_2' and reach.winner_content_id==b[0]['id']
    assert engagement.outcome=='content_1'
    assert engagement.difference_content_1_minus_content_2==pytest.approx(493/34021*100-19184/1527222*100)
    assert engagement.difference_units=='percentage_points'
    assert reach.objective_decisions['balanced'].outcome=='insufficient_evidence'
    assert reach.objective_decisions['creative_quality'].outcome=='insufficient_evidence'
    assert len(reach.dimension_leaders)==6

@pytest.mark.parametrize('views,expected',[(0,'content_2'),(10000,'tie'),(10001,'content_1'),(None,'insufficient_evidence'),(-1,'insufficient_evidence'),(True,'insufficient_evidence')])
def test_reach_zero_equal_missing_invalid(views,expected):
    result=decide(make_subject('content_1',views=views),make_subject('content_2'),'reach')
    assert result.outcome==expected
    if expected in {'tie','insufficient_evidence'}:assert result.winner_slot is None


def test_publication_observation_context_is_preserved_without_velocity_claim():
    a=make_subject('content_1',views=100000,upload_date='2025-01-01')
    b=make_subject('content_2',upload_date='2026-01-01',captured_at=None)
    result=decide(a,b,'reach')
    assert result.outcome=='content_1'
    assert result.content_1.publication_date=='2025-01-01'
    assert any('Publication dates' in x for x in result.limitations)
    assert 'not unique viewers or growth velocity' in result.explanation

@pytest.mark.parametrize('views,likes,comments',[(4,4,0),(999,20,0),(1000,None,1),(1000,1,None),(1000,2000,0),(0,0,0)])
def test_engagement_missing_or_insufficient_is_not_a_winner(views,likes,comments):
    a=make_subject('content_1',views=views,likes=likes,comments=comments)
    b=make_subject('content_2',views=1000000,likes=4000,comments=0)
    result=decide(a,b,'engagement')
    assert result.outcome=='insufficient_evidence'
    assert result.winner_slot is None
    assert result.dimension_leaders['engagement'].descriptive_leader_slot is None
    assert result.dimension_leaders['observed_reach'].outcome=='content_2'

@pytest.mark.parametrize('likes,expected',[(109,'tie'),(110,'tie'),(111,'content_2')])
def test_engagement_tolerance_uses_exact_rate_difference(likes,expected):
    a=make_subject('content_1',views=10000,likes=100,comments=0)
    b=make_subject('content_2',views=10000,likes=likes,comments=0)
    result=decide(a,b,'engagement')
    assert result.outcome==expected
    assert result.dimension_leaders['engagement'].tie_tolerance==.1
    assert result.raw_objective_values['content_2']==pytest.approx(likes/100)

@pytest.mark.parametrize('platform',['instagram','facebook'])
def test_cross_platform_counts_are_descriptive_and_not_objective_winners(platform):
    a=make_subject('content_1',views=100000)
    b=make_subject('content_2',platform=platform,follower_count=1000,reactions=100,shares=10)
    result=decide(a,b,'reach')
    assert result.outcome=='incomparable' and result.winner_slot is None
    assert result.dimension_leaders['observed_reach'].descriptive_leader_slot=='content_1'
    assert result.objective_decisions['engagement'].outcome=='incomparable'


def test_facebook_partial_share_field_blocks_combined_engagement_only():
    a=make_subject('content_1',platform='facebook',follower_count=1000,reactions=100,shares=None)
    b=make_subject('content_2',platform='facebook',follower_count=1000,reactions=100,shares=10)
    result=decide(a,b,'engagement')
    assert result.outcome=='insufficient_evidence'
    assert result.objective_decisions['reach'].outcome=='tie'

@pytest.mark.parametrize('size',[None,0])
def test_efficiency_missing_denominator_is_not_zero_or_tie(size):
    a=make_subject('content_1',subscriber_count=size)
    b=make_subject('content_2')
    result=decide(a,b,'reach').dimension_leaders['creator_efficiency']
    assert result.outcome=='insufficient_evidence' and result.values['content_1'] is None


def test_efficiency_and_public_performance_independent_leaders():
    a=make_subject('content_1',views=10000,subscriber_count=100)
    b=make_subject('content_2',views=1000000,likes=10000,comments=2000,subscriber_count=1000000)
    result=decide(a,b,'reach')
    assert result.dimension_leaders['creator_efficiency'].outcome=='content_1'
    assert result.dimension_leaders['public_performance'].outcome=='content_2'

@pytest.mark.parametrize('state',['pending','failed','unavailable'])
def test_semantic_state_does_not_block_metrics_or_become_zero(state):
    a=make_subject('content_1');a[1].semantic_analysis={'status':state}
    b=make_subject('content_2',semantic=True)
    result=decide(a,b,'creative_quality')
    assert result.outcome=='insufficient_evidence' and result.raw_objective_values['content_1'] is None
    assert result.objective_decisions['reach'].outcome=='tie'
    assert result.objective_decisions['engagement'].outcome=='tie'

@pytest.mark.parametrize('difference,expected',[(0,'tie'),(.499,'tie'),(.5,'tie'),(.501,'content_1')])
def test_creative_score_tolerance_boundary_on_supplied_versioned_scores(difference,expected):
    a,b=make_subject('content_1',semantic=True),make_subject('content_2',semantic=True)
    a[1].semantic_scoring.creative_structure.score=8+difference
    b[1].semantic_scoring.creative_structure.score=8
    result=decide(a,b,'creative_quality')
    assert result.outcome==expected
    assert result.dimension_leaders['creative_quality'].evidence_references['content_1']
    assert result.creative_policy_version=='semantic-creative-1.0.0'


def test_creative_quality_does_not_require_engagement_or_same_platform():
    a=make_subject('content_1',semantic=True,views=None,likes=None,comments=None)
    b=make_subject('content_2',semantic=True,platform='instagram',views=None,likes=None,comments=None,follower_count=None)
    result=decide(a,b,'creative_quality')
    assert result.outcome=='tie'
    assert result.objective_decisions['balanced'].outcome in {'insufficient_evidence','incomparable'}

@pytest.mark.parametrize('change',['transcript','input','snapshot','owner','evidence','excerpt','timestamp'])
def test_stale_or_wrong_semantic_identity_is_rejected(change):
    a,b=make_subject('content_1',semantic=True),make_subject('content_2',semantic=True)
    analysis=a[1].semantic_analysis
    if change=='transcript':a[0]['transcript_evidence']['revision']='new'
    elif change=='input':analysis['input_revision']='new'
    elif change=='snapshot':analysis['snapshot_id']='new'
    elif change=='owner':analysis['features']['content_id']='other-video'
    elif change=='evidence':analysis['evidence_sources'][0]['slot']='content_2'
    elif change=='excerpt':analysis['features']['features'][0]['evidence'][0]['excerpt']='fabricated'
    else:analysis['features']['features'][0]['evidence'][0]['end_time']=2.
    result=decide(a,b,'creative_quality')
    assert result.outcome=='insufficient_evidence'
    assert result.winner_slot is None

@pytest.mark.parametrize('change',['creative','metric','model','prompt','schema'])
def test_policy_and_model_version_mismatches_are_incomparable(change):
    a,b=make_subject('content_1',semantic=True),make_subject('content_2',semantic=True)
    if change=='creative':b[1].semantic_scoring.creative_policy_version='unsupported'
    elif change=='metric':b[1].semantic_scoring.metric_policy_version='unsupported'
    elif change=='model':b[1].semantic_analysis['model_id']='other-model'
    elif change=='prompt':b[1].semantic_analysis['prompt_version']='2.0.0'
    else:b[1].semantic_analysis['schema_version']='unsupported'
    result=decide(a,b,'creative_quality')
    assert result.outcome=='incomparable'

@pytest.mark.parametrize('creator_sizes',[(1000,1000),(None,None),(None,1000)])
def test_balanced_equal_and_different_component_coverage(creator_sizes):
    a=make_subject('content_1',semantic=True,subscriber_count=creator_sizes[0])
    b=make_subject('content_2',semantic=True,subscriber_count=creator_sizes[1])
    result=decide(a,b)
    assert result.outcome==('tie' if creator_sizes[0]==creator_sizes[1] else 'incomparable')
    assert result.raw_objective_values['content_1']==a[1].semantic_scoring.overall.score
    if result.eligibility.status=='eligible':
        assert result.key_contributions['content_1']==[x.model_dump(mode='json') for x in a[1].semantic_scoring.overall.components]


def test_creative_feature_mask_mismatch_is_not_compared_as_equal_quality():
    a,b=make_subject('content_1',semantic=True),make_subject('content_2',semantic=True)
    part=b[1].semantic_scoring.creative_structure.components[-1]
    part.score=None;part.weight=0;part.contribution=None
    result=decide(a,b,'creative_quality')
    assert result.outcome=='incomparable'

@pytest.mark.parametrize('change',['same_id','foreign_project','wrong_slot','insight_platform','blank_id','missing','same_url'])
def test_valid_distinct_project_owned_content_is_required(change):
    a,b=make_subject('content_1'),make_subject('content_2')
    if change=='same_id':b[0]['id']=a[0]['id']
    elif change=='foreign_project':b[0]['project_id']='another-project'
    elif change=='wrong_slot':b[0]['slot']='content_1'
    elif change=='insight_platform':b[1].platform='facebook'
    elif change=='blank_id':b[0]['id']=' '
    elif change=='same_url':a[0]['url']=b[0]['url']='same-public-url'
    else:b=(None,None)
    result=decide(a,b,'reach')
    assert result.outcome in {'insufficient_evidence','incomparable'}
    assert result.winner_content_id is None


def test_parent_membership_is_explicit_for_legacy_records_without_project_id():
    a,b=make_subject('content_1'),make_subject('content_2')
    a[0].pop('project_id');b[0].pop('project_id')
    result=decide(a,b,'reach')
    assert result.outcome=='tie'
    assert result.content_1.ownership_source=='summary_project_membership'


def test_reproducible_json_nulls_and_no_confidence_probability():
    a,b=make_subject('content_1'),make_subject('content_2')
    first=decide(a,b)
    assert first==decide(a,b)
    assert ComparisonDecision.model_validate_json(first.model_dump_json())==first
    assert first.winner_content_id is None
    assert 'confidence' not in first.model_dump_json()
    assert first.content_1.metric_input_revision
    assert len(list(ComparisonObjective))==4
    with pytest.raises(ValueError):decide(a,b,'virality')

@pytest.mark.parametrize('views,expected',[(999,'insufficient_evidence'),(1000,'tie'),(1001,'tie')])
def test_engagement_sample_floor_boundary(views,expected):
    result=decide(make_subject('content_1',views=views,likes=0,comments=0),make_subject('content_2',views=1000,likes=0,comments=0),'engagement')
    assert result.outcome==expected

@pytest.mark.parametrize('dimension,field,objective',[
    ('creator_efficiency','creator_efficiency','reach'),('public_performance','public_performance','reach'),
    ('balanced','overall','balanced')])
@pytest.mark.parametrize('delta,expected',[(.499,'tie'),(.5,'tie'),(.501,'content_1')])
def test_shared_score_thresholds(dimension,field,objective,delta,expected):
    a,b=make_subject('content_1',semantic=True),make_subject('content_2',semantic=True)
    for subject,value in ((a,8+delta),(b,8)):
        scores=subject[1].semantic_scoring if dimension=='balanced' else subject[1].scoring
        getattr(scores,field).score=value
    assert decide(a,b,objective).dimension_leaders[dimension].outcome==expected


def test_metric_source_identity_and_input_revisions_are_separate_per_slot():
    a,b=make_subject('content_1'),make_subject('content_2')
    result=decide(a,b,'reach')
    assert result.content_1.metric_provenance['content_item_id']==a[0]['id']
    assert result.content_2.metric_provenance['content_item_id']==b[0]['id']
    assert result.content_1.metric_input_revision!=result.content_2.metric_input_revision


def test_semantic_feature_differences_include_actual_source_ids():
    a,b=make_subject('content_1',semantic=True),make_subject('content_2',semantic=True)
    # A valid alternate label yields an actual recomputed semantic breakdown.
    payload=b[1].semantic_analysis['features']
    next(f for f in payload['features'] if f['feature']=='verbal_hook_clarity')['value']='partial'
    from app.insights.semantic_models import CreativeFeatures
    b[1].semantic_scoring=apply_semantic_scoring(b[1].scoring,CreativeFeatures.model_validate(payload),b[1].semantic_analysis['snapshot_id'])
    result=decide(a,b,'creative_quality')
    assert result.outcome=='content_1'
    assert any(f['feature']=='verbal_hook_clarity' for f in result.dimension_leaders['creative_quality'].feature_differences)
    assert result.dimension_leaders['creative_quality'].evidence_references['content_2'][0]['evidence_id']

@pytest.mark.parametrize('change',['missing_policy','coverage','required_component','overall_weight'])
def test_incomplete_semantic_eligibility_metadata_is_rejected(change):
    a,b=make_subject('content_1',semantic=True),make_subject('content_2',semantic=True)
    if change=='missing_policy':a[1].semantic_analysis.pop('model_id')
    elif change=='coverage':a[1].semantic_scoring.creative_structure.coverage=.5
    elif change=='required_component':a[1].semantic_scoring.creative_structure.components[0].weight=0
    else:a[1].semantic_scoring.policy.overall_weights['public_performance']=.8
    result=decide(a,b)
    assert result.outcome in {'insufficient_evidence','incomparable'}
    assert result.winner_slot is None


def test_explicit_blank_project_identity_is_not_parent_membership():
    a,b=make_subject('content_1'),make_subject('content_2')
    b[0]['project_id']=''
    assert decide(a,b,'reach').outcome=='incomparable'
