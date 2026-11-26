"""Independent fixtures for source-scoped Hook & Message rules; entirely offline."""
from copy import deepcopy
import pytest
from app.models.video import TranscriptSegment
from app.services.evidence_quality import assess_transcript
from app.insights.observed_intelligence import build_observed_intelligence
from app.insights.hook_message import POLICY, topic_terms


def segment(text, start=0, end=8, index=0):
    return dict(segment_index=index, start_time=start, end_time=end, text=text)


def content(segments=None, *, language='en', duration=60, caption_kind='original', **overrides):
    segments = segments or []
    provenance = dict(caption_track_language=language, caption_kind=caption_kind)
    clean, quality = assess_transcript([TranscriptSegment.model_validate(s) for s in segments],
        duration=duration, source='fixture', provenance=provenance)
    raw = dict(id='video-a', project_id='p', slot='content_1', platform='youtube', title='Dopamine Brain',
        views=34021, likes=485, comments=None, description='Dopamine supports brain signaling.',
        duration_seconds=duration, transcript_language=language, transcript_source='fixture', transcript_evidence=quality)
    raw.update(overrides)
    return raw, [s.model_dump() for s in clean]


def analyze(segments=None, **kwargs):
    raw, clean = content(segments, **kwargs)
    result = build_observed_intelligence('p', [raw], {'content_1': clean})
    item = result.contents[0]
    return item['hook_message'], item, result


def finding(analysis, rule):
    return next(f for f in analysis['assessments'] if f['rule_id'] == rule)


def test_complete_window_negative_checks_are_scoped_not_quality_judgments():
    analysis, item, result = analyze([segment('We begin with a few observations about cells.')])
    topic = finding(analysis, 'opening_topic')
    assert topic['status'] == 'not_detected' and topic['matched'] is False
    assert topic['scope']['actual_ranges'] == [[0.0, 8.0]]
    assert topic['scope']['coverage'] == 'complete'
    assert topic['action_eligible']
    assert result.recommendations and all(r['target_content_id'] == 'video-a' for r in result.recommendations)
    assert 'poor' not in topic['observation'].lower()
    assert 'creativity' in topic['limitation']


@pytest.mark.parametrize('start,end', [(0,5), (.1,8), (2,5), (0,7.999)])
def test_partial_speech_never_becomes_eight_second_absence(start, end):
    analysis, item, result = analyze([segment('Cells communicate in several different ways.', start, end)])
    assert analysis['opening_scope']['coverage'] == 'partial'
    assert analysis['opening_scope']['actual_ranges'] == [[start,end]]
    for rule in ('opening_topic','generic_intro','explicit_takeaway'):
        f = finding(analysis,rule)
        assert f['status'] == 'not_assessable' and f['matched'] is None
        assert not f['action_eligible']
    assert not result.recommendations
    assert all(o['rule_id'] == 'description_topic' for o in item['observations'])


def test_positive_detection_is_valid_even_in_only_five_seconds():
    analysis, item, result = analyze([segment('Welcome to neuroscience. Dopamine helps cells communicate.', 0, 5)])
    assert finding(analysis,'opening_topic')['status'] == 'detected'
    assert finding(analysis,'generic_intro')['status'] == 'detected'
    assert finding(analysis,'explicit_takeaway')['status'] == 'not_assessable'
    assert any(r['trigger_rule'] == 'generic_intro' for r in result.recommendations)
    assert not any(r['trigger_rule'] == 'explicit_takeaway' for r in result.recommendations)


def test_gapped_segments_keep_actual_ranges_without_fabricated_aggregate_time():
    analysis, item, result = analyze([segment('Welcome to this series.',0,2),segment('Cells communicate.',4,8,1)])
    assert analysis['opening_scope']['coverage'] == 'partial'
    assert analysis['opening_scope']['actual_ranges'] == [[0.0,2.0],[4.0,8.0]]
    assert finding(analysis,'opening_topic')['status'] == 'not_assessable'
    opening = next(e for e in item['evidence'] if e['source_type'] == 'opening')
    assert opening['start_time'] is None and opening['end_time'] is None


