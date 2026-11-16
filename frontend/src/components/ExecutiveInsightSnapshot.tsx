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
 const dimensions=[["observed_reach","trend"],["engagement","target"],["creative_quality","bulb"],["creator_efficiency","chart"]];
 return <section className="comparison-highlights" aria-label="Independent comparison signals"><h2>What stands out</h2><div className="highlight-grid">{dimensions.filter(([name])=>decision.dimension_leaders[name]).map(([name,icon])=>{const item=decision.dimension_leaders[name];return <article className="highlight-card creator-signal" key={name}><span className="signal-icon"><Icon name={icon} size={22}/></span><div><h3>{objectiveNames[name]}</h3><p>{outcomeLabel(item.outcome)}</p><span className="muted">{comparisonValue(item.values.content_1,item.units)} / {comparisonValue(item.values.content_2,item.units)}</span>{name==="engagement"&&item.outcome==="insufficient_evidence"&&[summary?.content_1,summary?.content_2].some(content=>content?.scoring?.metrics?.rates_percent.likes!=null)&&<span className="like-rate-context">Like rate: {summary?.content_1?.scoring?.metrics?.rates_percent.likes==null?"Unavailable":summary.content_1.scoring.metrics.rates_percent.likes.toFixed(2)+"%"} / {summary?.content_2?.scoring?.metrics?.rates_percent.likes==null?"Unavailable":summary.content_2.scoring.metrics.rates_percent.likes.toFixed(2)+"%"}<small>Descriptive context, not a complete engagement comparison.</small></span>}</div></article>;})}</div></section>;
}
