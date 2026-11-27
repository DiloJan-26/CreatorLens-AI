"""Versioned multi-platform policy regressions; all metadata and captions are synthetic."""
from itertools import product
import pytest
from app.insights.observed_intelligence import build_observed_intelligence, POLICY
from app.extraction import bounded_provider, policy
from app.services.url_normalization_service import normalize_content_url
from tests.unit.test_observed_intelligence import item, evidence
from tests.unit.test_bounded_extraction import settings

PLATFORMS=("youtube","instagram","facebook")
URLS={"youtube":"https://www.youtube.com/watch?v=fixture","instagram":"https://www.instagram.com/reel/fixture/","facebook":"https://www.facebook.com/reel/12345/"}

@pytest.mark.parametrize("left,right",list(product(PLATFORMS,repeat=2)))
def test_all_platform_pairs_compare_independent_reported_metrics(left,right):
    a=item(platform=left,views=2000,likes=40,comments=None,subscriber_count=100,follower_count=50)
    b=item("content_2",platform=right,views=4000,likes=40,comments=10,subscriber_count=100,follower_count=50)
    value=build_observed_intelligence("p",[a,b],{})
    assert value.policy_version=="observed-intelligence-1.1.0"
    assert value.decisions["reach"]["winner_content_id"]=="content_2"
    assert value.decisions["like_rate"]["winner_content_id"]=="content_1"
    assert value.decisions["comment_rate"]["status"]=="insufficient_evidence"
    assert value.decisions["reach"]["comparison_scope"]==("same_platform" if left==right else "cross_platform_descriptive")
    assert value.contents[0]["values"]["audience_efficiency"]==(20 if left=="youtube" else 40)
    assert value.contents[0]["values"]["followers"]==50
    assert value.model_dump_json()==build_observed_intelligence("p",[a,b],{}).model_dump_json()
    assert not value.recommendations  # Losing on reach does not establish a creative defect.


def test_facebook_reactions_never_become_likes_or_positive_sentiment():
    value=build_observed_intelligence("p",[item(platform="facebook",likes=None,reactions=200),item("content_2")],{})
    assert value.contents[0]["values"]["likes"] is None
    assert value.contents[0]["values"]["reactions"]==200
    assert value.decisions["like_rate"]["status"]=="insufficient_evidence"
    assert value.decisions["reach"]["status"]=="eligible"


@pytest.mark.parametrize("url",["https://facebook.com/reel/12345/","https://m.facebook.com/watch/?v=12345","https://www.facebook.com/creator/videos/a-title/12345/?tracking=1"])
def test_facebook_video_variants_share_canonical_identity(url):
    assert normalize_content_url(url)=="https://www.facebook.com/watch/?v=12345"
    assert policy.input_url(url,"facebook",settings())==normalize_content_url(url)


@pytest.mark.parametrize("url,platform",[("https://facebook.com/share/r/opaque/","facebook"),("https://fb.watch/opaque/","facebook"),("https://facebook.com/creator/posts/123/","facebook"),("https://instagram.com/creator/","instagram"),("https://instagram.com.evil.test/reel/abc/","instagram"),("https://user:secret@facebook.com/reel/123/","facebook"),(URLS["instagram"],"facebook")])
def test_unknown_identity_and_unsafe_urls_are_rejected(url,platform):
    with pytest.raises(policy.ExtractionSafetyError):policy.input_url(url,platform,settings())


@pytest.mark.parametrize("platform",PLATFORMS)
def test_emergency_stop_applies_to_every_platform(monkeypatch,platform):
    from fastapi import HTTPException
    monkeypatch.setattr(bounded_provider,"get_settings",lambda:settings(provider_emergency_stop=True))
    monkeypatch.setattr(bounded_provider,"request",lambda *a:pytest.fail("Emergency stop permitted provider execution"))
    with pytest.raises(HTTPException):bounded_provider.extract("p","content_1",platform,URLS[platform])