def test_boundary_crossing_segment_not_falsely_clipped():
    analysis, item, result = analyze([segment('Welcome to neuroscience. Dopamine is our subject.',0,12)])
    assert analysis['opening_scope']['kind'] == 'word_passage'
    assert analysis['opening_scope']['requested_end'] is None
    assert finding(analysis,'explicit_takeaway')['status'] == 'not_assessable'
    ref = next(e for e in item['evidence'] if e['source_type'] == 'transcript')
    assert ref['start_time'] is None and ref['end_time'] is None
    assert ref['text'].endswith('subject.')


def test_untimed_passage_is_bounded_without_timestamp_claims():
    analysis, item, result = analyze([segment('Dopamine ' + 'word '*80, None, None)])
    assert analysis['opening_scope']['word_count'] == 40
    assert analysis['opening_scope']['coverage'] == 'word_limited'
    f = finding(analysis,'topic_position')
    assert f['measured']['word_position'] == 1
    assert f['measured']['segment_range'] is None
    ref = next(e for e in item['evidence'] if e['source_type'] == 'transcript')
    assert len(ref['text'].split()) == 40 and ref['start_time'] is None


def test_short_video_uses_confirmed_duration_not_eight_second_fabrication():
    analysis, _, _ = analyze([segment('Cells send signals.',0,5)], duration=5)
    assert analysis['opening_scope']['coverage'] == 'complete'
    assert analysis['opening_scope']['requested_end'] == 5
    assert finding(analysis,'opening_topic')['status'] == 'not_detected'


@pytest.mark.parametrize('segments', [[], [segment('[Music]')], [segment('(Applause)')]])
def test_missing_or_music_only_speech_is_not_a_weak_hook(segments):
    analysis, item, result = analyze(segments)
    assert analysis['opening_scope']['kind'] == 'unavailable'
    assert all(f['status']=='not_assessable' for f in analysis['assessments'] if f['rule_id']!='description_topic')
    assert finding(analysis,'description_topic')['status'] == 'detected'
    assert not result.recommendations


def test_music_before_speech_cannot_prove_full_spoken_window():
    analysis, _, _ = analyze([segment('[Music]',0,3),segment('Cells communicate.',3,8,1)])
    assert analysis['opening_scope']['coverage'] == 'partial'
    assert finding(analysis,'opening_topic')['status'] == 'not_assessable'


@pytest.mark.parametrize('language', ['ta','hi','unknown',''])
def test_unsupported_language_does_not_block_independent_description_overlap(language):
    analysis, _, result = analyze([segment('Dopamine is discussed.')], language=language)
    assert finding(analysis,'opening_topic')['status'] == 'not_assessable'
    desc = finding(analysis,'description_topic')
    assert desc['status']=='detected' and desc['measured']['description_language'] is None
    assert not result.recommendations


def test_stale_transcript_is_excluded_but_current_description_is_usable():
    raw, segments = content([segment('Dopamine is discussed.')])
    segments[0]['text'] = 'Changed transcript text.'
    result = build_observed_intelligence('p',[raw],{'content_1':segments})
    analysis=result.contents[0]['hook_message']
    assert finding(analysis,'opening_topic')['status']=='not_assessable'
    assert 'revision' in finding(analysis,'opening_topic')['observation']
    assert finding(analysis,'description_topic')['status']=='detected'
    assert not any(r['source_type'] in {'opening','transcript'} for r in result.contents[0]['evidence'])


def test_word_boundaries_and_unicode_punctuation():
    analysis, _, _ = analyze([segment('Dopaminergic brainy concepts.')])
    assert finding(analysis,'opening_topic')['status']=='not_detected'
    analysis, _, _ = analyze([segment('DOPAMINE: you\u2019ll learn its role in the brain.')])
    assert finding(analysis,'opening_topic')['measured']['topic_coverage']==1
    assert finding(analysis,'explicit_takeaway')['status']=='detected'


def test_generic_title_tokens_not_treated_as_distinctive_subjects():
    assert topic_terms('Official Video: 2-Minute Dopamine Explained') == ['dopamine']
    analysis, _, _ = analyze([segment('Dopamine is a signaling chemical.')], title='Dopamine Brain')
    assert finding(analysis,'opening_topic')['measured']['topic_coverage']==.5
    assert finding(analysis,'opening_topic')['status']=='detected'


