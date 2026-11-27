"""Current deterministic intelligence: independent public signals and bounded text observations.

Policy anchors are editorial heuristics, not calibrated population statistics.
This module has no storage, clock, provider or model side effects.
"""
from fractions import Fraction
import math
from pydantic import BaseModel, Field
from app.insights.deterministic_scoring import normalize_metrics
from app.services.hash_service import hash_payload
from app.insights.hook_message import analyze_hook_message, POLICY as TEXT_POLICY

POLICY = "observed-intelligence-1.1.0"
SUPPORTED_PLATFORMS = frozenset({"youtube", "instagram", "facebook"})
SLOTS = ("content_1", "content_2")
MIN_VIEWS = 1000
LIKE_TOLERANCE = Fraction(1, 10)

class ObservedIntelligence(BaseModel):
    policy_version: str = POLICY
    text_policy_version: str = TEXT_POLICY
    project_id: str
    snapshot_revision: str
    contents: list[dict] = Field(default_factory=list)
    decisions: dict[str, dict] = Field(default_factory=dict)
    recommendations: list[dict] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

def _reference(project, item, kind, text, revision, start=None, end=None):
    payload=dict(project_id=project, content_id=item['content_id'], slot=item['slot'], platform=item['platform'],
                 source_type=kind, text=text, evidence_revision=revision, start_time=start, end_time=end)
    return dict(evidence_id=hash_payload(payload), **payload)

def _content(project, raw, segments):
    metrics=normalize_metrics(raw)
    content_id=raw.get('id') or raw.get('content_item_id') or raw.get('content_id')
    if not content_id or raw.get('slot') not in SLOTS or raw.get('project_id',project)!=project:
        raise ValueError('Invalid deterministic content ownership.')
    revision=hash_payload(dict(metrics=metrics.model_dump(mode='json'),title=raw.get('title'),description=raw.get('description'),
        caption=raw.get('caption'),transcript_evidence=raw.get('transcript_evidence'),segments=segments,
        text_policy=TEXT_POLICY, duration_seconds=raw.get('duration_seconds'), transcript_language=raw.get('transcript_language'),description_language=raw.get('description_language')))
    c=metrics.counts; v=c['views']; s=metrics.creator_size
    like=100*c['likes']/v if v and c['likes'] is not None else None
    comment=100*c['comments']/v if v and c['comments'] is not None else None
    values=dict(views=v,likes=c['likes'],comments=c['comments'],reactions=c['reactions'],shares=c['shares'],
        subscribers=c['subscriber_count'],followers=c['follower_count'],audience_size=s,like_rate=like,comment_rate=comment,
        combined_interaction_rate=metrics.rates_percent['combined_engagement'],audience_efficiency=v/s if s and v is not None else None)
    reach=min(10,10*math.log1p(v)/math.log1p(10_000_000)) if v is not None else None
    eligible=bool(v and v>=MIN_VIEWS and c['likes'] is not None and c['likes']<=v)
    response=min(10,2*like) if eligible else None
    item=dict(content_id=str(content_id),project_id=project,slot=raw['slot'],platform=metrics.platform,title=raw.get('title'),creator=raw.get('creator'),
        input_revision=revision,transcript_revision=(raw.get('transcript_evidence') or {}).get('revision'),source=raw,
        publication_date=metrics.publication_date,observed_at=metrics.observed_at,duration_seconds=raw.get('duration_seconds'),values=values,
        scores=dict(reach=round(reach,3) if reach is not None else None,like_response=round(response,3) if response is not None else None,
            public_performance=round((reach+response)/2,3) if reach is not None and response is not None else None),
        formulas=dict(like_rate='100*likes/views',comment_rate='100*comments/views',audience_efficiency='views/current_audience_size',
            reach='min(10,10*ln(1+views)/ln(10000001))',like_response='min(10,2*like_rate_percent)',public_performance='(reach+like_response)/2'),
        metric_provenance=metrics.provenance,field_provenance=(raw.get('transcript_evidence') or {}).get('provenance',{}).get('field_provenance',{}))
    metric=_reference(project,item,'metadata',__import__('json').dumps(dict(**values,title=item['title'],creator=item['creator'],duration_seconds=item['duration_seconds'],publication_date=item['publication_date']),sort_keys=True),revision)
    analysis,refs=analyze_hook_message(project,item,raw,segments)
    # Preserve the existing observation contract for supported facts. Explicit unknown
    # assessments live alongside it, without turning missing evidence into a weakness.
    obs=[finding for finding in analysis['assessments'] if finding['status']!='not_assessable']
    item.update(hook_message=analysis,observations=obs,evidence=[metric,*refs],limitations=analysis['limitations'])
    del item['source']
    return item

