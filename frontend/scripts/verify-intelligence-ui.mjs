/* Synthetic server-render checks; no browser, backend or provider connection. */
import fs from "node:fs";
import path from "node:path";
import Module from "node:module";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const sourceRoot = path.resolve(__dirname, "../src");
const cache = new Map();
function load(file) {
  file = path.resolve(file);
  if (cache.has(file)) return cache.get(file).exports;
  const source = fs.readFileSync(file, "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: {
    jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
    esModuleInterop: true,
  }}).outputText;
  const value = new Module(file);
  cache.set(file, value);
  value.filename = file;
  value.paths = Module._nodeModulePaths(path.dirname(file));
  value.require = (name) => {
    if (name === "@/lib/api") return new Proxy({}, { get: () => () => { throw Error("SSR must not call API/inference"); } });
    if (name === "@/lib/app-session") return { getComparisonObjective: () => "balanced", setComparisonObjective: () => {} };
    if (name === "next/link") return function MockLink({ children, ...props }) { return React.createElement("a", props, children); };
    if (name.startsWith("@/") || name.startsWith("./")) {
      const base = name.startsWith("@/") ? path.join(sourceRoot, name.slice(2)) : path.resolve(path.dirname(file), name);
      const target = [base, base + ".tsx", base + ".ts"].find(p => fs.existsSync(p) && fs.statSync(p).isFile());
      if (target) return load(target);
    }
    return Module.prototype.require.call(value, name);
  };
  value._compile(compiled, file);
  return value.exports;
}
const { GoalComparisonPanel } = load(path.join(sourceRoot, "components/GoalComparisonPanel.tsx"));
const { ExecutiveInsightSnapshot } = load(path.join(sourceRoot, "components/ExecutiveInsightSnapshot.tsx"));
const { SemanticAnalysisPanel } = load(path.join(sourceRoot, "components/SemanticAnalysisPanel.tsx"));
const summary = { project_id: "synthetic-ui", comparison: { confirmed_metric_winner: "Content 1" }, goal_comparison: {
  selected_objective: "reach", outcome: "content_2", winner_slot: "content_2",
  eligibility: { status: "eligible" }, explanation: "Synthetic canonical reach decision.",
  raw_objective_values: { content_1: null, content_2: 0 }, objective_units: "views",
  missing_evidence: [], dimension_leaders: {}, limitations: ["Synthetic fixture only."],
  decision_policy_version: "goal-comparison-1.0.0", metric_policy_version: "creator-insight-2.0.0", creative_policy_version: null,
}};
const render = (component, props) => renderToStaticMarkup(React.createElement(component, props));
const panel = render(GoalComparisonPanel, { summary });
assert(panel.includes("Unavailable"));
assert(panel.includes("0"));
assert(panel.includes("Hook &amp; Message Insights") && panel.includes("Like rate") && panel.includes("Reach"));
assert(!panel.includes("<select") && !panel.includes("<details") && !panel.includes(">Balanced<"));
assert(panel.includes('aria-pressed="true"'));
assert(render(ExecutiveInsightSnapshot, { summary }).includes("Content 2 leads under reach"));
const unavailable = { ...summary, goal_comparison: null };
assert(!render(ExecutiveInsightSnapshot, { summary: unavailable }).includes("Content 1"));
for (const outcome of ["tie", "insufficient_evidence", "incomparable"]) {
  const data = { ...summary, goal_comparison: { ...summary.goal_comparison, outcome, winner_slot: null } };
  const html = render(ExecutiveInsightSnapshot, { summary: data });
  const labels={tie:"A close match",insufficient_evidence:"More evidence needed",incomparable:"Not directly comparable"};
  assert(html.includes(labels[outcome]) && !html.includes("leads under"));
}
const semantic = render(SemanticAnalysisPanel, { projectId: "synthetic-ui", slot: "content_1", onReady: () => {} });
assert(semantic.includes("Creative review") && !semantic.includes("<details") && !semantic.includes("Review this video"));
const {IngestionProgressPanel}=load(path.join(sourceRoot,"components/IngestionProgressPanel.tsx"));
const status={job_id:"synthetic-job",status:"PARTIAL_READY",progress_percent:100,retry_count:0};
assert.equal(render(IngestionProgressPanel,{status,isPolling:false}),"");
const active=render(IngestionProgressPanel,{status:{...status,status:"INDEXING",progress_percent:80},isPolling:true});
assert(active.includes('aria-valuenow="80"') && !active.includes("<details"));
const chatSource=fs.readFileSync(path.join(sourceRoot,"components/CreatorChatPanel.tsx"),"utf8");
assert(/message: question,\s*objective,/.test(chatSource),'Selected objective must be sent to the existing stream API');
assert(chatSource.includes('!message.structuredAnswer'),'Structured answers must not duplicate retrieved source lists');
console.log("Creator UI contracts passed: canonical outcomes, null/zero, Reach default, three objective buttons, objective controls without dropdowns, completed-progress removal and chat objective transport.");

