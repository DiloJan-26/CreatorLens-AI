"use client";
import {useCallback,useEffect,useRef,useState} from "react";
import {EngineeringLockButton} from "./EngineeringAccess";
import {PageHeading,Icon} from "./ui";
import {getEvaluationDatasets,getEvaluationRun,getEvaluationRuns} from "@/lib/api";
import type {EvaluationDatasetSummary,EvaluationRunSummary,EvaluationRunDetail,EvaluationResultSummary} from "@/types/evaluation";

const METRICS:Record<string,string>={faithfulness_lexical:"Lexical faithfulness (proxy)",response_relevance_lexical:"Response relevance (lexical)",context_relevance_lexical:"Context relevance (lexical)",context_precision_ragas:"Context precision (RAGAS non-LLM)",context_recall_ragas:"Context recall (RAGAS non-LLM)",citation_presence:"Citation presence",missing_evidence_compliance:"Missing-evidence compliance"};
const NAMES:Record<string,string>={creatorlens_ci_smoke_v1:"RAG smoke",creatorlens_core_v1:"RAG core",creatorlens_intelligence_ci_v2:"Intelligence critical",creatorlens_intelligence_v2:"Intelligence full"};

export function EvaluationDashboard(){
 const [datasets,setDatasets]=useState<EvaluationDatasetSummary[]>([]),[runs,setRuns]=useState<EvaluationRunSummary[]>([]);
 const [selectedId,setSelectedId]=useState<string|null>(null),[detail,setDetail]=useState<EvaluationRunDetail|null>(null);
 const [loading,setLoading]=useState(true),[detailLoading,setDetailLoading]=useState(false);
 const [error,setError]=useState<string|null>(null),[detailError,setDetailError]=useState<string|null>(null),[refreshVersion,setRefreshVersion]=useState(0);
 const request=useRef(0);
 const refresh=useCallback(async()=>{
  const version=++request.current;setLoading(true);setError(null);
  try{
   const [nextDatasets,nextRuns]=await Promise.all([getEvaluationDatasets(),getEvaluationRuns()]);
   if(version!==request.current)return;
   setDatasets(nextDatasets);setRuns(nextRuns);setSelectedId(current=>nextRuns.some(r=>r.id===current)?current:nextRuns[0]?.id??null);
   if(!nextRuns.length){setDetail(null);setDetailLoading(false);}
   setRefreshVersion(v=>v+1);
  }catch(e){if(version===request.current)setError(message(e));}
  finally{if(version===request.current)setLoading(false);}
 },[]);
 useEffect(()=>{const timer=setTimeout(()=>void refresh(),0);return()=>{clearTimeout(timer);};},[refresh]);
 useEffect(()=>{
  if(!selectedId)return;let active=true;
  const timer=setTimeout(()=>{
   setDetailLoading(true);setDetailError(null);setDetail(null);
   getEvaluationRun(selectedId).then(value=>{if(active)setDetail(value);}).catch(e=>{if(active)setDetailError(message(e));}).finally(()=>{if(active)setDetailLoading(false);});
  },0);
  return()=>{active=false;clearTimeout(timer);};
 },[selectedId,refreshVersion]);
 const selected=runs.find(r=>r.id===selectedId)??null;
 const activeDetail=detail?.run.id===selectedId?detail:null;
 return <main className="page-container engineering-view evaluation-dashboard"><div className="mx-auto max-w-7xl space-y-6">
  <PageHeading eyebrow="Engineering / Read-only" title="RAG Evaluation" icon="shield" description="Release checks, evidence grounding and regression history." action={<div className="engineering-header-actions"><button className="button-secondary" onClick={()=>void refresh()} disabled={loading}><Icon name="refresh" size={15}/>{loading?"Refreshing...":"Refresh results"}</button><EngineeringLockButton/></div>}/>
  {error&&<p role="alert" className="notice notice-error">{error}{runs.length>0?" Showing previously loaded results.":""}</p>}
  {loading&&!runs.length?<p role="status" className="ui-panel">Loading evaluation results...</p>:!selected&&!error?<EvaluationEmptyState/>:null}
  {selected&&<>
   <EvaluationRunView run={activeDetail?.run??selected}/>
   <div className="engineering-grid"><EvaluationMeasurements run={activeDetail?.run??selected}/><EvaluationHistory runs={runs} selectedId={selectedId} onSelect={setSelectedId}/></div>
   {detailError?<p role="alert" className="notice notice-error">Case results could not be loaded: {detailError}</p>:detailLoading?<p role="status" className="ui-panel">Loading case results...</p>:activeDetail?<EvaluationCaseResults key={activeDetail.run.id} detail={activeDetail}/>:null}
  </>}
  <EvaluationDatasets datasets={datasets}/>
 </div></main>;
}