def _decision(contents, name):
    value_key={'reach':'views','like_rate':'like_rate','comment_rate':'comment_rate','audience_efficiency':'audience_efficiency'}[name]
    by={i['slot']:i for i in contents}; values={s:by[s]['values'][value_key] if s in by else None for s in SLOTS}
    missing=[]; incompatible=[]; notes=[]; scope='same_platform'
    if len(by)!=2:missing.append('Both distinct content slots are required.')
    if len(by)==2:
        a,b=(by[s] for s in SLOTS)
        if a['content_id']==b['content_id']:incompatible.append('Distinct content identities are required.')
        if any(i['platform'] not in SUPPORTED_PLATFORMS for i in (a,b)):
            incompatible.append('A supported public-video platform is required for each content.')
        if a['platform']!=b['platform']:
            scope='cross_platform_descriptive'
            notes.append('Cross-platform comparison of reported counts only: view definitions, audiences and distribution differ; the leader is not a platform-normalized effectiveness winner.')
        if name=='like_rate':
            notes.append('Only explicitly reported likes are used; Facebook reactions are never substituted for likes.')
        if a['publication_date']!=b['publication_date']:notes.append('Publication dates differ or are unknown; lifetime counts are not growth velocity.')
        notes.append('Counts have source observation times; differing snapshots are not simultaneous measurements.')
    if any(v is None for v in values.values()):missing.append('Required inputs for this signal are missing; other signals remain independent.')
    if name=='like_rate':
        for item in contents:
            if (item['values']['views'] or 0)<MIN_VIEWS:missing.append(item['slot']+': at least 1,000 views required for rate ranking.')
            if item['values']['likes'] is not None and item['values']['views'] is not None and item['values']['likes']>item['values']['views']:
                missing.append(item['slot']+': likes exceed views; inconsistent counts cannot be ranked.')
        notes.append('The 1,000-view threshold and 0.10-point tolerance are heuristic safeguards, not statistical significance.')
    if name=='audience_efficiency':notes.append('Current followers/subscribers may be rounded and are not historical audience size or conversion.')
    if name=='comment_rate':notes.append('Comment events do not establish audience sentiment. Values are descriptive; no winner policy is applied.')
    status='incomparable' if incompatible else 'insufficient_evidence' if missing else 'descriptive' if name=='comment_rate' else 'eligible'
    diff=None; outcome='incomparable' if incompatible else 'insufficient_evidence';winner=None
    if all(v is not None for v in values.values()):
        if name=='like_rate':
            a,b=(by[s]['values'] for s in SLOTS)
            diff=Fraction(100*a['likes'],a['views'])-Fraction(100*b['likes'],b['views'])
        else:diff=values['content_1']-values['content_2']
    if status=='eligible':
        outcome='tie' if abs(diff)<=(LIKE_TOLERANCE if name=='like_rate' else 0) else 'content_1' if diff>0 else 'content_2'
        winner=outcome if outcome in SLOTS else None
    elif status=='descriptive':outcome='descriptive'
    units='views' if name=='reach' else 'views_per_current_audience' if name=='audience_efficiency' else 'percent'
    explanation=(("Cross-platform reported " if scope=='cross_platform_descriptive' else "")+f"{name.replace('_',' ').title()}: "+(f"Content {winner[-1]} leads the observed signal." if winner else 'The observed values are equal or within the policy tolerance.' if outcome=='tie' else 'Descriptive values only.' if status=='descriptive' else ' '.join(incompatible+missing)))
    return dict(dimension=name,policy_version=POLICY,status=status,outcome=outcome,winner_slot=winner,
        winner_content_id=by[winner]['content_id'] if winner else None,values=values,difference=float(diff) if diff is not None else None,
        comparison_scope=scope,units=units,tie_tolerance=.10 if name=='like_rate' else 0,explanation=explanation,missing_inputs=missing,limitations=notes)