def test_ambiguous_series_name_is_literal_not_invented_topic_interpretation():
    analysis, _, _ = analyze([segment('Welcome to neuroscience.',0,5)], title='2-Minute Neuroscience: Dopamine')
    topic = finding(analysis,'opening_topic')
    assert topic['measured']['matching_terms']==['neuroscience']
    assert topic['measured']['topic_coverage']==.5
    assert 'dopamine' not in topic['observation'].lower()


def test_position_is_word_index_and_matching_segment_not_word_timestamp():
    analysis, _, _ = analyze([segment('Welcome to this series.',0,3),segment('Today dopamine is discussed.',3,8,1)])
    position=finding(analysis,'topic_position')['measured']
    assert position['word_position']==6 and position['segment_range']==[3.0,8.0]
    assert position['timing_precision']=='segment_range'
    assert 'timestamp' not in position


def test_description_absence_cannot_borrow_caption_language():
    analysis, _, result = analyze([segment('Dopamine is our topic. You will learn its role.')], description='Welcome to our channel.')
    desc=finding(analysis,'description_topic')
    assert desc['status']=='not_detected' and not desc['action_eligible']
    assert not any(r['category']=='description' for r in result.recommendations)
    analysis, _, result = analyze([], description='Welcome to our channel.', description_language='en')
    assert finding(analysis,'description_topic')['action_eligible']
    assert any(r['category']=='description' for r in result.recommendations)


@pytest.mark.parametrize('title,description', [(None,'Dopamine.'),('Official Video','Dopamine.'),('Dopamine',None)])
def test_missing_title_or_description_is_unknown_not_a_negative(title,description):
    analysis, _, _ = analyze([], title=title, description=description)
    assert finding(analysis,'description_topic')['status']=='not_assessable'


def test_translated_captions_do_not_trigger_original_speech_experiments():
    analysis, item, result = analyze([segment('Welcome to this series.')], caption_kind='translated')
    assert finding(analysis,'generic_intro')['status']=='detected'
    assert not any(f['action_eligible'] for f in analysis['assessments'] if f['scope']['kind']=='timed')
    assert not result.recommendations
    assert any('translated' in note for note in analysis['limitations'])


def test_excerpts_are_exact_owned_source_slices_and_bounded():
    analysis, item, _ = analyze([segment('Introductory words '*20 + 'dopamine is the topic.')])
    refs={r['evidence_id']:r for r in item['evidence']}
    for f in analysis['assessments']:
        if not f['evidence_ids']:continue
        ref=refs[f['evidence_ids'][0]]
        assert (ref['project_id'],ref['content_id'],ref['slot'])==('p','video-a','content_1')
        assert f['excerpt']==ref['text'][f['excerpt_start']:f['excerpt_end']]
        assert len(f['excerpt'])<=200
    assert 'dopamine' in finding(analysis,'opening_topic')['excerpt']


def test_empty_evidence_unknown_states_and_nulls_serialize():
    analysis, _, result = analyze([], title=None, description=None)
    assert analysis['status']=='not_assessable'
    assert len(analysis['assessments'])==5
    assert all(f['matched'] is None for f in analysis['assessments'])
    assert 'null' in result.model_dump_json() and not result.recommendations


def test_policy_version_and_reproducibility_without_metric_policy_changes():
    segments=[segment('Welcome to neuroscience. Dopamine is our topic.')]
    raw, clean=content(segments)
    result_a=build_observed_intelligence('p',[raw],{'content_1':clean})
    result_b=build_observed_intelligence('p',[deepcopy(raw)],{'content_1':deepcopy(clean)})
    item_a=result_a.contents[0]
    assert result_a.model_dump_json()==result_b.model_dump_json()
    assert result_a.text_policy_version==POLICY=='hook-message-2.0.0'
    assert result_a.policy_version=='observed-intelligence-1.0.0'
    assert item_a['values']['like_rate']==pytest.approx(100*485/34021)
    assert item_a['scores']['public_performance'] is not None
    assert not any('creative' in name for name in item_a['scores'])