export function EvaluationEmptyState(){
 return <section className="ui-panel evaluation-empty" aria-label="Evaluation publication status"><span className="stat-icon"><Icon name="shield" size={24}/></span><div><h2>No evaluation published</h2><p className="muted mt-2">Published release checks will appear here. Completing a video comparison does not run an evaluation.</p><p className="muted text-sm mt-2">Offline regression results are separate from live model quality.</p></div></section>;
}

export function EvaluationRunView({run}:{run:EvaluationRunSummary}){
 const gate=run.evaluation_details?.critical_gate,publication=run.publication,executed=run.passed_cases+run.failed_cases;
 const failedExecution=run.status==="FAILED";
 const cards=[
  {label:gate?"Critical contracts":"Regression cases",value:failedExecution?"Not completed":gate?`${gate.passed_cases}/${gate.total_cases}`:`${run.passed_cases}/${executed}`,note:gate?"Required deterministic checks":"Passed / executed"},
  {label:"Passed",value:String(run.passed_cases),note:`${executed} executed / ${run.total_cases} planned`},
  {label:"Failed",value:String(run.failed_cases),note:failedExecution?"Execution interrupted":"Cases requiring review"},
  {label:"Skipped",value:String(run.skipped_cases??0),note:publication?.not_executed_cases?`${publication.not_executed_cases} not executed`:"Excluded from executed-case totals"},
 ];
 return <section className="evaluation-selected" aria-label="Selected evaluation run">
  <div className="flex flex-wrap items-center justify-between gap-3"><div><p className="signal-label">{family(run)}</p><h2 className="text-xl font-semibold mt-1">{datasetName(run.dataset_name)} <span className="muted text-sm">v{run.dataset_version}</span></h2></div><RunBadge run={run}/></div>
  <p className="muted text-sm mt-2">Offline checks on curated fixtures. These results do not measure live Gemini accuracy.</p>
  {failedExecution&&<p role="alert" className="notice notice-error mt-3">{executionError(run.error_code)} No successful evaluation is claimed.</p>}
  <div className="engineering-stats mt-4">{cards.map((card,i)=><article className="engineering-stat" key={card.label}><span className="stat-icon"><Icon name={["shield","check","close","clock"][i]} size={20}/></span><p className="stat-label">{card.label}</p><p className="stat-value">{card.value}</p><p className="stat-note">{card.note}</p></article>)}</div>
  <dl className="evaluation-audit mt-4">
   <Audit label="Evaluated commit" value={publication?.source_commit?short(publication.source_commit):"Not recorded"} full={publication?.source_commit??undefined}/>
   <Audit label="Source identity" value={run.source_status==="current"?"Matches current backend":run.source_status==="different"?"Different backend source":"Historical / unverified"}/>
   <Audit label="Executed" value={date(run.completed_at??run.created_at)}/>
   <Audit label="Evaluator" value={run.evaluator}/><Audit label="Execution" value={publication?.execution_mode==="offline_regression"?"Offline / no provider inference":"Not recorded"}/><Audit label="Runtime" value={publication?.python_version?`Python ${publication.python_version}`:"Not recorded"}/>
   <Audit label="Source fingerprint" value={publication?.source_fingerprint?short(publication.source_fingerprint):"Not recorded"} full={publication?.source_fingerprint}/>
   <Audit label="Dataset fingerprint" value={publication?.dataset_fingerprint?short(publication.dataset_fingerprint):run.evaluation_details?.dataset_fingerprint?short(run.evaluation_details.dataset_fingerprint):"Not recorded"} full={publication?.dataset_fingerprint??run.evaluation_details?.dataset_fingerprint}/>
  </dl>
  {run.source_status==="different"&&<p className="notice mt-3">This run evaluates different backend source. Publish checks for the current release before treating it as verified.</p>}
  {publication?.non_reproducible_result&&<p className="notice mt-3">The same release and dataset produced different results. Both runs are retained for review.</p>}
  {publication?.source_state==="modified"&&<p className="notice mt-3">Evaluated with local source changes; the fingerprint identifies the tested code.</p>}
 </section>;
}

