"""Project current intelligence into existing chat/SSE contracts, without recalculating decisions."""
import json
import re
from app.models.chat import Citation
from app.llm.structured_outputs import ComparisonAnswer, MetricAnswer, MetricItem, RecommendationAnswer


def project_current_context(summary, selected, question):
    data=summary['intelligence']
    objective='comment_rate' if re.search(r'comment rate',question,re.I) else 'audience_efficiency' if re.search(r'efficiency|per subscriber',question,re.I) else selected
    dimension={'engagement':'like_rate','creative_quality':'structure'}.get(objective,objective)
    decisions={}
    for name,d in data['decisions'].items():
        decisions[name]=dict(**d,eligibility=dict(status=d['status'],reasons=d['missing_inputs'],missing_evidence=d['missing_inputs']),
            difference_content_1_minus_content_2=d['difference'],difference_units='percentage_points' if d['units']=='percent' else d['units'],
            contributions={},evidence_references={})
    selected_decision=decisions.get(dimension)
    if selected_decision is None:
        selected_decision=dict(outcome='insufficient_evidence',winner_slot=None,winner_content_id=None,values={},difference=None,
            difference_content_1_minus_content_2=None,difference_units='none',units='none',
            explanation='Opening and messaging are individual textual observations. No universal or creative-quality winner is inferred.',
            eligibility=dict(status='insufficient_evidence',reasons=[],missing_evidence=[]),limitations=[])
    identities={i['slot']:dict(content_id=i['content_id'],project_id=data['project_id'],platform=i['platform'],metric_input_revision=i['input_revision'],
                transcript_revision=i['transcript_revision']) for i in data['contents']}
    aliases={'reach':decisions['reach'],'engagement':decisions['like_rate'],'comment_rate':decisions['comment_rate'],'audience_efficiency':decisions['audience_efficiency']}
    decision=dict(project_id=data['project_id'],selected_objective=objective,decision_policy_version=data['policy_version'],metric_policy_version=data['policy_version'],
        creative_policy_version=data['text_policy_version'],**identities,**selected_decision,raw_objective_values=selected_decision['values'],
        missing_evidence=selected_decision['eligibility']['missing_evidence'],objective_decisions=aliases,
        dimension_leaders=dict(observed_reach=decisions['reach'],engagement=decisions['like_rate'],**decisions))
    summary['goal_comparison']=decision
    citations=[]
    for item in data['contents']:
        # Historical numerical/textual policies remain stored, but never enter the current prompt.
        content=summary.get(item['slot']) or {}
        content.update(semantic_analysis={},semantic_scoring=None)
        for ref in item['evidence']:
            citations.append(Citation(**{k:ref[k] for k in ('project_id','content_id','slot','platform','source_type','text','evidence_id','evidence_revision','start_time','end_time')},
                citation_label=f"Content {item['slot'][-1]} / {item['platform']} / {ref['source_type']} / {ref['evidence_id'][:12]}"))
    recs=[]
    evidence={r['evidence_id']:r for i in data['contents'] for r in i['evidence']}
    for r in data['recommendations']:
        recs.append(dict(**r,recommended_change=r['action'],evidence=[dict(evidence_id=eid,source_type=evidence[eid]['source_type']) for eid in r['evidence_ids']]))
    summary['creator_recommendations']=dict(policy_version=data['policy_version'],recommendations=recs,findings=[],limitations=data['limitations'])
    return objective,summary,citations


def observed_answer(context, question, intent, citations):
    from app.rag.intelligence_context import evidence_items,recommendation_items
    data=context['summary']['intelligence']; decision=context['summary']['goal_comparison'];objective=context['selected_objective']
    evidence=evidence_items(citations);text=question.lower()
    recommendations=recommendation_items(context,question,citations)
    if intent in {'improvement_suggestions','rewrite_request'} or re.search(r'\b(improve|recommend|experiment|test next)\b',text):
        return RecommendationAnswer(summary='Supported wording experiments from current evidence.' if recommendations else 'The available findings do not support a specific wording change.',
            objective=objective,evidence_status='supported' if recommendations else 'source_observations',recommendations=recommendations,evidence=evidence,limitations=data['limitations'])
    target=re.search(r'content ([12])',text)
    target_slot='content_'+target[1] if target else None
    if intent in {'hook_analysis','insight_summary'} or objective=='creative_quality':
        from app.services.evidence_window import requested_verbal_window
        window=requested_verbal_window(question)
        allowed={c.evidence_id for c in citations}
        observations=[f"Content {i['slot'][-1]}: "+o['observation'] for i in data['contents'] if not target_slot or i['slot']==target_slot for o in i['observations']
            if set(o['evidence_ids']).issubset(allowed) and (not window or o['rule_id']!='description_topic')]
        return ComparisonAnswer(winner='insufficient_evidence', confidence=0, objective=objective, decision_status='insufficient_evidence',
            evidence_status='source_observations', canonical_decision=decision, key_reasons=observations[:8] or [decision['explanation']],
            recommendations=recommendations,evidence=evidence,limitations=data['limitations'])
    compare=bool(re.search(r'which|winner|wins|leads|higher|lower|difference|overall|balanced|compare|real winner',text)) or intent=='performance_reasoning'
    if compare:
        reasons=[decision['explanation']]
        if objective=='balanced':reasons.extend(('observed_reach: ' if name=='reach' else name+': ')+d['explanation'] for name,d in data['decisions'].items())
        if decision.get('difference') is not None:reasons.append(f"Content 1 minus Content 2: {decision['difference']:.6f} {decision['difference_units']}.")
        return ComparisonAnswer(winner=decision['outcome'] if decision['outcome'] in {'content_1','content_2','tie'} else 'insufficient_evidence',confidence=0,
            objective=objective,decision_status=decision['outcome'],canonical_decision=decision,evidence_status=decision['eligibility']['status'],
            key_reasons=reasons,evidence=evidence,limitations=data['limitations']+decision['limitations'])
    if intent=='metadata_missing':
        fields=[i['slot']+': '+', '.join(k for k in ('views','likes','comments','subscribers') if i['values'].get(k) is None) for i in data['contents'] if not target_slot or i['slot']==target_slot]
        return MetricAnswer(summary='Unavailable extracted fields: '+'; '.join(fields),objective=objective,evidence_status='source_observations',evidence=evidence,limitations=data['limitations'])
    names=[n for n in ('views','likes','comments','subscriber_count','follower_count') if n.replace('_',' ') in text or n in text]
    if 'subscriber' in text:names=['subscriber_count']
    if 'follower' in text:names=['follower_count']
    if 'like rate' in text:names=['like_rate']
    elif 'comment rate' in text:names=['comment_rate']
    elif 'engagement' in text:names=['like_rate']
    if not names:names=['views'] if intent=='metrics' else []
    metrics=[]
    for item in data['contents']:
        if target_slot and target_slot!=item['slot']:continue
        label=next((c.citation_label for c in citations if c.slot==item['slot'] and c.source_type=='metadata'),None)
        selected={name:item['values'].get('subscribers' if name=='subscriber_count' else name) for name in names}
        if intent=='creator_info':selected.update({k:item.get(k) for k in ('creator','title','publication_date','duration_seconds')})
        for name,value in selected.items():
            metrics.append(MetricItem(name=name,slot=item['slot'],value=value,availability='confirmed' if value is not None else 'unavailable',citation_label=label if value is not None else None))
    return MetricAnswer(summary='Current observed public metrics. Engagement uses like rate; comment rate is reported independently.',objective=objective,
        evidence_status='source_observations',metrics=metrics,evidence=evidence,limitations=data['limitations'])