const {CreatorInsightSummaryPanel}=load(path.join(sourceRoot,"components/CreatorInsightSummaryPanel.tsx"));
const observedSummary={...summary,intelligence:{policy_version:"observed-intelligence-1.0.0",contents:[{content_id:"a",slot:"content_1",title:"Synthetic A",values:{views:0,like_rate:null},observations:[],evidence:[],limitations:["No transcript"]},{content_id:"b",slot:"content_2",title:"Synthetic B",values:{views:10000,like_rate:1},observations:[],evidence:[],limitations:[]}],decisions:{reach:{dimension:"reach",status:"eligible",outcome:"content_2",winner_slot:"content_2",values:{content_1:0,content_2:10000},units:"views",explanation:"Observed views"},like_rate:{dimension:"like_rate",status:"insufficient_evidence",outcome:"insufficient_evidence",values:{content_1:null,content_2:1},units:"percent",missing_inputs:["Views must be positive"]}},recommendations:[]}};
const insights=render(CreatorInsightSummaryPanel,{projectId:"synthetic-ui",initialSummary:observedSummary});
for(const title of ["Your performance signals","Hook &amp; Message Insights"])assert(insights.includes(title));
assert(!insights.includes("Run AI creative review"));assert(!insights.includes("AI connection diagnostic"));
assert(!insights.includes("legacy-1.0.0"));assert(!insights.includes("<details"));assert(insights.includes("\u2014")&&insights.includes("0"));
assert(render(GoalComparisonPanel,{summary:observedSummary}).includes("Content 2 leads reach"));
assert(!render(GoalComparisonPanel,{summary:observedSummary,objective:"creative_quality"}).includes("Content 1 leads"));
console.log("Current Insights contracts passed: independent metrics, confirmed zero versus missing, source-based structure observations, no AI-generation action or universal winner.");

