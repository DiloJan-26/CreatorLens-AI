"""Canonical snapshot adapter and deterministic answer projection; no scoring or inference."""
import json
from copy import deepcopy
import re
from app.insights.insight_service import get_creator_insight_summary
from app.insights.comparison_engine import validate_semantic_content
from app.models.chat import Citation
from app.llm.structured_outputs import ComparisonAnswer, MetricAnswer, MetricItem, RecommendationAnswer, RecommendationItem, EvidenceItem
from app.rag.query_router import resolve_comparison_objective, parse_target_reference_slots
from app.services.storage_compat_service import get_project_detail_record
from app.services.hash_service import hash_payload

CONTEXT_POLICY='creator-intelligence-context-1.0.0'


def snapshot_fingerprint(project):
    return hash_payload({'project_id':project.get('id') or project.get('project_id'), 'contents':project.get('content_items',[])})


def build_intelligence_context(project_id, question, objective=None):
    selected=resolve_comparison_objective(question,objective)
    for _attempt in range(2):
        project=deepcopy(get_project_detail_record(project_id))
        if project is None:raise ValueError('Project not found.')
        if str(project.get('id') or project.get('project_id') or project_id)!=project_id:
            raise ValueError('Project identity mismatch.')
        fingerprint=snapshot_fingerprint(project)
        summary=get_creator_insight_summary(project_id,selected,project_record=project)
        latest=get_project_detail_record(project_id)
        if latest is not None and fingerprint==snapshot_fingerprint(latest):
            decision=summary.goal_comparison
            if decision is None or decision.project_id!=project_id:raise ValueError('Canonical decision unavailable.')
            citations=[]
            for slot in ('content_1','content_2'):
                content=getattr(summary,slot)
                identity=getattr(decision,slot)
                item=next((i for i in project.get('content_items',[]) if i.get('slot')==slot),None)
                if content is None or item is None or not identity.content_id or content.content_id!=identity.content_id:continue
                if content.scoring is not None:
                    citations.append(Citation(project_id=project_id,content_id=identity.content_id,slot=slot,platform=content.platform,
                        source_type='metadata',evidence_id='metric-'+identity.metric_input_revision,evidence_revision=identity.metric_input_revision,
                        citation_label=f'{content.label} / {content.platform} / confirmed metrics',
                        text=json.dumps(dict(metrics=content.scoring.metrics.model_dump(mode='json'),title=content.title,creator=content.creator,duration_seconds=item.get('duration_seconds')),ensure_ascii=False)))
                if validate_semantic_content(project_id,item,content) is None:
                    for source in content.semantic_analysis.get('evidence_sources',[]):
                        citations.append(Citation(project_id=project_id,content_id=identity.content_id,slot=slot,platform=content.platform,
                            source_type=source['source_type'],evidence_id=source['id'],evidence_revision=identity.transcript_revision,
                            start_time=source['start_time'],end_time=source['end_time'],
                            citation_label=f'{content.label} / {content.platform} / {source["source_type"]} / {source["id"][:12]}',text=source['text']))
            return dict(policy_version=CONTEXT_POLICY,status='ready',project_id=project_id,selected_objective=selected.value,
                snapshot_fingerprint=fingerprint,summary=summary.model_dump(mode='json'),
                content_evidence={i['slot']:dict(quality=i.get('transcript_evidence') or {},duration=i.get('duration_seconds')) for i in project.get('content_items',[]) if i.get('slot') in {'content_1','content_2'}},
                citations=[c.model_dump(mode='json') for c in citations],limitations=[])
    return dict(policy_version=CONTEXT_POLICY,status='evidence_changed',project_id=project_id,selected_objective=selected.value,
        snapshot_fingerprint=None,summary=None,citations=[],limitations=['Evidence changed during both snapshot attempts; retry the question. No mixed-revision decision was used.'])


def evidence_items(citations):
    return [EvidenceItem(citation_label=c.citation_label,claim='Authoritative stored evidence for this project/content snapshot.',
        claim_type='observation',project_id=c.project_id,content_id=c.content_id,evidence_id=c.evidence_id,
        evidence_revision=c.evidence_revision,slot=c.slot,platform=c.platform,source_type=c.source_type,
        excerpt=c.text,start_time=c.start_time,end_time=c.end_time) for c in citations]


