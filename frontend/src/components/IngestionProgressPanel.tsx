import type {IngestionStatusResponse} from "@/types/project";
import {Icon} from "./ui";
export function IngestionProgressPanel({status}:{status:IngestionStatusResponse|null;isPolling:boolean}){
 if(!status||["READY","PARTIAL_READY"].includes(status.status))return null;
 const progress=Math.min(100,Math.max(0,status.progress_percent));
 return <section className="processing-card compact-progress" role="status"><Icon name={status.status==="FAILED"?"shield":"clock"}/><strong>{status.status==="FAILED"?"Analysis interrupted":"Analyzing your videos"}</strong><span>{progress}%</span>{status.status==="FAILED"?<p>{status.error_message??"Please retry later."}</p>:<div className="processing-track" role="progressbar" aria-label="Analysis progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}><span style={{width:`${progress}%`}}/></div>}</section>;
}
