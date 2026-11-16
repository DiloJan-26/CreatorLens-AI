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
assert(panel.includes("Creative quality") && panel.includes("Engagement") && panel.includes("Reach"));
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
