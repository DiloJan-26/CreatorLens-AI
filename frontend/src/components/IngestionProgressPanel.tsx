"use client";
import type { IngestionStatusResponse } from "@/types/project";
import { Icon } from "./ui";
const labels:Record<string,string>={PENDING:"Queued",EXTRACTING_METADATA:"Collecting video details",EXTRACTING_TRANSCRIPT:"Reading captions",CHUNKING:"Preparing evidence",EMBEDDING:"Preparing search",INDEXING:"Organizing evidence",READY:"Evidence ready",PARTIAL_READY:"Evidence ready with limitations",FAILED:"Processing needs attention"};
export function IngestionProgressPanel({status,isPolling}:{status:IngestionStatusResponse|null;isPolling:boolean}){
 if(!status)return null;
 const terminal=["READY","PARTIAL_READY","FAILED"].includes(status.status),failed=status.status==="FAILED";
 const progress=Math.min(100,Math.max(0,status.progress_percent));
 return <details key={`${status.job_id}-${terminal}`} className={`processing-card ${failed?"processing-error":""}`} open={!terminal||failed} aria-live="polite">
  <summary><span className="signal-icon"><Icon name={failed?"shield":"evidence"} size={20}/></span><span><strong>Analysis progress</strong><span className="processing-caption">{labels[status.status]}</span></span><span className="processing-percent">{progress}%</span><span className="processing-toggle">Details</span></summary>
  <div className="processing-body"><div role="progressbar" aria-label="Evidence preparation progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress} className="processing-track"><span style={{width:`${progress}%`}}/></div>
  <p className="muted text-sm mt-3">{failed?status.error_message??"We could not finish preparing this evidence.":terminal?"Evidence preparation has finished. Creative review is shown separately.":isPolling?"Your videos are being prepared. You can collapse this panel while we work.":"Waiting for the next update."}</p>
  {status.status==="PARTIAL_READY"&&<p className="text-sm mt-2">Some source details have limitations. Available metrics and evidence remain usable.</p>}
  {status.retry_count>0&&<p className="muted text-xs mt-2">Processing retries: {status.retry_count}</p>}
  </div></details>;
}
