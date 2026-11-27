/* Offline browser acceptance of automatic analysis completion; all APIs are mocked. */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const require=createRequire(import.meta.url);
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'creatorlens-auto-completion-'));
if(!process.env.ACCEPTANCE_PLAYWRIGHT_PACKAGE)throw Error('Set ACCEPTANCE_PLAYWRIGHT_PACKAGE to an existing local Playwright installation.');
const {chromium}=require(process.env.ACCEPTANCE_PLAYWRIGHT_PACKAGE);
const webpack=require('next/dist/compiled/webpack/webpack').webpack;
const write=(name,text)=>{const file=path.join(temp,name);fs.writeFileSync(file,text);return file;};
const loader=write('loader.cjs',`const ts=require(${JSON.stringify(require.resolve('typescript'))});module.exports=s=>ts.transpileModule(s,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText;`);
const link=write('link.cjs',`const React=require(${JSON.stringify(require.resolve('react'))});module.exports=({children,...props})=>React.createElement('a',props,children);`);
const account=write('account.cjs',`const refresh=async()=>{window.fixture.refreshes++;};exports.useAccount=()=>({refresh});`);
const api=write('api.cjs',`exports.getProjectUsage=async()=>({analysis_state:window.fixture.state,assistant_remaining:3});exports.completeAnalysis=async(project,metricsOnly)=>{window.fixture.completions.push({project,metricsOnly});if(window.fixture.fail)throw Error('Analysis evidence is unresolved.');window.fixture.state='completed';};`);
const components=path.join(root,'src/components').replaceAll('\\','/');
const entry=write('entry.tsx',`
import React from 'react';import {createRoot} from 'react-dom/client';
import {AnalysisAllowancePanel} from '${components}/AnalysisAllowancePanel';
const params=new URLSearchParams(location.search);
window.fixture={state:params.get('state')??'completed',completions:[],refreshes:0,fail:params.has('fail')};
createRoot(document.getElementById('root')).render(<React.StrictMode><h1>AI Assistant</h1><AnalysisAllowancePanel projectId="owned-project" ready={params.get('ready')==='true'} showResponseCount={!params.has('hidden')}/></React.StrictMode>);
`);
await new Promise((resolve,reject)=>webpack({mode:'development',devtool:false,entry,output:{path:temp,filename:'bundle.js'},resolve:{extensions:['.tsx','.ts','.js','.mjs'],modules:[path.join(root,'node_modules'),'node_modules'],alias:{'next/link':link,'@/lib/api':api,'@':path.join(root,'src'),'react$':require.resolve('react'),'react-dom/client':require.resolve('react-dom/client'),'react/jsx-runtime':require.resolve('react/jsx-runtime')}},plugins:[new webpack.NormalModuleReplacementPlugin(/^\.\/AccountProvider$/,account)],module:{rules:[{test:/\.tsx?$/,use:loader}]}},(error,stats)=>error||stats.hasErrors()?reject(error??Error(stats.toString())):resolve()));
function cssFiles(dir){if(!fs.existsSync(dir))return [];return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?cssFiles(path.join(dir,e.name)):e.name.endsWith('.css')?[path.join(dir,e.name)]:[]);}
const css=cssFiles(path.join(root,'.next/static')).map(file=>fs.readFileSync(file,'utf8')).join('\n');
assert(css.includes('analysis-save-row'),'Build the frontend before browser acceptance.');
const server=http.createServer((req,res)=>{if(req.url==='/bundle.js'){res.setHeader('Content-Type','text/javascript');res.end(fs.readFileSync(path.join(temp,'bundle.js')));}else{res.setHeader('Content-Type','text/html; charset=utf-8');res.end('<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/><style>'+css+'</style></head><body><main class="page-container"><div id="root"></div></main><script src="/bundle.js"></script></body></html>');}});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin='http://127.0.0.1:'+server.address().port;
let browser;
try {
 browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1100}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>route.request().url().startsWith(origin)?route.continue():route.abort());
 await page.goto(origin+'?state=processing&ready=true');await page.getByText('3 AI responses available',{exact:true}).waitFor();
 assert.deepEqual(await page.evaluate(()=>window.fixture.completions),[{project:'owned-project',metricsOnly:false}]);
 assert.equal(await page.getByRole('button').count(),0);
 assert.equal(await page.getByText('Save analysis',{exact:true}).count(),0);
 await page.screenshot({path:path.join(temp,'automatic-completion-desktop.png'),fullPage:true});
 for(const query of ['state=completed&ready=true','state=needs_reconciliation&ready=true','state=failed&ready=true','state=processing&ready=false']){
  await page.goto(origin+'?'+query);await page.getByRole('heading',{name:'AI Assistant'}).waitFor();await page.waitForTimeout(100);
  assert.equal(await page.evaluate(()=>window.fixture.completions.length),0,query);
 }
 await page.goto(origin+'?state=processing&ready=true&hidden');await page.waitForFunction(()=>window.fixture.state==='completed');
 assert.equal(await page.getByText('3 AI responses available',{exact:true}).count(),0);
 await page.goto(origin+'?state=processing&ready=true&fail');await page.getByRole('alert').waitFor();
 assert.equal(await page.getByRole('alert').textContent(),'Analysis evidence is unresolved.');
 assert.equal(await page.evaluate(()=>window.fixture.completions.length),1);
 await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:path.join(temp,'automatic-completion-mobile.png'),fullPage:true});
 assert.deepEqual(errors,[]);
 console.log('PASS: no Save button, ready-only completion, StrictMode duplicate protection, completed/failed/unresolved states, hidden Insights allowance, safe completion error, mobile layout and no external requests.');
 console.log('Screenshots: '+temp);
} finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