@pytest.mark.parametrize("platform",PLATFORMS)
def test_provider_mapping_keeps_platform_counts_native_evidence_and_enrichment_separate(monkeypatch,platform):
    calls=[]
    monkeypatch.setattr(bounded_provider,"get_settings",lambda:settings())
    def request(project,slot,url,source,operation):
        calls.append((source,operation))
        if operation=="native_transcript":return None
        return dict(platform=platform,type="video",url=url,title="Focus",description="Focus on one task.",media={"duration":30},stats={"views":2000,"likes":40,"comments":0,"reactions":70},additionalData={"followerCount":500,"subscriberCount":600})
    monkeypatch.setattr(bounded_provider,"request",request)
    from app.extraction import youtube_enrichment
    monkeypatch.setattr(youtube_enrichment,"enrich",lambda *a:pytest.fail("Non-YouTube content reached YouTube enrichment") if platform!="youtube" else (a[2],{}))
    result=bounded_provider.extract("p","content_1",platform,URLS[platform])
    assert result.metadata.platform==platform and result.metadata.likes==40 and result.metadata.reactions==70
    assert result.metadata.comments==0 and not result.transcript_segments and not result.metadata.transcript_available
    assert result.metadata.follower_count==(500 if platform!="youtube" else None)
    assert result.metadata.subscriber_count==(600 if platform=="youtube" else None)
    assert calls==[(platform,"metadata"),(platform,"native_transcript")]


def test_unapproved_provider_metadata_identity_and_images_are_not_video_evidence(monkeypatch):
    monkeypatch.setattr(bounded_provider,"get_settings",lambda:settings())
    for payload in (dict(platform="youtube",type="video",url=URLS["youtube"]),dict(platform="instagram",type="image",url=URLS["instagram"])):
        monkeypatch.setattr(bounded_provider,"request",lambda *a:payload)
        with pytest.raises(policy.ExtractionSafetyError):bounded_provider.extract("p","content_1","instagram",URLS["instagram"])


def test_historical_bounded_youtube_cache_retained_but_not_unapproved_social_cache():
    from app.models.video import VideoMetadata, VideoExtractionResult
    for platform in PLATFORMS:
        cached=VideoExtractionResult(metadata=VideoMetadata(platform=platform,url=URLS[platform],duration_seconds=30,transcript_evidence={"provenance":{"extraction_policy":"bounded-native-1.0.0"}}))
        assert bounded_provider.compatible_cache(cached,settings())==(platform=="youtube")


def test_unknown_platform_is_not_ranked():
    decision=build_observed_intelligence("p",[item(platform="unknown"),item("content_2")],{}).decisions["reach"]
    assert decision["status"]=="incomparable" and decision["winner_slot"] is None


def test_social_hook_recommendation_has_correct_target_and_owned_evidence():
    segments,quality=evidence()
    a=item(platform="instagram",transcript_evidence=quality,duration_seconds=6)
    b=item("content_2",platform="facebook",views=20000,likes=100)
    value=build_observed_intelligence("p",[a,b],{"content_1":segments})
    assert value.recommendations
    assert all(r["target_content_id"]=="content_1" for r in value.recommendations)
    refs={r["evidence_id"]:r for content in value.contents for r in content["evidence"]}
    assert all(refs[e]["platform"]=="instagram" and refs[e]["content_id"]=="content_1" for r in value.recommendations for e in r["evidence_ids"])


@pytest.mark.parametrize("platform,field,value",[("instagram","followers",500),("facebook","followers",500),("youtube","subscribers",600)])
def test_rag_reports_platform_specific_creator_size_without_inference(platform,field,value):
    from app.rag.observed_context import project_current_context,observed_answer
    intelligence=build_observed_intelligence("p",[item(platform=platform,follower_count=500,subscriber_count=600),item("content_2")],{}).model_dump(mode="json")
    question=f"How many {field} does Content 1 have?"
    objective,summary,citations=project_current_context({"intelligence":intelligence},"reach",question)
    answer=observed_answer({"summary":summary,"selected_objective":objective},question,"metrics",citations)
    assert len(answer.metrics)==1 and answer.metrics[0].value==value
    assert answer.metrics[0].availability=="confirmed" and answer.metrics[0].slot=="content_1"
