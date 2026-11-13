"""Build synthetic inputs, not expected answers. No SDK invocation or repository reads."""
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from app.insights.deterministic_scoring import calculate_scoring
from app.insights.semantic_evidence import build_semantic_input,parse_features
from app.insights.semantic_models import FEATURES
from app.insights.semantic_scoring import apply_semantic_scoring
from app.insights.comparison_engine import build_goal_comparison
from app.insights.recommendation_engine import build_creator_recommendations
from app.models.chat import Citation

ROOT=Path(__file__).parent
PROJECT='offline-intelligence-project'
CREATIVE=dict(hook_clarity=5,problem_solution_clarity=5,caption_strength=5,cta_strength=5,audience_specificity=5)


def fixtures():
    return json.loads((ROOT/'fixtures/intelligence_fixtures_v2.json').read_text(encoding='utf-8'))['fixtures']


def subject(slot,fixture,*,changes=None,labels=None,semantic=False):
    f=deepcopy(fixture)
    item={**f['metadata'],'id':'eval-'+slot,'project_id':PROJECT,'slot':slot,'platform':'youtube',
        'transcript_source':'synthetic_captions','transcript_evidence':{'status':'valid','revision':'revision-'+slot,
        'provenance':{'original_audio_language':f['language'],'caption_track_language':f['language'],'transcript_language':f['language'],'caption_kind':f['caption_kind']}}}
    item.update(changes or {})
    score=calculate_scoring(item,CREATIVE,hook_assessable=True)
    insight=SimpleNamespace(content_id=item['id'],slot=slot,platform=item['platform'],label=slot.replace('_',' ').title(),title=item['title'],creator='Synthetic creator',scoring=score,semantic_analysis={'status':'unavailable'},semantic_scoring=None)
    context=None;payload=None
    if semantic:
        context=build_semantic_input(PROJECT,item,f['segments'])
        values={**f['mocked_labels'],**(labels or {})}
        parts=[]
        for name in FEATURES:
            value=values[name]
            kind='opening' if name in {'opening_type','verbal_hook_clarity','topic_specificity','curiosity_gap'} else 'description' if name=='description_cta' else 'transcript'
            source=next((s for s in context['sources'] if s['source_type']==kind),None)
            if source is None:value='unassessable'
            refs=[] if value=='unassessable' else [dict(evidence_id=source['id'],content_id=item['id'],slot=slot,excerpt=source['text'],start_time=source['start_time'],end_time=source['end_time'])]
            if name=='evidence_coverage' and value!='unassessable':value='clear' if context['complete'] else 'partial'
            parts.append(dict(feature=name,value=value,status='unassessable' if value=='unassessable' else 'assessed',evidence=refs))
        payload=dict(schema_version='creative-features-1.0.0',project_id=PROJECT,content_id=item['id'],slot=slot,input_revision=context['input_revision'],features=parts)
        parsed=parse_features(json.dumps(payload),context)
        insight.semantic_analysis=dict(status='ready',snapshot_id='snapshot-'+slot,input_revision=context['input_revision'],features=parsed.model_dump(mode='json'),evidence_sources=context['sources'],evidence_complete=context['complete'],creative_policy='semantic-creative-1.0.0',schema_version='creative-features-1.0.0',prompt_version='1.0.0',model_id='mock-fixture-model')
        insight.semantic_scoring=apply_semantic_scoring(score,parsed,'snapshot-'+slot)
    return item,insight,context,payload


def comparison_inputs(fixture,inputs):
    left=dict(inputs.get('left') or {});right=dict(inputs.get('right') or {})
    if inputs.get('dopamine'):
        left.update(views=34021,likes=485,comments=8);right.update(views=1527222,likes=18876,comments=308)
    use_semantic=inputs.get('semantic',False)
    a=subject('content_1',fixture,changes=left,labels=inputs.get('left_labels') or inputs.get('labels'),semantic=use_semantic)
    b=subject('content_2',fixture,changes=right,labels=inputs.get('right_labels'),semantic=use_semantic)
    if inputs.get('damage')=='stale' and use_semantic:a[1].semantic_analysis['snapshot_id']='old'
    if inputs.get('damage')=='policy' and use_semantic:a[1].semantic_scoring.creative_policy_version='unknown'
    decision=build_goal_comparison(PROJECT,a[0],b[0],a[1],b[1],inputs.get('objective','balanced'))
    return a,b,decision


def assistant_context(fixture,inputs):
    from app.rag.intelligence_context import evidence_items
    from app.rag.query_router import resolve_comparison_objective
    question=inputs.get('question','Who wins under Reach?')
    objective=resolve_comparison_objective(question,inputs.get('objective')).value
    options={**inputs,'objective':objective,'dopamine':True,'semantic':bool(inputs.get('probe'))}
    a,b,decision=comparison_inputs(fixture,options)
    recommendations=build_creator_recommendations(PROJECT,decision,[(a[0],a[1]),(b[0],b[1])])
    citations=[];contents={}
    for item,insight,context,payload in (a,b):
        identity=getattr(decision,item['slot'])
        contents[item['slot']]=dict(content_id=item['id'],slot=item['slot'],platform=item['platform'],title=item['title'],creator=insight.creator,
            scoring=insight.scoring.model_dump(mode='json'),semantic_analysis=insight.semantic_analysis,semantic_scoring=insight.semantic_scoring.model_dump(mode='json') if insight.semantic_scoring else None,missing_metadata=['hashtags'])
        citations.append(Citation(project_id=PROJECT,content_id=item['id'],slot=item['slot'],platform=item['platform'],source_type='metadata',citation_label=item['slot']+' metadata',evidence_id='metric-'+item['slot'],evidence_revision=identity.metric_input_revision,text=json.dumps(insight.scoring.metrics.model_dump(mode='json'))))
        if context:
            for source in context['sources']:
                citations.append(Citation(project_id=PROJECT,content_id=item['id'],slot=item['slot'],platform=item['platform'],source_type=source['source_type'],citation_label=item['slot']+' '+source['id'][:12],evidence_id=source['id'],evidence_revision=identity.transcript_revision,text=source['text'],start_time=source['start_time'],end_time=source['end_time']))
    summary=dict(project_id=PROJECT,goal_comparison=decision.model_dump(mode='json'),creator_recommendations=recommendations.model_dump(mode='json'),**contents)
    return dict(policy_version='creator-intelligence-context-1.0.0',status='ready',project_id=PROJECT,selected_objective=objective,
        summary=summary,citations=[c.model_dump(mode='json') for c in citations],limitations=[],content_evidence={item['slot']:dict(quality=item['transcript_evidence'],duration=item['duration_seconds']) for item,_,_,_ in (a,b)}),citations,question
