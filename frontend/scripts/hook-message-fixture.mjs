/* Synthetic UI fixtures only; no model output or live source assertions. */
export function hookMessageFixture() {
  const make=(n)=>{
    const slot='content_'+n, content_id='video-'+n, evidence_id='opening-'+n;
    const partial=n===1;
    const text=partial?'Welcome to neuroscience.':'Dopamine is the topic. You will learn how brain signals work.';
    const scope={kind:'timed',label:`Inspected speech 0-${partial?5:8}s`,coverage:partial?'partial':'complete',requested_end:8,actual_ranges:[[0,partial?5:8]],word_count:text.split(' ').length};
    const ref={project_id:'fixture-project',content_id,slot,platform:'youtube',source_type:'opening',text,evidence_id,evidence_revision:'revision-'+n,start_time:0,end_time:partial?5:8};
    const finding=(rule,title,status,observation,measured={})=>({id:rule+'-'+n,rule_id:rule,title,status,matched:status==='detected'?true:status==='not_detected'?false:null,policy_version:'hook-message-2.0.0',evidence_ids:[evidence_id],evidence_quality:partial?'local':'complete',scope,observation,measured,excerpt:text,excerpt_start:0,excerpt_end:text.length,action_eligible:false,limitation:'Wording observations, not performance measurements.'});
    const assessments=[finding('opening_topic','Topic introduction',partial?'not_assessable':'detected',partial?'The partial passage cannot establish whether title terms appear throughout the opening window.':'Title terms found: dopamine (1 of 2).'),finding('generic_intro','Introduction pattern',partial?'detected':'not_detected',partial?'A welcome-style introduction starts the inspected passage.':'No recognized greeting starts the inspected opening.'),finding('explicit_takeaway','Viewer takeaway',partial?'not_assessable':'detected',partial?'The partial passage cannot establish whether an explicit takeaway appears throughout the opening window.':'An explicit learning or explanation phrase is present.')];
    if(!partial)assessments.push(finding('topic_position','Topic placement','detected','The first title-term match is at word 1 of the inspected passage.',{word_position:1,segment_range:[0,8]}));
    return {content_id,slot,platform:'youtube',title:partial?'Dopamine in a short introduction':'How dopamine supports brain signals',evidence:[ref],observations:assessments.filter(a=>a.status!=='not_assessable'),hook_message:{policy_version:'hook-message-2.0.0',status:partial?'partial':'assessed',topic_candidates:['dopamine','brain'],opening_scope:scope,assessments,limitations:[]}};
  };
  const contents=[make(1),make(2)];
  const recommendations=[{id:'experiment-a',target_content_id:'video-1',target_slot:'content_1',evidence_ids:['opening-1'],title:'Introduce the topic before background',experiment:'Test an opening that names dopamine before the welcome-style introduction.',priority:{label:'high',score:5},limitation:'No retention outcome is established.'}];
  return {contents,recommendations};
}
