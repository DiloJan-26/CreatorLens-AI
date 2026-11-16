import type { DecisionOutcome, GoalComparison } from "@/types/project";
export const objectiveNames:Record<string,string>={balanced:"Balanced",reach:"Reach",observed_reach:"Reach",engagement:"Engagement",creative_quality:"Creative quality",creator_efficiency:"Audience efficiency",public_performance:"Public performance"};
export function outcomeLabel(outcome:DecisionOutcome){return ({content_1:"Content 1 leads",content_2:"Content 2 leads",tie:"A close match",insufficient_evidence:"More evidence needed",incomparable:"Not directly comparable"})[outcome];}
export function decisionCopy(decision:GoalComparison){
 const objective=objectiveNames[decision.selected_objective]??"Comparison";
 const title=decision.winner_slot?`${decision.winner_slot==="content_1"?"Content 1":"Content 2"} leads under ${objective.toLowerCase()}`:outcomeLabel(decision.outcome);
 let description="";
 if(decision.winner_slot)description=({reach:"Higher confirmed lifetime views. This describes observed exposure, not growth speed.",engagement:"A higher observed interaction rate with sufficient comparable data. It does not measure sentiment or retention.",creative_quality:"A stronger assessment under the transcript-based creative rubric.",balanced:"The leading result under the balanced creator rubric, using compatible performance and creative evidence."})[decision.selected_objective];
 else if(decision.outcome==="tie")description="The difference falls within this objective's comparison tolerance. Both results remain visible below.";
 else if(decision.outcome==="incomparable")description="The available measurements or scoring inputs are not comparable under this objective.";
 else if(decision.selected_objective==="reach")description="Confirmed views are needed for both videos before reach can be compared.";
 else if(decision.selected_objective==="engagement")description="This comparison needs complete interaction counts and at least 1,000 views per video. Available likes and views are still useful context.";
 else if(decision.missing_evidence.some(value=>/semantic|creative/i.test(value)))description="Creative review is needed for both videos. You can explore Reach now while the remaining assessment is prepared.";
 else description="Some required scores are unavailable or use different evidence coverage. Review the supporting data before choosing a leader.";
 return {title,description,objective};
}
export function comparisonValue(value:number|null|undefined,units:string){if(value==null)return "Unavailable";const number=value.toLocaleString(undefined,{maximumFractionDigits:units==="views"?0:2});return `${number}${units==="percent"?"%":units==="points_out_of_10"?" / 10":units==="views"?" views":""}`;}