function Audit({label,value,full}:{label:string;value:string;full?:string}){return <div><dt>{label}</dt><dd title={full}>{value}</dd></div>;}

export function EvaluationMeasurements({run}:{run:EvaluationRunSummary}){
 const details=run.evaluation_details;
 if(run.status!=="COMPLETED")return <section className="ui-panel"><h2>Evaluation not completed</h2><p className="muted mt-2">Quality indicators are not available for this execution.</p></section>;
 return <section className="ui-panel quality-panel"><h2 className="text-lg font-semibold">Measured quality</h2>
  {details?.critical_gate?<>
   <p className="muted text-sm mt-2">Contract checks, synthetic retrieval and mocked Assistant responses. Each indicator retains its own denominator.</p>
   <div className="evaluation-indicators mt-4">{Object.entries(details.indicators??{}).map(([name,m])=><article key={name}><h3>{words(name)}</h3><strong>{m.denominator>0?`${m.numerator} / ${m.denominator}`:"Not measured"}</strong><p className="muted text-xs">{words(m.mode)}</p></article>)}</div>
   {details.grounding_confusion&&<section className="mt-5"><h3 className="font-semibold">Grounding decisions</h3><div className="evaluation-confusion mt-3">{Object.entries(details.grounding_confusion).map(([name,value])=><p key={name}><span>{words(name)}</span><strong>{value}</strong></p>)}</div><p className="muted text-xs mt-2">Labeled mocked responses; false accepts and false rejections are reported separately.</p></section>}
   {details.categories&&<section className="mt-5"><h3 className="font-semibold">Coverage by category</h3><div className="evaluation-table-wrap mt-3"><table className="evaluation-table"><thead><tr><th>Category</th><th>Passed</th><th>Failed</th><th>Skipped</th></tr></thead><tbody>{Object.entries(details.categories).map(([name,r])=><tr key={name}><td>{words(name)}</td><td>{r.passed}</td><td>{r.failed}</td><td>{r.skipped}</td></tr>)}</tbody></table></div></section>}
   <p className="muted text-xs mt-4">{details.limitations?.join(" ")}</p>
  </>:<><p className="muted text-sm mt-2">RAGAS non-LLM metrics and lexical proxies. Lexical similarity and citation presence do not prove semantic faithfulness.</p><div className="evaluation-indicators mt-4">{Object.entries(METRICS).filter(([key])=>number(run.aggregate_metrics[key])!==null).map(([key,label])=><article key={key}><h3>{label}</h3><strong>{number(run.aggregate_metrics[key])?.toFixed(3)}</strong></article>)}</div></>}
 </section>;
}

export function EvaluationHistory({runs,selectedId,onSelect}:{runs:EvaluationRunSummary[];selectedId:string|null;onSelect:(id:string)=>void}){
 return <section className="ui-panel"><h2 className="text-lg font-semibold">Run history</h2><p className="muted text-sm mt-2">Versioned results across all evaluation suites.</p><div className="evaluation-history mt-4">{runs.map(run=><button key={run.id} type="button" aria-pressed={run.id===selectedId} onClick={()=>onSelect(run.id)}><div className="flex flex-wrap items-start justify-between gap-2"><div><span className="signal-label">{family(run)}</span><h3>{datasetName(run.dataset_name)}</h3></div><RunBadge run={run}/></div><p className="muted text-xs mt-2">v{run.dataset_version} / {date(run.completed_at??run.created_at)}</p><p className="text-sm mt-2">{run.passed_cases} passed / {run.failed_cases} failed / {run.skipped_cases??0} skipped</p></button>)}</div></section>;
}

