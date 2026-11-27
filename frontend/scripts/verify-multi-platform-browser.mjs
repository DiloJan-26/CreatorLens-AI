/* Offline browser acceptance of multi-platform submission and canonical comparison results. */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const require=createRequire(import.meta.url);
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'creatorlens-multi-platform-'));
if(!process.env.ACCEPTANCE_PLAYWRIGHT_PACKAGE)throw Error('Set ACCEPTANCE_PLAYWRIGHT_PACKAGE to an existing local Playwright installation.');
const {chromium}=require(process.env.ACCEPTANCE_PLAYWRIGHT_PACKAGE);
const webpack=require('next/dist/compiled/webpack/webpack').webpack;
const write=(name,text)=>{const file=path.join(temp,name);fs.writeFileSync(file,text);return file;};
const loader=write('loader.cjs',`const ts=require(${JSON.stringify(require.resolve('typescript'))});module.exports=s=>ts.transpileModule(s,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText;`);
const link=write('link.cjs',`const React=require(${JSON.stringify(require.resolve('react'))});module.exports=({children,...props})=>React.createElement('a',props,children);`);
const api=write('api.cjs',`exports.getCreatorInsightSummary=()=>{throw Error('Unexpected API call');};`);
const session=write('session.cjs',`exports.setComparisonObjective=()=>{};`);
const components=path.join(root,'src/components').replaceAll('\\','/');
const entry=write('entry.tsx',`
import React,{useState} from 'react';import {createRoot} from 'react-dom/client';
import {VideoUrlForm} from '${components}/VideoUrlForm';
import {GoalComparisonPanel} from '${components}/GoalComparisonPanel';
window.fixture={submissions:[]};
const summary={project_id:'synthetic',intelligence:{decisions:{reach:{winner_slot:'content_2',comparison_scope:'cross_platform_descriptive',status:'eligible',outcome:'content_2',values:{content_1:2000,content_2:4000},units:'views',explanation:'Cross-platform reported views: 2000 versus 4000.',missing_inputs:[]}}}};
function App(){const [a,setA]=useState(''),[b,setB]=useState('');return <><VideoUrlForm content1Url={a} content2Url={b} setContent1Url={setA} setContent2Url={setB} onSubmit={()=>window.fixture.submissions.push([a,b])} isSubmitting={false}/><GoalComparisonPanel summary={summary}/></>}
createRoot(document.getElementById('root')).render(<App/>);
`);
await new Promise((resolve,reject)=>webpack({mode:'development',devtool:false,entry,output:{path:temp,filename:'bundle.js'},resolve:{extensions:['.tsx','.ts','.js','.mjs'],modules:[path.join(root,'node_modules'),'node_modules'],alias:{'next/link':link,'@/lib/api':api,'@/lib/app-session':session,'@':path.join(root,'src'),'react$':require.resolve('react'),'react-dom/client':require.resolve('react-dom/client'),'react/jsx-runtime':require.resolve('react/jsx-runtime')}},module:{rules:[{test:/\.tsx?$/,use:loader}]}},(error,stats)=>error||stats.hasErrors()?reject(error??Error(stats.toString())):resolve()));
function cssFiles(dir){if(!fs.existsSync(dir))return [];return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?cssFiles(path.join(dir,e.name)):e.name.endsWith('.css')?[path.join(dir,e.name)]:[]);}
const css=cssFiles(path.join(root,'.next/static')).map(file=>fs.readFileSync(file,'utf8')).join('\n');
assert(css.includes('compare-form'),'Build the frontend before browser acceptance.');
const server=http.createServer((req,res)=>{if(req.url==='/bundle.js'){res.setHeader('Content-Type','text/javascript');res.end(fs.readFileSync(path.join(temp,'bundle.js')));}else{res.setHeader('Content-Type','text/html; charset=utf-8');res.end('<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/><style>'+css+'</style></head><body><main class="page-container"><div id="root"></div></main><script src="/bundle.js"></script></body></html>');}});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin='http://127.0.0.1:'+server.address().port;
let browser;
try {
 browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1100}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>route.request().url().startsWith(origin)?route.continue():route.abort());
 await page.goto(origin);await page.getByRole('button',{name:'Analyze videos',exact:true}).waitFor();
 for(const platform of ['YouTube','Instagram','Facebook'])await page.getByText(platform,{exact:true}).waitFor();
 const urls=['https://youtube.com/watch?v=fixture','https://instagram.com/reel/fixture/','https://facebook.com/reel/12345/'];
 for(const a of urls)for(const b of urls){await page.locator('#content-url-1').fill(a);await page.locator('#content-url-2').fill(b);await page.getByRole('button',{name:'Analyze videos',exact:true}).click();}
 assert.equal(await page.evaluate(()=>window.fixture.submissions.length),9);
 await page.getByText('Content 2 leads reported reach',{exact:true}).waitFor();
 await page.getByText('Reported counts across platforms; view definitions and audiences differ.',{exact:true}).waitFor();
 await page.locator('#content-url-1').fill('https://facebook.com/share/r/opaque/');await page.getByRole('button',{name:'Analyze videos',exact:true}).click();
 assert.equal(await page.evaluate(()=>window.fixture.submissions.length),9);assert.equal(await page.getByRole('alert').count(),1);
 assert.equal(await page.locator('#content-url-1').getAttribute('aria-invalid'),'true');
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:path.join(temp,'multi-platform-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:path.join(temp,'multi-platform-mobile.png'),fullPage:true});
 assert.deepEqual(errors,[]);
 console.log('PASS: all nine platform pair submissions, canonical descriptive result, platform labels, unsafe URL prevention, desktop/mobile layout and no external requests.');
 console.log('Screenshots: '+temp);
} finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
