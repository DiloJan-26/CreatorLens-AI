import type {ContentInsight,CreatorRecommendationBundle} from "@/types/project";
import {Icon} from "./ui";
export function CreatorRecommendationList({bundle,contents,emptyMessage}:{bundle:CreatorRecommendationBundle;contents:(ContentInsight|null|undefined)[];emptyMessage?:string}){
 return <section className="ui-panel creator-actions" aria-label="Evidence-grounded creator recommendations"><h2><Icon name="bulb" size={21}/> What to try next</h2>
 {bundle.recommendations.length?<ol className="creator-action-list">{bundle.recommendations.map((item,index)=>{
 const target=contents.find(c=>c?.content_id===item.target_content_id&&c.slot===item.target_slot&&c.platform===item.target_platform);
 const owned=target&&item.project_id===bundle.project_id&&item.selected_objective===bundle.selected_objective&&item.evidence.every(ref=>ref.project_id===bundle.project_id&&contents.some(c=>c?.content_id===ref.content_id&&c.slot===ref.slot&&c.platform===ref.platform)&&(ref.role==="comparison_context"||ref.content_id===target.content_id));
 if(!owned)return <li key={item.id}>Recommendation unavailable: source mismatch.</li>;
 return <li key={item.id} data-recommendation-id={item.id}><div className="action-meta"><span className="action-target"><span className="action-rank">{String(index+1).padStart(2,"0")}</span>{target.label}</span><span className={`priority priority-${item.priority.label}`}>{item.priority.label} priority</span></div><h3>{item.title}</h3><p>{item.recommended_change}</p><p className="muted"><strong>Test: </strong>{item.experiment}</p><p className="action-basis">{item.observed_signal}</p>{item.example&&item.example.target_content_id===target.content_id&&<blockquote className="suggested-draft">Suggested draft: {item.example.text}</blockquote>}<p className="action-limit">{item.limitation}</p></li>;
 })}</ol>:<p className="muted mt-3">{emptyMessage??"No specific change is supported by the available evidence."}</p>}</section>;
}