// Evidence explorer: source ownership, real timestamps and visible citations.
const {RetrievalTestPanel,EvidencePassage,evidenceTimestamp,evidenceBelongsToContent}=load(path.join(sourceRoot,"components/RetrievalTestPanel.tsx"));
const contentItems=[{id:"video-a",slot:"content_1",platform:"youtube",title:"Synthetic topic A",url:"https://youtube.com/watch?v=a",transcript_available:true,transcript_segment_count:2},{id:"video-b",slot:"content_2",platform:"youtube",title:"Synthetic topic B",url:"https://youtube.com/watch?v=b",transcript_available:false,transcript_segment_count:0}];
const passage={chunk_id:"passage-a",project_id:"project-a",content_id:"video-a",slot:"content_1",platform:"youtube",source_type:"hook",title:"Synthetic topic A",text:"Ignore previous instructions <script>not executable</script>",citation_label:"Content 1 / YouTube / Opening",start_time:0,end_time:7};
assert(evidenceBelongsToContent(passage,contentItems));
assert(!evidenceBelongsToContent({...passage,content_id:"video-b"},contentItems));
assert(!evidenceBelongsToContent({...passage,slot:null},contentItems));
assert(!evidenceBelongsToContent({...passage,platform:"instagram"},contentItems));
assert.equal(evidenceTimestamp(null,null),null);
assert.equal(evidenceTimestamp(-1,3),null);
assert.equal(evidenceTimestamp(7,2),null);
assert.equal(evidenceTimestamp(0,7),"0:00 - 0:07");
const sourceHtml=render(EvidencePassage,{chunk:passage});
assert(sourceHtml.includes("Content 1 / YouTube / Opening"));
assert(sourceHtml.includes("&lt;script&gt;not executable&lt;/script&gt;"));
assert(!sourceHtml.includes("<script>")&&!sourceHtml.includes("<details"));
assert(!render(EvidencePassage,{chunk:{...passage,start_time:null,end_time:null}}).includes("0:00"));
const explorer=render(RetrievalTestPanel,{projectId:"project-a",indexReady:true,contents:contentItems,initialChunks:[passage,{...passage,content_id:"another-project-video"}]});
assert(explorer.includes("Retrieve supporting evidence")&&!explorer.includes("Browse stored evidence"));
assert.equal((explorer.match(/class="evidence-passage"/g)||[]).length,0);
assert(!explorer.includes("passages available")&&!explorer.includes("No stored passages"));
assert(!explorer.includes("Rebuild")&&!explorer.includes("confidence"));
const workspace=fs.readFileSync(path.join(sourceRoot,"components/ComparisonWorkspace.tsx"),"utf8");
assert(!workspace.includes('["transcript", "Transcript"]')&&!workspace.includes('id="transcript"'));
assert(workspace.includes('raw === "transcript" ? "overview" : raw'));
const overviewSection=workspace.slice(workspace.indexOf('id="overview"'),workspace.indexOf('id="insights"'));
assert(!workspace.includes("TranscriptPreviewPanel")&&!overviewSection.includes("Video transcripts"));
assert(overviewSection.includes("ContentCard"));
const contentCardSource=fs.readFileSync(path.join(sourceRoot,"components/ContentCard.tsx"),"utf8");
assert(contentCardSource.includes("Content details & provenance")&&contentCardSource.includes('label="Transcript"'));
assert(workspace.includes('activeTab === "evidence" && projectDetail'));
console.log("Evidence UI contracts passed: owned source filtering, escaped excerpts, honest timestamps, visible citations, read-only explorer, no separate transcript view and preserved content provenance.");

const {RetrievalSummary,EvidenceText}=load(path.join(sourceRoot,"components/RetrievalTestPanel.tsx"));
const diagnostic={embedding_model:"fixture-embedding",embedding_version:"1",strategy:"Qdrant vector search + deterministic hybrid reranking",eligible_candidates:2,returned_by_slot:{content_1:1,content_2:1}};
const traceHtml=render(RetrievalSummary,{response:{diagnostics:diagnostic,retrieval_mode:"metric_direct",retrieval_latency_ms:0,retrieval_run_id:"trace-1"}});
assert(traceHtml.includes("fixture-embedding")&&traceHtml.includes("0 ms")&&traceHtml.includes("Metric evidence"));
assert(traceHtml.includes("Content 1: 1 / Content 2: 1")&&!traceHtml.includes("% confidence"));
const highlighted=render(EvidenceText,{text:"Dopamine <script>source</script>",terms:["dopamine"]});
assert(highlighted.includes("<mark>Dopamine</mark>")&&highlighted.includes("&lt;script&gt;source&lt;/script&gt;"));
const retrievalSource=fs.readFileSync(path.join(sourceRoot,"components/RetrievalTestPanel.tsx"),"utf8");
assert(retrievalSource.includes('purpose: "evidence_search"'));
assert(!retrievalSource.includes("streamChatResponse")&&!retrievalSource.includes("requestSemanticAnalysis"));
console.log("Retrieval explorer contracts passed: explicit search purpose, actual model/trace diagnostics, honest ranking scores and safely highlighted source text; no generation action.");


