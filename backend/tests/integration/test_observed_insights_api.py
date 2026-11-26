"""Current API contract; providers forbidden by the reused isolated route fixture."""
from tests.integration.test_goal_comparison_api import client


def test_current_response_has_independent_observed_decisions(client):
    response=client.get('/api/projects/p/insights/summary?objective=reach')
    assert response.status_code==200
    data=response.json();current=data['intelligence']
    assert current['policy_version']=='observed-intelligence-1.0.0'
    assert current['decisions']['reach']['winner_content_id']=='video-2'
    assert current['decisions']['like_rate']['winner_content_id']=='video-1'
    assert 'balanced' not in current['decisions']
    assert data['comparison']['policy_version']=='legacy-1.0.0'
    assert current==client.get('/api/projects/p/insights/summary?objective=reach').json()['intelligence']


def test_no_semantic_inputs_are_used_by_current_findings(client):
    data=client.get('/api/projects/p/insights/summary').json()['intelligence']
    assert all(not c['observations'] for c in data['contents'])
    assert data['recommendations']==[]
    assert all(c['values']['subscribers'] is None for c in data['contents'])
    assert data['decisions']['like_rate']['status']=='eligible'


def test_hook_message_unknowns_serialize_without_triggering_inference(client):
    data=client.get('/api/projects/p/insights/summary?objective=creative_quality').json()['intelligence']
    assert data['text_policy_version']=='hook-message-2.0.0'
    for content in data['contents']:
        analysis=content['hook_message']
        assert analysis['status']=='not_assessable'
        assert len(analysis['assessments'])==5
        assert all(f['status']=='not_assessable' and f['matched'] is None for f in analysis['assessments'])
        assert not any(f['action_eligible'] for f in analysis['assessments'])
    assert data['recommendations']==[]
