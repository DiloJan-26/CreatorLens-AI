import type { CreatorInsightSummaryResponse } from "@/types/project";
import { decisionCopy,outcomeLabel,objectiveNames,comparisonValue } from "@/lib/intelligence-copy";
import { ResultBanner } from "./ResultBanner";
import { Icon } from "./ui";
export function ExecutiveInsightSnapshot({summary,isLoading=false}:{summary:CreatorInsightSummaryResponse|null;isLoading?:boolean}){
 const decision=summary?.goal_comparison;
 if(!decision)return <div className="notice">{isLoading?"Preparing your creator insights...":"Your comparison needs source evidence."}</div>;
 const copy=decisionCopy(decision);
 return <section className="insight-conclusion"><ResultBanner title={copy.title} description={copy.description} winner={Boolean(decision.winner_slot)} detail={<><span className="signal-label">{copy.objective}</span><strong>{decision.eligibility.status==="eligible"?"Assessed":"Review needed"}</strong></>}/></section>;
}
export function ComparisonHighlights({summary}:{summary:CreatorInsightSummaryResponse|null}){
 const decision=summary?.goal_comparison;if(!decision)return null;
 const rec=summary?.creator_recommendations?.recommendations[0];
 return <section className="comparison-highlights" aria-label="Independent comparison signals"><h2>Key insights</h2><div className="highlight-grid">{[["observed_reach","trend"],["engagement","target"]].map(([name,icon])=>{const value=decision.dimension_leaders[name];return <article className="highlight-card" key={name}><span className={`highlight-icon ${icon}`}><Icon name={icon} size={23}/></span><div><h3>{objectiveNames[name]}</h3><p>{value?outcomeLabel(value.outcome):"More evidence needed"}</p>{value&&<span className="muted">{comparisonValue(value.values.content_1,value.units)} / {comparisonValue(value.values.content_2,value.units)}</span>}</div></article>;})}<article className="highlight-card"><span className="highlight-icon bulb"><Icon name="bulb" size={23}/></span><div><h3>Opportunity</h3><p>{rec?.title??"Creative review needed"}</p><span className="muted">{rec?`${rec.target_slot==="content_1"?"Content 1":"Content 2"} ? ${rec.priority.label} priority`:"Review your videos in Insights."}</span></div></article></div></section>;
}