ACTIONS={
 'generic_intro':('opening','Introduce the topic before background','Test the same explanation with the topic in the first sentence, before the greeting.'),
 'opening_topic':('opening','Test a more explicit topic introduction','Keep the explanation unchanged and test an opening that names its specific subject in the first sentence.'),
 'explicit_takeaway':('takeaway','Test an explicit learning takeaway','If this is intended as an explanation, compare the current opening with one sentence stating what the viewer can learn.'),
 'description_topic':('description','Clarify the description opening','Keep the video unchanged and test a first description sentence that names the subject in the title.')}

def _recommendations(contents, objective):
    candidates=[]
    for item in contents:
        for ob in item['observations']:
            if ob['rule_id'] not in ACTIONS or not ob.get('action_eligible',False):continue
            trigger=ob['matched'] if ob['rule_id']=='generic_intro' else not ob['matched']
            # Absence-based experiments need complete applicable local evidence.
            if not trigger or ob['evidence_quality']!='complete' and not ob['matched']:continue
            group,title,experiment=ACTIONS[ob['rule_id']]
            relevance=2 if objective in {'creative_quality','structure','balanced'} or objective=='reach' and group in {'opening','description'} else 1
            rank=dict(evidence_support=2 if ob['evidence_quality']=='complete' else 1,objective_relevance=relevance,actionability=2)
            score=sum(rank.values())
            candidates.append(dict(id=hash_payload([POLICY,TEXT_POLICY,item['content_id'],ob['id'],group,objective]),policy_version=POLICY,
                project_id=item['project_id'],target_content_id=item['content_id'],target_slot=item['slot'],selected_objective=objective,
                category=group,title=title,observation=ob['observation'],trigger_rule=ob['rule_id'],detected_value=ob['measured'],
                evidence_ids=ob['evidence_ids'],input_revision=item['input_revision'],evidence_quality=ob['evidence_quality'],
                action=experiment,experiment=experiment,rationale='The cited textual pattern supports an optional wording experiment; a metric difference did not establish a creative defect.',
                priority=dict(**rank,score=score,label='high' if score>=5 else 'medium' if score>=3 else 'low'),
                limitation='A pattern not detected is not proof of weak content. No improvement, retention or revenue outcome is established.'))
    grouped={}
    for r in sorted(candidates,key=lambda x:(-x['priority']['score'],x['target_slot'],x['trigger_rule'])):
        key=(r['target_content_id'],r['category'])
        if key not in grouped:grouped[key]=r
        else:grouped[key]['evidence_ids']=sorted(set(grouped[key]['evidence_ids']+r['evidence_ids']))
    ranked=list(grouped.values())
    # Give each supported target one slot before filling the remaining display allowance.
    chosen=[]; seen=set()
    for r in ranked:
        if r['target_content_id'] not in seen:
            chosen.append(r);seen.add(r['target_content_id'])
    for r in ranked:
        if len(chosen)>=3:break
        if r not in chosen:chosen.append(r)
    return sorted(chosen,key=lambda r:(-r['priority']['score'],r['target_slot'],r['trigger_rule']))[:3]

def build_observed_intelligence(project_id, content_items, transcripts, objective='reach'):
    contents=[_content(project_id,item,transcripts.get(item.get('slot'),[])) for item in content_items if item]
    if len({i['slot'] for i in contents})!=len(contents) or len({i['content_id'] for i in contents})!=len(contents):
        raise ValueError('Duplicate content identity or slot.')
    contents.sort(key=lambda i:i['slot'])
    decisions={name:_decision(contents,name) for name in ('reach','like_rate','comment_rate','audience_efficiency')}
    return ObservedIntelligence(project_id=project_id,snapshot_revision=hash_payload([POLICY,TEXT_POLICY,[(i['content_id'],i['input_revision']) for i in contents]]),
        contents=contents,decisions=decisions,recommendations=_recommendations(contents,str(getattr(objective,'value',objective))),
        limitations=['Public counts do not measure retention, sentiment, revenue or causal effects.',
                      'Hook & Message Insights are source-scoped text observations, not a creativity score or universal winner.'])
