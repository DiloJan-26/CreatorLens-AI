"""Exercise the existing HTTP summary route with real normalization and decision engine."""
from copy import deepcopy
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from app.api.insights import router
from app.insights import insight_service
from app.services import semantic_service, llm_service

@pytest.fixture
def client(monkeypatch):
    items=[dict(id='video-1',project_id='p',slot='content_1',platform='youtube',views=34021,likes=485,comments=8,title='Habits one'),
           dict(id='video-2',project_id='p',slot='content_2',platform='youtube',views=1527222,likes=18876,comments=308,title='Habits two')]
    monkeypatch.setattr(insight_service,'get_project_detail_record',lambda project_id:dict(id='p',content_items=deepcopy(items)) if project_id=='p' else None)
    monkeypatch.setattr(insight_service,'get_transcript_segments',lambda **kwargs:[])
    monkeypatch.setattr(semantic_service,'get_semantic_analysis',lambda *args,**kwargs:dict(status='unavailable'))
    def forbidden(*args,**kwargs):raise AssertionError('Comparison GET must not invoke Gemini.')
    monkeypatch.setattr(semantic_service,'_invoke',forbidden)
    monkeypatch.setattr(semantic_service,'get_llm',forbidden)
    monkeypatch.setattr(llm_service,'get_llm',forbidden)
    app=FastAPI();app.include_router(router)
    with TestClient(app) as test_client:yield test_client

@pytest.mark.parametrize('objective,outcome',[('reach','content_2'),('engagement','content_1'),('creative_quality','insufficient_evidence'),('balanced','insufficient_evidence')])
def test_objective_query_uses_same_canonical_engine_and_preserves_legacy(client,objective,outcome):
    response=client.get('/api/projects/p/insights/summary',params={'objective':objective})
    assert response.status_code==200
    data=response.json();decision=data['goal_comparison']
    assert decision['selected_objective']==objective and decision['outcome']==outcome
    assert decision['decision_policy_version']=='goal-comparison-1.0.0'
    assert data['comparison']['policy_version']=='legacy-1.0.0'
    assert data['comparison']['confirmed_metric_winner']=='Content 2'
    assert data['content_1']['scores']['policy_version']=='legacy-1.0.0'
    assert data['content_1']['scoring']['policy']['version']=='creator-insight-2.0.0'
    assert set(decision['objective_decisions'])=={'reach','engagement','creative_quality','balanced'}
    assert decision['content_1']['content_id']=='video-1' and decision['content_2']['content_id']=='video-2'
    if outcome=='insufficient_evidence':assert decision['winner_content_id'] is None


def test_default_objective_is_balanced_and_unknown_objective_is_422(client):
    assert client.get('/api/projects/p/insights/summary').json()['goal_comparison']['selected_objective']=='balanced'
    assert client.get('/api/projects/p/insights/summary?objective=virality').status_code==422
    assert client.get('/api/projects/missing/insights/summary').status_code==404


def test_openapi_lists_exact_four_objectives(client):
    schema=client.get('/openapi.json').json()
    assert set(schema['components']['schemas']['ComparisonObjective']['enum'])=={'balanced','reach','engagement','creative_quality'}
