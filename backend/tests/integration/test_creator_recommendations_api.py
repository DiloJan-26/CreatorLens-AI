"""Real HTTP serialization and cached semantic input integration without inference."""
from copy import deepcopy
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from app.api.insights import router
from app.insights import insight_service
from app.services import semantic_service,llm_service
from tests.unit.test_creator_recommendations import semantic
from tests.unit.test_goal_comparison import PROJECT


@pytest.fixture
def client(monkeypatch):
    subjects=[semantic('content_1',{'verbal_hook_clarity':'absent'},views=34021,likes=485,comments=8),
        semantic('content_2',views=1527222,likes=18876,comments=308)]
    segments=[dict(segment_index=0,start_time=0.,end_time=4.,text='Why do students get distracted?'),
        dict(segment_index=1,start_time=4.,end_time=8.,text='Students can use a timed break to focus.'),
        dict(segment_index=2,start_time=8.,end_time=12.,text='The problem is distraction; try a break and subscribe.')]
    monkeypatch.setattr(insight_service,'get_project_detail_record',lambda project_id:
        dict(id=PROJECT,content_items=deepcopy([s[0] for s in subjects])) if project_id==PROJECT else None)
    monkeypatch.setattr(insight_service,'get_transcript_segments',lambda **kwargs:deepcopy(segments))
    monkeypatch.setattr(semantic_service,'get_semantic_analysis',lambda project_id,slot:
        deepcopy(next(s[1].semantic_analysis for s in subjects if s[0]['slot']==slot)))
    def forbidden(*args,**kwargs):raise AssertionError('Recommendation GET must not invoke inference.')
    monkeypatch.setattr(semantic_service,'_invoke',forbidden)
    monkeypatch.setattr(semantic_service,'get_llm',forbidden)
    monkeypatch.setattr(llm_service,'get_llm',forbidden)
    app=FastAPI();app.include_router(router)
    with TestClient(app) as client:yield client


@pytest.mark.parametrize('objective',['reach','engagement','creative_quality','balanced'])
def test_cached_summary_exposes_owned_recommendations_and_keeps_legacy(client,objective):
    response=client.get(f'/api/projects/{PROJECT}/insights/summary',params={'objective':objective})
    assert response.status_code==200
    data=response.json();bundle=data['creator_recommendations'];decision=data['goal_comparison']
    assert bundle['policy_version']=='creator-recommendations-1.0.0'
    assert bundle['selected_objective']==objective and bundle['decision_policy_version']==decision['decision_policy_version']
    assert bundle['status']=='ready'
    assert data['content_1']['content_id']=='video-content_1'
    assert data['content_1']['semantic_analysis']['status']=='ready'
    assert data['comparison']['policy_version']=='legacy-1.0.0'
    assert isinstance(data['comparison']['top_recommendations'],list)
    assert 'example_rewrite_for_content_2' in data['comparison']
    for r in bundle['recommendations']:
        target=data[r['target_slot']]
        assert target['content_id']==r['target_content_id'] and target['platform']==r['target_platform']
        assert r['comparison']['selected_outcome']==decision['outcome']
        assert any(e['role']=='target' and e['content_id']==r['target_content_id'] for e in r['evidence'])
    assert response.json()==client.get(f'/api/projects/{PROJECT}/insights/summary',params={'objective':objective}).json()


def test_default_bundle_remains_balanced_without_fallback(client):
    data=client.get(f'/api/projects/{PROJECT}/insights/summary').json()
    assert data['creator_recommendations']['selected_objective']=='balanced'
    assert data['creator_recommendations']['recommendations'][0]['target_slot']=='content_1'
    assert client.get(f'/api/projects/{PROJECT}/insights/summary?objective=unsupported').status_code==422
