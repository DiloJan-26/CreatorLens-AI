/* Offline Chromium interactions against real Evidence/Transcript components.
   Uses an existing Playwright installation; all application APIs are mocked. */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import http from "node:http";
import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {fileURLToPath} from "node:url";
const require=createRequire(import.meta.url);
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const temp=fs.mkdtempSync(path.join(os.tmpdir(),"creatorlens-evidence-"));
if(!process.env.ACCEPTANCE_PLAYWRIGHT_PACKAGE) throw Error("Set ACCEPTANCE_PLAYWRIGHT_PACKAGE to an existing local installation.");
const {chromium}=require(process.env.ACCEPTANCE_PLAYWRIGHT_PACKAGE);
const webpack=require("next/dist/compiled/webpack/webpack").webpack;
const write=(name,text)=>{const file=path.join(temp,name);fs.writeFileSync(file,text);return file;};
const api=write("api.cjs",`module.exports=new Proxy({},{get:(_,name)=>(...args)=>window.fixture.api(name,...args)});`);
const loader=write("loader.cjs",`const ts=require(${JSON.stringify(require.resolve("typescript"))});module.exports=s=>ts.transpileModule(s,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText;`);
const components=path.join(root,"src/components").replaceAll("\\","/");
const entry=write("entry.tsx",`
import React from 'react';import {createRoot} from 'react-dom/client';
import {EvidenceSystemDetails} from '${components}/EvidenceSystemDetails';
import {TranscriptPreviewPanel} from '${components}/TranscriptPreviewPanel';
const contents=[1,2].map(n=>({id:'video-'+n,slot:'content_'+n,platform:'youtube',title:n===1?'How dopamine works':'Dopamine in two minutes',url:'https://youtube.com/watch?v=fixture'+n,transcript_available:n===1,transcript_segment_count:n===1?125:0,transcript_language:'en',metric_source_note:'Synthetic public metadata',transcript_source_note:'Synthetic native captions'}));
const chunk=(n,type,text)=>({project_id:'fixture-project',chunk_id:'chunk-'+n+'-'+type,content_id:'video-'+n,slot:'content_'+n,platform:'youtube',source_type:type,citation_label:'Content '+n+' / YouTube / '+type,text,title:contents[n-1].title,start_time:type==='hook'?0:null,end_time:type==='hook'?7:null,score:.8,match_details:{rank:n,vector_match:true,semantic_similarity:.8,keyword_overlap:.25,matching_terms:['dopamine'],contributions:{semantic:.44,keyword:.0625,source:.1,balance:0}}});
const chunks=[chunk(1,'hook','Dopamine is involved in motivation.'),chunk(2,'metadata','Views: 1000. Likes: 0.'),chunk(1,'description','An educational explanation.')];
const calls=[];window.fixture={calls,mode:'normal',async api(name,...args){calls.push({name,args:args.slice(0,2)});
 if(name==='getProjectEvidenceChunks')return {project_id:'fixture-project',total_chunks:3,chunks};
 if(name==='getMetadataAvailability')return {project_id:'fixture-project',items:contents.map((item,i)=>({...item,available_fields:['views','likes','transcript'],missing_fields:i?['comments']:[],completeness_score:90}))};
 if(name==='retrieveProjectChunks'){
  if(args[1].purpose!=='evidence_search')throw Error('Evidence purpose is required');
  const response=rows=>{
   const results=rows.map((c,i)=>{
    const matching_terms=['dopamine','views'].filter(term=>args[1].query.toLowerCase().includes(term)&&c.text.toLowerCase().includes(term));
    const keyword=matching_terms.length?.0625:0;
    return {...c,score:.54+keyword,match_details:{rank:i+1,vector_match:true,semantic_similarity:.8,keyword_overlap:matching_terms.length?.25:0,matching_terms,contributions:{semantic:.44,keyword,source:.1,balance:0}}};
   });
   return {project_id:'fixture-project',query:args[1].query,results,retrieval_mode:args[1].query.includes('views')?'metric_direct':'transcript_deep',retrieval_run_id:'synthetic-trace',retrieval_latency_ms:12,diagnostics:{embedding_model:'fixture-bge',embedding_version:'1',strategy:'Qdrant vector search + deterministic hybrid reranking',eligible_candidates:results.length,returned_by_slot:{content_1:results.filter(c=>c.slot==='content_1').length,content_2:results.filter(c=>c.slot==='content_2').length}}};
  };
  if(window.fixture.mode==='empty')return response([]);

  if(window.fixture.mode==='failure')throw Error('Synthetic vector store unavailable');
  if(window.fixture.mode==='wrong-content')return {project_id:'fixture-project',query:args[1].query,results:[{...chunks[0],content_id:'video-2'}]};
  if(window.fixture.mode==='deferred')return await new Promise(resolve=>window.fixture.resolve=()=>resolve({project_id:'fixture-project',query:args[1].query,results:[chunks[0]]}));
  return response(chunks.filter(c=>(!args[1].slot||c.slot===args[1].slot)&&(!args[1].source_type||c.source_type===args[1].source_type))));
 }
 if(name==='getTranscriptPreview')return {project_id:'fixture-project',slot:'content_1',platform:'youtube',transcript_available:true,transcript_segment_count:125,transcript_source:'Synthetic captions',segments:[{segment_index:0,text:'Source text remains source text.',start_time:null,end_time:null}]};
 throw Error('Unexpected API call: '+name);
}};
createRoot(document.getElementById('root')).render(location.pathname==='/transcript-fixture'?<TranscriptPreviewPanel projectId="fixture-project" item={contents[0]} label="Content 1"/>:<EvidenceSystemDetails projectId="fixture-project" indexReady={!location.search.includes('pending')} contents={contents}/>);
`);
await new Promise((resolve,reject)=>webpack({mode:"development",devtool:false,entry,output:{path:temp,filename:"bundle.js"},resolve:{extensions:[".tsx",".ts",".js"],modules:[path.join(root,"node_modules"),"node_modules"],alias:{"@/lib/api":api,"react$":require.resolve("react"),"react-dom/client":require.resolve("react-dom/client"),"react/jsx-runtime":require.resolve("react/jsx-runtime")}},module:{rules:[{test:/\.tsx?$/,use:loader}]}},(error,stats)=>error||stats.hasErrors()?reject(error??Error(stats.toString())):resolve()));
function cssFiles(dir){if(!fs.existsSync(dir))return [];return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?cssFiles(path.join(dir,e.name)):e.name.endsWith('.css')?[path.join(dir,e.name)]:[]);}
const css=cssFiles(path.join(root,'.next/static')).map(file=>fs.readFileSync(file,'utf8')).join('\n');
const server=http.createServer((req,res)=>{if(req.url==='/bundle.js'){res.setHeader('Content-Type','text/javascript');res.end(fs.readFileSync(path.join(temp,'bundle.js')));}else{res.setHeader('Content-Type','text/html');res.end('<html><head><meta name="viewport" content="width=device-width, initial-scale=1"/><style>'+css+'</style></head><body><main class="page-container"><div id="root"></div></main><script src="/bundle.js"></script></body></html>');}});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin='http://127.0.0.1:'+server.address().port;
let browser;
try {
 browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1100}});
 await page.route('**/*',route=>route.request().url().startsWith(origin)?route.continue():route.abort());
 const errors=[];page.on('pageerror',error=>errors.push(error.message));page.on('console',message=>{if(message.type()==='error')errors.push(message.text())});
 await page.goto(origin);await page.getByText('3 stored passages',{exact:true}).waitFor();
 assert.equal(await page.locator('.evidence-passage').count(),3);
 assert.equal(await page.getByText('Partial coverage',{exact:true}).count(),1);
 assert.equal(await page.locator('.evidence-time').count(),1);
 await page.screenshot({path:path.join(temp,'evidence-desktop.png'),fullPage:true});
 await page.getByLabel('Content',{exact:true}).selectOption('content_2');assert.equal(await page.locator('.evidence-passage').count(),1);
 await page.getByLabel('Evidence query').fill('confirmed views');await page.getByRole('button',{name:'Search evidence',exact:true}).click();
 await page.getByRole('heading',{name:'Results for "confirmed views"',exact:true}).waitFor();assert.equal(await page.locator('.evidence-passage').count(),1);
 await page.getByText('fixture-bge',{exact:false}).waitFor();await page.getByText('12 ms',{exact:true}).waitFor();
 assert.equal(await page.evaluate(()=>window.fixture.calls.find(c=>c.name==='retrieveProjectChunks').args[1].purpose),'evidence_search');
 await page.screenshot({path:path.join(temp,'retrieval-desktop.png'),fullPage:true});
 await page.getByRole('button',{name:'Browse all sources'}).click();await page.getByLabel('Content',{exact:true}).selectOption('all');
 await page.evaluate(()=>window.fixture.mode='empty');await page.getByRole('button',{name:'Search evidence',exact:true}).click();await page.getByText('No eligible indexed passages matched this search. Try another phrase or source type.',{exact:true}).waitFor();assert.equal(await page.locator('.evidence-passage').count(),0);
 await page.evaluate(()=>window.fixture.mode='wrong-content');await page.getByRole('button',{name:'Search evidence',exact:true}).click();
 await page.getByText('Returned evidence does not match the selected sources.',{exact:true}).waitFor();
 await page.evaluate(()=>window.fixture.mode='failure');await page.getByRole('button',{name:'Search evidence',exact:true}).click();await page.getByText('Synthetic vector store unavailable',{exact:true}).waitFor();
 await page.evaluate(()=>window.fixture.mode='deferred');await page.getByRole('button',{name:'Search evidence',exact:true}).click();
 await page.getByRole('button',{name:'Searching...',exact:true}).waitFor();await page.getByLabel('Content',{exact:true}).selectOption('content_2');await page.evaluate(()=>window.fixture.resolve());
 assert.equal(await page.locator('.evidence-passage[data-content-slot="content_1"]').count(),0);
 await page.goto(origin+'?pending');await page.getByText('Search not ready',{exact:true}).waitFor();assert.equal(await page.locator('.evidence-passage').count(),3);assert(await page.getByRole('button',{name:'Search evidence',exact:true}).isDisabled());
 await page.goto(origin);await page.getByText('3 stored passages',{exact:true}).waitFor();await page.setViewportSize({width:390,height:844});
 await page.getByLabel('Evidence query').fill('How is dopamine introduced?');await page.getByRole('button',{name:'Search evidence',exact:true}).click();await page.getByText('fixture-bge',{exact:false}).waitFor();assert(await page.locator('mark').count()>0);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));await page.screenshot({path:path.join(temp,'evidence-mobile.png'),fullPage:true});
 await page.goto(origin+'/transcript-fixture');await page.getByRole('button',{name:'Read transcript'}).click();await page.getByText('Source text remains source text.',{exact:true}).waitFor();await page.getByText('Showing 1 of 125 segments.',{exact:true}).waitFor();assert.equal(await page.locator('li > span').count(),0);
 assert.equal(await page.evaluate(()=>window.fixture.calls.find(c=>c.name==='getTranscriptPreview').args[1].slot),'content_1');assert.deepEqual(errors,[]);
 console.log('PASS: offline Evidence browser scenarios (including empty vector results, explicit search purpose, model/latency/rank diagnostics and safe term highlighting): source loading, coverage, timestamps, content filters, vector search, wrong identity rejection, provider error, stale response cancellation, pending index, mobile overflow, transcript reading and truncation disclosure.');console.log('Screenshots: '+temp);
} finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