export function EvaluationCaseResults({detail}:{detail:EvaluationRunDetail}){
 const [query,setQuery]=useState(""),[page,setPage]=useState(0),[inspectedId,setInspectedId]=useState<string|null>(null);
 const rank:Record<string,number>={FAILED:0,SKIPPED:1,PASSED:2};
 const results=[...detail.results].filter(r=>(r.case_id+" "+(r.scenario??"")+" "+(r.evaluation_details?.category??"")+" "+r.status).toLowerCase().includes(query.toLowerCase())).sort((a,b)=>(rank[a.status]??3)-(rank[b.status]??3)||a.case_id.localeCompare(b.case_id));
 const pages=Math.max(1,Math.ceil(results.length/12)),current=Math.min(page,pages-1),visible=results.slice(current*12,current*12+12);
 const inspected=visible.find(r=>r.case_id===inspectedId)??visible[0];
 return <section className="ui-panel"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-lg font-semibold">Case results</h2><p className="muted text-sm mt-1">Failures and skipped references appear first.</p></div><label className="evaluation-search">Find a case<input type="search" value={query} onChange={e=>{setQuery(e.target.value);setPage(0);}} placeholder="Scenario, category or status"/></label></div>
  <div className="evaluation-cases mt-4">{visible.map(result=><button type="button" className="evaluation-case-row" key={result.case_id} aria-pressed={inspected?.case_id===result.case_id} onClick={()=>setInspectedId(result.case_id)}><div><strong>{result.scenario??words(result.case_id)}</strong><span className="muted text-xs">{result.case_id} / {words(result.evaluation_details?.execution_mode??"deterministic_fixture")}</span></div><span className={`evaluation-badge ${result.status==="PASSED"?"evaluation-pass":result.status==="FAILED"?"evaluation-fail":"evaluation-pending"}`}>{result.status}</span><Icon name="chevron" size={16}/></button>)}</div>
  {!results.length&&<p className="muted mt-3">{detail.results.length?"No matching cases.":"No case results were recorded for this execution."}</p>}
  {inspected&&<section className="mt-4" aria-label="Selected case details"><EvaluationCase result={inspected}/></section>}
  {results.length>12&&<nav aria-label="Case pages" className="flex flex-wrap items-center justify-between gap-3 mt-4"><button className="button-secondary" disabled={!current} onClick={()=>setPage(current-1)}>Previous</button><span className="muted text-sm">Page {current+1} of {pages} / {results.length} cases</span><button className="button-secondary" disabled={current+1===pages} onClick={()=>setPage(current+1)}>Next</button></nav>}
 </section>;
}