def recommendation_items(context, question, citations):
    bundle=context['summary'].get('creator_recommendations') or {}
    target,_=parse_target_reference_slots(question)
    labels={c.evidence_id:c.citation_label for c in citations}
    items=[]
    for r in bundle.get('recommendations',[]):
        if target and r['target_slot']!=target:continue
        refs=[e['evidence_id'] for e in r['evidence']]
        metric_label=next((c.citation_label for c in citations if c.content_id==r['target_content_id'] and c.source_type=='metadata'),None)
        items.append(RecommendationItem(recommendation_id=r['id'],target_content_id=r['target_content_id'],target_slot=r['target_slot'],
            objective=context['selected_objective'],recommendation=r['recommended_change'],rationale=r['rationale'],priority=r['priority']['label'],
            citation_labels=list(dict.fromkeys([labels[x] for x in refs if x in labels]+([metric_label] if metric_label and any(e['source_type']=='metric_snapshot' for e in r['evidence']) else []))),
            source_evidence_ids=refs,experiment=r['experiment'],limitation=r['limitation']))
    return items


def canonical_answer(context, question, intent, citations=None):
    objective=context['selected_objective']
    if context['status']!='ready':
        return MetricAnswer(summary='Evidence changed while assembling the answer; please retry.',objective=objective,evidence_status='evidence_changed',limitations=context['limitations'])
    summary=context['summary'];decision=summary['goal_comparison']
    citations=citations if citations is not None else [Citation.model_validate(c) for c in context['citations']]
    evidence=evidence_items(citations)
    limitations=list(dict.fromkeys([*decision['limitations'],*decision['missing_evidence'],*context.get('limitations',[])]))
    text=question.lower()
    if intent in {'improvement_suggestions','rewrite_request'} or re.search(r'\b(recommend|improve|improvement|test next)\b',text):
        recommendations=recommendation_items(context,question,citations)
        bundle=summary.get('creator_recommendations') or {}
        target,_=parse_target_reference_slots(question)
        findings=[f['observation'] for f in bundle.get('findings',[]) if not target or f.get('target_slot')==target]
        message='Supported experiments from the canonical recommendation policy.' if recommendations else 'No current V2 actionable recommendation supports this request. Missing evidence is not a confirmed weakness.'
        return RecommendationAnswer(summary=message,objective=objective,evidence_status='supported' if recommendations else 'not_assessable',recommendations=recommendations,
            evidence=evidence,limitations=list(dict.fromkeys([*limitations,*bundle.get('limitations',[]),*findings[:5]])))
    comparison=bool(re.search(r'\b(which|winner|wins|leader|leads|higher|difference|compare|overall|balanced|creative quality|performs? better|performed better)\b',text)) or intent in {'performance_reasoning','hook_analysis','insight_summary'}
    if intent in {'creator_info','metadata_missing'} and not re.search(r'\b(winner|wins|overall|balanced|better|leads)\b',text) or intent=='metrics' and re.search(r'likes|comments|reactions|shares|followers|subscribers',text) and not re.search(r'views|engagement|winner|wins',text):
        comparison=False
    if comparison:
        reasons=[decision['explanation']]
        difference=decision['difference_content_1_minus_content_2']
        if difference is not None:
            reasons.append(f'Observed Content 1 minus Content 2 difference: {difference:.6f} {decision["difference_units"]}. The raw value is retained in the canonical decision.')
        if objective=='balanced' and decision['eligibility']['status']!='eligible':
            for name in ('observed_reach','engagement'):
                dimension=decision['dimension_leaders'][name]
                reasons.append(f'{name}: '+dimension['explanation'])
        elif objective=='balanced':
            for name in ('observed_reach','engagement','creative_quality'):
                dimension=decision['dimension_leaders'][name]
                if dimension['outcome']!=decision['outcome']:reasons.append(name+': '+dimension['explanation'])
        if intent in {'insight_summary','hook_analysis'}:
            target,_=parse_target_reference_slots(question)
            for slot in ('content_1','content_2'):
                if target and slot!=target:continue
                content=summary.get(slot) or {}
                analysis=content.get('semantic_analysis') or {}
                labels=[f for f in (analysis.get('features') or {}).get('features',[]) if f['status']=='assessed' and f['feature'] not in {'opening_type','evidence_coverage'}]
                if 'weakness' in text:labels=[f for f in labels if f['value'] in {'partial','absent'}]
                if 'strength' in text and 'weakness' not in text:labels=[f for f in labels if f['value']=='clear']
                if analysis.get('status')=='ready':
                    reasons.append(slot+' validated semantic labels (interpretations, not audience outcomes): '+(', '.join(f['feature']+'='+f['value'] for f in labels) or 'No assessed label matches this request.'))
                else:reasons.append(slot+': current semantic strengths/weaknesses are not assessable.')
        return ComparisonAnswer(winner=decision['outcome'] if decision['outcome']!='incomparable' else 'insufficient_evidence',
            confidence=0.0,objective=objective,decision_status=decision['outcome'],evidence_status=decision['eligibility']['status'],
            canonical_decision=decision,key_reasons=reasons,evidence=evidence,limitations=limitations,
            recommendations=recommendation_items(context,question,citations) if intent=='insight_summary' else [])
    if intent in {'general','content_summary'}:
        return RecommendationAnswer(summary='Current source evidence is available for inspection. Interpretations are limited to the cited text; no unsupported weakness or outcome is inferred.',objective=objective,
            evidence_status='source_observations',evidence=evidence,limitations=limitations)
    target,_=parse_target_reference_slots(question)
    names=[name for name in ('views','likes','reactions','comments','shares','subscriber_count','follower_count') if name.replace('_',' ') in text or name in text]
    if 'engagement' in text:names.append('combined_engagement_percent')
    if 'subscriber' in text and 'subscriber_count' not in names:names.append('subscriber_count')
    if 'follower' in text and 'follower_count' not in names:names.append('follower_count')
    if not names:names=['views'] if intent=='metrics' else []
    metrics=[]
    for slot in ('content_1','content_2'):
        if target and target!=slot:continue
        content=summary.get(slot)
        if not content or not content.get('scoring'):continue
        values=content['scoring']['metrics']
        if intent=='creator_info':
            observed={'creator':content.get('creator'),'title':content.get('title'),'upload_date':values.get('publication_date'),
                'duration_seconds':context.get('content_evidence',{}).get(slot,{}).get('duration')}
            for name,value in observed.items():
                if value is not None:
                    metadata_label=next((c.citation_label for c in citations if c.slot==slot and c.source_type=='metadata'),None)
                    metrics.append(MetricItem(name=name,slot=slot,value=value,availability='confirmed',citation_label=metadata_label))
        label=next((c.citation_label for c in citations if c.slot==slot and c.source_type=='metadata'),None)
        for name in names:
            value=values['rates_percent']['combined_engagement'] if name=='combined_engagement_percent' else values['counts'].get(name)
            metrics.append(MetricItem(name=name,slot=slot,value=value,availability='confirmed' if value is not None else 'unavailable',citation_label=label if value is not None else None))
    if intent=='metadata_missing':
        notes=[slot+': '+', '.join((summary.get(slot) or {}).get('missing_metadata',[])) for slot in ('content_1','content_2') if not target or slot==target]
        return MetricAnswer(summary='Unavailable extracted fields (not zero): '+ '; '.join(notes),objective=objective,evidence_status='source_observations',evidence=evidence,limitations=limitations)
    return MetricAnswer(summary='Current normalized public evidence; unavailable values are not zero.' if metrics else 'This snapshot provides evidence and limitations; no additional facts were inferred.',
        objective=objective,evidence_status='supported' if metrics else 'not_assessable',metrics=metrics,evidence=evidence,limitations=limitations)


