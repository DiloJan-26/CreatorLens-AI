"""Real production boundaries exercised with explicit offline inputs; no reference generation."""
import json
from copy import deepcopy
from app.evaluations.intelligence_fixtures import subject,comparison_inputs,assistant_context,PROJECT,CREATIVE


def execute_case(case,fixture):
    i=case.inputs;op=case.operation
    if op=='stream':
        import os,subprocess,sys,tempfile
        from pathlib import Path
        env=dict(os.environ);env['PYTHONPATH']=str(Path(__file__).resolve().parents[2])
        with tempfile.TemporaryDirectory(prefix='creatorlens-stream-') as temp:
            result=subprocess.run([sys.executable,'-m','app.evaluations.offline_runner','--stream-probe',i['mode']],cwd=temp,env=env,capture_output=True,text=True,timeout=35)
        if result.returncode:raise ValueError('Isolated stream probe failed: '+result.stderr[-300:])
        return json.loads(result.stdout.strip().splitlines()[-1]),{}
    if op=='evidence':
        from app.services.evidence_quality import assess_transcript
        from app.models.video import TranscriptSegment
        provenance=dict(original_audio_language=i.get('audio_language','en'),caption_track_language=i.get('track_language','en'),transcript_language=i.get('track_language','en'),caption_kind=i.get('caption_kind','original'))
        usable,quality=assess_transcript([TranscriptSegment.model_validate(s) for s in i.get('segments',fixture['segments'])],duration=12,provenance=provenance,source='synthetic_captions')
        return dict(status=quality['status'],issues=quality['issues'],provenance=quality['provenance'],invented_confidence=quality['provider_confidence'] is not None),{}
    if op=='window':
        from app.services.evidence_window import select_evidence_window
        window=select_evidence_window(i['segments'])
        return dict(selected=len(window.segments),end=window.end,actual_ranges=window.describe()['actual_ranges']),{}
    if op=='revision':
        from app.services.evidence_quality import validate_extraction
        from app.models.video import VideoExtractionResult,VideoMetadata,TranscriptSegment
        from app.rag.chunk_builder import _make_chunk
        from app.services.project_service import _cache_hashes
        result=VideoExtractionResult(metadata=VideoMetadata(platform='youtube',url='https://youtu.be/synthetic',duration_seconds=12,transcript_source='captions',transcript_language='en',transcript_evidence={'provenance':{'original_audio_language':'en','caption_track_language':'en','caption_kind':'original'}}),transcript_segments=[TranscriptSegment.model_validate(s) for s in fixture['segments']])
        first=validate_extraction(result);second=first.model_copy(deep=True);second.metadata.transcript_evidence['provenance']['caption_kind']='translated';second=validate_extraction(second)
        def chunk(r):return _make_chunk(PROJECT,'eval-content_1','content_1','youtube','hook',0,'Source words','Source',evidence_revision=r.metadata.transcript_evidence['revision'])
        return dict(revision_changed=first.metadata.transcript_evidence['revision']!=second.metadata.transcript_evidence['revision'],chunk_changed=chunk(first).chunk_id!=chunk(second).chunk_id,cache_hash_changed=_cache_hashes(first)!=_cache_hashes(second)),{}
    if op=='scoring':
        from app.insights.deterministic_scoring import calculate_scoring
        a=subject('content_1',fixture,changes=i.get('changes'))
        result=a[1].scoring.model_dump(mode='json')
        result.update(scores_bounded=all(getattr(a[1].scoring,n).score is None or 0<=getattr(a[1].scoring,n).score<=10 for n in ('reach','engagement','public_performance','creator_efficiency','creative_structure','overall')),
            reproducible=a[1].scoring==calculate_scoring(a[0],CREATIVE,hook_assessable=True),confidence_separate=not any(c.feature=='engagement_confidence' for c in a[1].scoring.overall.components))
        return result,{}
    if op=='comparison':
        a,b,d=comparison_inputs(fixture,i)
        result=d.model_dump(mode='json');result['reproducible']=d==comparison_inputs(fixture,i)[2]
        return result,{}
    if op=='semantic':
        from app.insights.semantic_evidence import parse_features
        from app.insights.semantic_scoring import semantic_creative_score
        a=subject('content_1',fixture,semantic=True)
        context=deepcopy(a[2]);payload=deepcopy(a[3]);damage=i.get('damage');ref=payload['features'][0]['evidence']
        if damage=='unknown_id':ref[0]['evidence_id']='unknown'
        if damage=='wrong_content':ref[0]['content_id']='eval-content_2'
        if damage=='fabricated_excerpt':ref[0]['excerpt']='Invented quote'
        if damage=='fabricated_timestamp':ref[0]['end_time']=500.
        if damage=='partial_absence':context['complete']=False;payload['features'][1]['value']='absent'
        try:parsed=parse_features('not json' if damage=='malformed' else json.dumps(payload),context)
        except (ValueError,TypeError):return {'accepted':False},{}
        score=semantic_creative_score(parsed)
        assessed=sum(f.status=='assessed' for f in parsed.features)
        return dict(accepted=True,feature_present=i.get('feature') in {f.feature for f in parsed.features} if i.get('feature') else True,
            assessed_features=assessed,total_features=len(parsed.features),creative_score=score.score,
            reproducible=score==semantic_creative_score(parsed),labels={f.feature:f.value for f in parsed.features}),(dict(feature_coverage=dict(numerator=assessed,denominator=len(parsed.features),mode='distinct_format_mocked_model')) if case.case_id.startswith('semantic_format_') else {})
    if op=='recommendation':
        from app.insights.recommendation_engine import build_creator_recommendations,validate_recommendation,RecommendationSubject
        options={**i,'semantic':i.get('semantic',True),'left_labels':i.get('labels')}
        a,b,decision=comparison_inputs(fixture,options)
        bundle=build_creator_recommendations(PROJECT,decision,[(a[0],a[1]),(b[0],b[1])]);rejected=False
        if i.get('damage'):
            if not bundle.recommendations:raise ValueError('Mutation fixture requires an actionable recommendation.')
            r=bundle.recommendations[0].model_copy(deep=True)
            if i['damage']=='target':r.target_content_id=b[0]['id']
            if i['damage']=='revision':r.evidence[0].input_revision='stale'
            if i['damage']=='causal':r.recommended_change='This will increase retention.'
            if i['damage']=='priority':r.priority.label='low'
            subjects={x[0]['id']:RecommendationSubject(x[0],x[1],getattr(decision,x[0]['slot']),x[1].scoring.metrics,True) for x in (a,b)}
            try:validate_recommendation(r,subjects,decision)
            except ValueError:rejected=True
        output=dict(count=len(bundle.recommendations),merged=bundle.merged_candidates,first=bundle.recommendations[0].model_dump(mode='json') if bundle.recommendations else None,rejected=rejected)
        return output,{}
    if op=='retrieval':
        from app.models.rag import RetrievedChunk
        from app.rag.context_builder import validate_retrieved_source
        context,_,_=assistant_context(fixture,{})
        raw=dict(chunk_id='known-hook',content_id='eval-content_1',slot='content_1',platform='youtube',source_type='hook',text='Source opening',evidence_revision='revision-content_1',start_time=0.,end_time=4.,citation_label='Known source',score=.8)
        record={**raw,'project_id':PROJECT};damage=i.get('damage','none')
        if damage=='project':record['project_id']='foreign'
        if damage=='owner':raw['content_id']=record['content_id']='eval-content_2'
        if damage=='revision':raw['evidence_revision']=record['evidence_revision']='old'
        if damage=='text':raw['text']='Fabricated words'
        if damage=='time':raw['end_time']=record['end_time']=100.
        if damage=='type':raw['source_type']=record['source_type']='metadata'
        result=dict(accepted=validate_retrieved_source(RetrievedChunk(**raw),None if damage=='orphan' else record,PROJECT,context) is None)
        if i.get('ranking'):
            from app.rag.hybrid_search import build_hybrid_candidates
            from app.rag.reranker import rerank_candidates
            from app.schemas.retrieval import RetrievalMode
            from app.evaluations.intelligence_fixtures import ROOT
            reference=json.loads((ROOT/'fixtures/retrieval_references_v2.json').read_text(encoding='utf-8'))
            collection=[dict(record,chunk_id=d['id'],text=d['text'],chunk_index=n) for n,d in enumerate(reference['documents'])]
            ranked=rerank_candidates(build_hybrid_candidates(reference['query'],collection,[]),mode=RetrievalMode.HOOK_FOCUSED,top_k=2,balance_slots=False)
            ids=[r.candidate.chunk_id for r in ranked];relevant=set(reference['relevant_ids'])
            hits=len(set(ids)&relevant)
            result.update(ranked_ids=ids,precision_at_k=hits/len(ids) if ids else 0,recall_at_k=hits/len(relevant),identity_correctness=sum(r.candidate.content_id=='eval-content_1' for r in ranked)/len(ranked) if ranked else 0)
            return result,dict(retrieval_precision_at_k=dict(numerator=hits,denominator=len(ids),mode='synthetic_retrieval'),retrieval_recall_at_k=dict(numerator=hits,denominator=len(relevant),mode='synthetic_retrieval'))
        return result,{}
    if op in {'assistant','integration'}:
        from app.rag.intelligence_context import canonical_answer,evidence_items
        from app.rag.query_router import classify_question
        from app.llm.structured_output_service import parse_structured_output,render_structured_answer
        from app.llm.structured_outputs import ComparisonAnswer
        context,citations,question=assistant_context(fixture,i)
        baseline=canonical_answer(context,question,classify_question(question),citations)
        if op=='integration':
            d=context['summary']['goal_comparison']
            return dict(consistent=baseline.winner==d['outcome'],no_legacy_fallback='comparison' not in context['summary'],repeatable=baseline==canonical_answer(context,question,classify_question(question),citations)),{}
        output=baseline;rejected=False;metrics={};damage=i.get('damage')
        if damage or i.get('claim'):
            # Adversarial mutations of a production answer are contract probes, not independently authored gold answers.
            payload=baseline.model_dump(mode='json')
            if i.get('probe'):
                # Candidate wording is separately authored in JSONL; expected validity is not read from production output.
                payload=ComparisonAnswer(winner='content_2',confidence=.85,objective='reach',key_reasons=[i['claim']],evidence=evidence_items([next(c for c in citations if c.source_type==('metadata' if any(word in i['claim'].lower() for word in ('views','reach')) else 'opening'))])).model_dump(mode='json')
            elif i.get('claim'):payload['evidence'][0]['claim']=i['claim']
            if damage=='winner':payload['winner']='content_1'
            if damage=='objective':payload['objective']='balanced'
            if damage=='metric':payload['metrics'][0]['value']=123
            if damage=='content':payload['evidence'][0]['content_id']='eval-content_2'
            if damage=='revision':payload['evidence'][0]['evidence_revision']='old'
            if damage=='timestamp':payload['evidence'][0]['start_time']=99.
            if damage=='excerpt':payload['evidence'][0]['excerpt']='Invented quote'
            if damage=='confidence':payload['confidence']=.85
            parsed=parse_structured_output('not json' if damage=='malformed' else json.dumps(payload),payload['answer_type'],citations=citations,canonical_context=context,question=question,intent=classify_question(question))
            output=parsed.answer;rejected=parsed.used_fallback
            if i.get('probe'):
                accepted=any(i['claim'] in t for t in getattr(output,'key_reasons',[]) if t.startswith('Evidence-limited interpretation:'))
                label=i['label_valid'];key='true_accept' if label and accepted else 'false_reject' if label else 'false_accept' if accepted else 'true_reject'
                metrics['grounding_classification']={'cell':key,'label_valid':label,'candidate_accepted':accepted,'mode':'mocked_model','reference_basis':case.reference_basis}
                return dict(candidate_accepted=accepted,rejected=rejected,warnings=parsed.warnings,answer=output.model_dump(mode='json')),metrics
        return dict(answer=output.model_dump(mode='json'),rejected=rejected,metric_leaders_present=any('observed_reach' in s for s in getattr(output,'key_reasons',[])),percentage_rendered='85%' in render_structured_answer(output) or '**Confidence:**' in render_structured_answer(output)),metrics
    raise ValueError('Unknown executable evaluation operation.')