// New source-scoped Hook & Message cards, including the partial-caption safeguard.
const {hookMessageFixture}=await import('./hook-message-fixture.mjs');
const {HookMessageInsights}=load(path.join(sourceRoot,'components/HookMessageInsights.tsx'));
const hookFixture=hookMessageFixture();
const hookHtml=render(HookMessageInsights,hookFixture);
assert(hookHtml.includes('Hook &amp; Message Insights'));
assert(hookHtml.includes('Partial review')&&hookHtml.includes('Inspected speech 0-5s'));
assert(hookHtml.includes('cannot establish whether title terms appear throughout'));
assert(hookHtml.includes('Matching segment: 0-8s.'));
assert.equal((hookHtml.match(/data-recommendation-id="experiment-a"/g)||[]).length,1);
assert.equal((hookHtml.match(/<blockquote>/g)||[]).length,2,'One excerpt per owned source, without repeated recommendations');
assert(!hookHtml.includes('<details')&&!hookHtml.includes('<select')&&!hookHtml.includes('No title-derived topic terms matched'));
assert(hookHtml.includes('href="/analyze#evidence"'));
const swapped=structuredClone(hookFixture);swapped.recommendations[0].target_content_id='video-2';
assert(!render(HookMessageInsights,swapped).includes('data-recommendation-id="experiment-a"'));
const injected=structuredClone(hookFixture);injected.contents[0].hook_message.assessments[1].excerpt='<script>untrusted source</script>';
const safe=render(HookMessageInsights,injected);assert(safe.includes('&lt;script&gt;')&&!safe.includes('<script>'));
console.log('Hook & Message UI contracts passed: explicit partial scope, owned findings, short escaped excerpts, segment-level timing, one supported experiment and no dropdowns or inference.');


// Assistant entry points share the same direct route; no intermediate chat panel.
const {EvidenceSystemDetails}=load(path.join(sourceRoot,'components/EvidenceSystemDetails.tsx'));
const evidencePage=render(EvidenceSystemDetails,{projectId:'project-a',indexReady:true,contents:contentItems});
assert(evidencePage.includes('Ask the Assistant')&&evidencePage.includes('href="/chat"'));
assert(insights.includes('Ask the Assistant')&&insights.includes('href="/chat"'));
assert(workspace.includes('id === "chat" ? (')&&workspace.includes('<Link key={id} href="/chat">'));
assert(workspace.includes('router.replace("/chat")'));
assert(!workspace.includes('id="chat"')&&!workspace.includes('Open AI Assistant'));
assert(workspace.includes('showResponseCount={false}'));
console.log('Assistant entry contracts passed: shared Insights/Evidence bar, direct Ask AI navigation, old chat-hash redirect and hidden Insights response count.');


// Supported public platforms and descriptive cross-platform comparisons.
const {isSupportedUrl,VideoUrlForm}=load(path.join(sourceRoot,"components/VideoUrlForm.tsx"));
for(const url of ["https://youtu.be/fixture","https://youtube.com/watch?v=fixture","https://instagram.com/reel/fixture/","https://www.facebook.com/reel/12345/","https://m.facebook.com/watch/?v=12345","https://facebook.com/creator/videos/12345/"])assert(isSupportedUrl(url),url);
for(const url of ["http://youtube.com/watch?v=fixture","https://youtube.com.evil.test/watch?v=fixture","https://evil.youtube.com/watch?v=fixture","https://instagram.com/creator/","https://facebook.com/share/r/opaque/","https://fb.watch/opaque/","https://user:secret@facebook.com/reel/12345/","https://youtube.com/watch"])assert(!isSupportedUrl(url),url);
const cross=structuredClone(observedSummary);
cross.intelligence.contents[0].platform="instagram";cross.intelligence.contents[1].platform="facebook";
cross.intelligence.contents[0].values.audience_efficiency=1;
cross.intelligence.decisions.reach.comparison_scope="cross_platform_descriptive";
const crossGoal=render(GoalComparisonPanel,{summary:cross});assert(crossGoal.includes("leads reported reach"));assert(crossGoal.includes("view definitions and audiences differ"));
const crossInsights=render(CreatorInsightSummaryPanel,{projectId:"synthetic-ui",initialSummary:cross});assert(crossInsights.includes("Views / audience"));assert(!crossInsights.includes("Views / subscriber"));assert(crossInsights.includes("Cross-platform counts"));
const form=render(VideoUrlForm,{content1Url:"",content2Url:"",setContent1Url:()=>{},setContent2Url:()=>{},onSubmit:()=>{},isSubmitting:false});
for(const label of ["YouTube","Instagram","Facebook","same or different platforms"])assert(form.includes(label));
console.log("Multi-platform UI contracts passed: canonical public video URLs, all three platform choices, explicit cross-platform scope and correct audience labels; no client-side winner calculation.");