def compact_prompt_context(context, question):
    if context['status']!='ready':return json.dumps(context)
    summary=context['summary'];decision=summary['goal_comparison'];target,_=parse_target_reference_slots(question)
    contents={}
    for slot in ('content_1','content_2'):
        content=summary.get(slot)
        if not content:continue
        semantic=content.get('semantic_analysis') or {}
        metric_scores=content.get('scoring') or {}
        semantic_scores=content.get('semantic_scoring') or {}
        breakdowns={name:metric_scores.get(name) for name in ('public_performance','creator_efficiency')}
        breakdowns.update({name:semantic_scores.get(name) for name in ('creative_structure','overall')})
        contents[slot]=dict(scoring_breakdowns=breakdowns,metric_policy=metric_scores.get('metric_policy_version'),
            creative_policy=semantic_scores.get('creative_policy_version'),content_id=content['content_id'],platform=content['platform'],metrics=(content.get('scoring') or {}).get('metrics'),
            semantic_status=semantic.get('status'),snapshot_id=semantic.get('snapshot_id'),
            features=[dict(feature=f['feature'],value=f['value'],status=f['status'],evidence_ids=[e['evidence_id'] for e in f['evidence']]) for f in (semantic.get('features') or {}).get('features',[])])
    recs=[r for r in (summary.get('creator_recommendations') or {}).get('recommendations',[]) if not target or r['target_slot']==target]
    return json.dumps(dict(policy=context['policy_version'],project_id=context['project_id'],objective=context['selected_objective'],
        authoritative_decision={key:decision[key] for key in ('outcome','winner_content_id','winner_slot','raw_objective_values','explanation','missing_evidence','decision_policy_version')},
        dimension_leaders={k:dict(outcome=v['outcome'],values=v['values'],eligibility=v['eligibility']) for k,v in decision['dimension_leaders'].items()},contents=contents,
        recommendations=[{key:r[key] for key in ('id','target_content_id','target_slot','category','recommended_change','rationale','experiment','priority','limitation')} for r in recs],
        limitations=decision['limitations'][:8]),ensure_ascii=False)


def context_is_current(context):
    if context['status']!='ready':return False
    project=get_project_detail_record(context['project_id'])
    return project is not None and snapshot_fingerprint(project)==context['snapshot_fingerprint']