def test_two_same_platform_targets_never_share_evidence_or_recommendation_identity():
    raw, segments = content([segment('Welcome to this series.')])
    second=deepcopy(raw);second.update(id='video-b',slot='content_2')
    value=build_observed_intelligence('p',[raw,second],{'content_1':segments,'content_2':segments},objective='creative_quality')
    assert value.recommendations and len(value.recommendations)<=3
    refs={r['evidence_id']:r for c in value.contents for r in c['evidence']}
    assert {r['target_content_id'] for r in value.recommendations}=={'video-a','video-b'}
    for r in value.recommendations:
        assert all(refs[e]['content_id']==r['target_content_id'] for e in r['evidence_ids'])
        assert r['priority']['score']==sum(r['priority'][k] for k in ('evidence_support','objective_relevance','actionability'))
    assert len({(r['target_content_id'],r['category']) for r in value.recommendations})==len(value.recommendations)


def test_unavailable_overall_does_not_remove_supported_findings():
    analysis, _, result=analyze([segment('Welcome to this series.')],views=None,likes=None)
    assert result.decisions['reach']['status']=='insufficient_evidence'
    assert finding(analysis,'generic_intro')['status']=='detected'
    assert result.recommendations


@pytest.mark.parametrize('question',['Explain the hooks','Explain the hooks in the first 8 seconds'])
def test_chat_uses_same_findings_and_preserves_partial_scope_disclosure(question):
    from app.rag.observed_context import project_current_context, observed_answer
    raw, segments = content([segment('Welcome to neuroscience.',0,5)])
    other=deepcopy(raw);other.update(id='video-b',slot='content_2')
    value=build_observed_intelligence('p',[raw,other],{'content_1':segments,'content_2':segments})
    objective, summary, citations=project_current_context({'intelligence':value.model_dump(mode='json')},'creative_quality',question)
    context=dict(status='ready',project_id='p',selected_objective=objective,summary=summary)
    answer=observed_answer(context,question,'hook_analysis',citations)
    assert answer.winner=='insufficient_evidence'
    assert any('does not establish absence' in reason for reason in answer.key_reasons)
    assert not any('No title-derived topic terms matched' in reason for reason in answer.key_reasons)
    assert all(c.content_id in {'video-a','video-b'} for c in citations)
    assert summary['intelligence']['text_policy_version']==POLICY


def test_revision_cache_is_bounded_identity_safe_and_cannot_be_mutated():
    from app.insights.hook_message import _cached_analysis
    _cached_analysis.cache_clear()
    raw, segments=content([segment('Welcome to neuroscience. Dopamine is discussed.')])
    first=build_observed_intelligence('p',[raw],{'content_1':segments})
    hits=_cached_analysis.cache_info().hits
    first.contents[0]['hook_message']['assessments'][0]['observation']='Forged caller mutation'
    second=build_observed_intelligence('p',[raw],{'content_1':segments})
    assert _cached_analysis.cache_info().hits==hits+1
    assert 'Forged' not in second.contents[0]['hook_message']['assessments'][0]['observation']
    misses=_cached_analysis.cache_info().misses
    changed=deepcopy(raw);changed['title']='Cell Communication'
    updated=build_observed_intelligence('p',[changed],{'content_1':segments})
    assert _cached_analysis.cache_info().misses==misses+1
    assert first.snapshot_revision!=updated.snapshot_revision
    assert _cached_analysis.cache_info().maxsize==64


def test_chronological_phrase_alone_is_not_a_viewer_takeaway():
    analysis, _, _=analyze([segment('By the end of yesterday, the experiment had finished.')])
    assert finding(analysis,'explicit_takeaway')['status']=='not_detected'


def test_bounded_takeaway_phrase_and_parenthetical_topic_are_preserved():
    analysis, _, _=analyze([segment('The chemical (dopamine) is our topic. By the end of this video, you will understand it.')])
    assert finding(analysis,'opening_topic')['measured']['matching_terms']==['dopamine']
    assert finding(analysis,'explicit_takeaway')['status']=='detected'
    assert finding(analysis,'topic_position')['measured']['word_position']==3