export function EvaluationCase({result}:{result:EvaluationResultSummary}){
 const detail=result.evaluation_details,checks=Object.entries(result.rubric_results);
 const reasons=detail?.failure_reasons?.length?detail.failure_reasons:checks.filter(([,check])=>!check.passed).map(([,check])=>check.message);
 const expected=detail?.expected_output,actual=detail?.actual_output;
 return <article className="evaluation-case"><div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><h3>{result.scenario??words(result.case_id)}</h3><p className="muted text-xs mt-1">{result.case_id}</p></div><span className={`evaluation-badge ${result.status==="PASSED"?"evaluation-pass":result.status==="FAILED"?"evaluation-fail":"evaluation-pending"}`}>{result.status}</span></div>
  <p className="muted text-xs mt-2">{words(detail?.category??result.answer_type??"Contract")} / {words(detail?.execution_mode??"deterministic_fixture")}{detail?.critical?" / Critical contract":""}{result.duration_ms==null?"":` / ${result.duration_ms} ms`}</p>
  {detail?.skip_reason&&<p className="evaluation-skip mt-3">{detail.skip_reason}</p>}
  {reasons.map(reason=><p className="evaluation-failure mt-2" key={reason}>{reason}</p>)}
  {checks.length>0&&<ul className="evaluation-checks mt-3">{checks.map(([name,check])=><li key={name}><Icon name={check.passed?"check":"close"} size={15}/><span><strong>{words(name)}</strong> / {check.message}</span></li>)}</ul>}
  {((expected&&Object.keys(expected).length>0)||(actual&&Object.keys(actual).length>0))&&<div className="evaluation-contract mt-3">{expected&&Object.keys(expected).length>0&&<div><h4>Expected contract</h4><pre>{JSON.stringify(expected,null,2)}</pre></div>}{actual&&Object.keys(actual).length>0&&<div><h4>Observed output</h4><pre>{JSON.stringify(actual,null,2)}</pre></div>}</div>}
  {(!actual||!Object.keys(actual).length)&&result.answer_text&&<p className="evaluation-answer mt-3">{result.answer_text}</p>}
  {result.citation_labels.length>0&&<p className="muted text-xs mt-3">Sources: {result.citation_labels.join(" / ")}</p>}
  {detail?.references?.length? <p className="muted text-xs mt-2">Contract references: {detail.references.join(" / ")}</p>:null}
 </article>;
}

export function EvaluationDatasets({datasets}:{datasets:EvaluationDatasetSummary[]}){
 if(!datasets.length)return null;
 return <section className="ui-panel"><h2 className="text-lg font-semibold">Available evaluation suites</h2><p className="muted text-sm mt-2">Bundled test definitions; availability does not indicate a completed run.</p><div className="evaluation-suite-grid mt-4">{datasets.map(dataset=><article key={dataset.name+dataset.version}><span className="stat-icon"><Icon name="evidence" size={18}/></span><div><h3>{datasetName(dataset.name)}</h3><p className="muted text-sm">{dataset.case_count} cases / v{dataset.version}</p></div></article>)}</div></section>;
}

function RunBadge({run}:{run:EvaluationRunSummary}){
 const gate=run.evaluation_details?.critical_gate;
 const pass=run.status==="COMPLETED"&&run.failed_cases===0&&(gate?gate.passed:run.passed_cases>0&&number(run.aggregate_metrics.pass_rate)===1);
 const label=run.status==="RUNNING"?"Running":run.status==="FAILED"?"Execution failed":run.failed_cases>0?"Review required":gate&&!gate.passed?"Critical checks failed":gate?"Critical checks passed":pass?"Regression passed":"Review required";
 return <span className={`evaluation-badge ${pass?"evaluation-pass":run.status==="FAILED"||run.failed_cases>0||gate&&!gate.passed?"evaluation-fail":"evaluation-pending"}`}>{label}</span>;
}
function family(run:EvaluationRunSummary){return run.dataset_name.startsWith("creatorlens_intelligence_")||run.evaluation_details?.critical_gate?"Creator Intelligence":"RAG Regression";}
function datasetName(value:string){return NAMES[value]??words(value);}
function words(value:string){return value.replaceAll("_"," ").replace(/\b\w/g,c=>c.toUpperCase());}
function short(value:string){return value.length>16?value.slice(0,12)+"...":value;}
function number(value:unknown){return typeof value==="number"&&Number.isFinite(value)?value:null;}
function date(value:string){const d=new Date(value);return Number.isNaN(d.getTime())?"Time not recorded":new Intl.DateTimeFormat("en",{dateStyle:"medium",timeStyle:"short"}).format(d);}
function message(error:unknown){return error instanceof Error?error.message:"Evaluation results could not be loaded.";}
function executionError(code:string|null){return code==="EVALUATION_TIMEOUT"?"Evaluation exceeded its execution time limit.":code==="EVALUATION_PROCESS_UNAVAILABLE"?"The evaluation process could not start.":"Evaluation execution failed.";}
