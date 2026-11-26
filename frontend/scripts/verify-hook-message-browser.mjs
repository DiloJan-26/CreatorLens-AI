/* Local browser acceptance of real Hook & Message cards with synthetic fixtures. */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const require=createRequire(import.meta.url);
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'creatorlens-hook-message-'));
if(!process.env.ACCEPTANCE_PLAYWRIGHT_PACKAGE)throw Error('Set ACCEPTANCE_PLAYWRIGHT_PACKAGE to an existing local Playwright installation.');
const {chromium}=require(process.env.ACCEPTANCE_PLAYWRIGHT_PACKAGE);
const webpack=require('next/dist/compiled/webpack/webpack').webpack;
const write=(name,text)=>{const file=path.join(temp,name);fs.writeFileSync(file,text);return file;};
const loader=write('loader.cjs',`const ts=require(${JSON.stringify(require.resolve('typescript'))});module.exports=s=>ts.transpileModule(s,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText;`);
const link=write('link.cjs',`const React=require(${JSON.stringify(require.resolve('react'))});module.exports=({children,...props})=>React.createElement('a',props,children);`);
const entry=write('entry.tsx',`
import React from 'react';import {createRoot} from 'react-dom/client';
import {HookMessageInsights} from '${path.join(root,'src/components/HookMessageInsights').replaceAll('\\','/')}';
import {hookMessageFixture} from '${path.join(root,'scripts/hook-message-fixture.mjs').replaceAll('\\','/')}';
const fixture=hookMessageFixture();
if(location.search.includes('missing'))fixture.contents.forEach(c=>{c.hook_message.status='not_assessable';c.hook_message.opening_scope={kind:'unavailable',coverage:'unavailable',label:'Opening evidence unavailable',actual_ranges:[],word_count:0};c.hook_message.assessments.forEach(a=>{a.status='not_assessable';a.observation='No current opening transcript is available.';a.evidence_ids=[];});});
createRoot(document.getElementById('root')).render(<div className="insights-workbench"><HookMessageInsights {...fixture}/></div>);
`);
await new Promise((resolve,reject)=>webpack({mode:'development',devtool:false,entry,output:{path:temp,filename:'bundle.js'},resolve:{extensions:['.tsx','.ts','.js','.mjs'],modules:[path.join(root,'node_modules'),'node_modules'],alias:{'next/link':link,'react$':require.resolve('react'),'react-dom/client':require.resolve('react-dom/client'),'react/jsx-runtime':require.resolve('react/jsx-runtime')}},module:{rules:[{test:/\.tsx?$/,use:loader}]}},(error,stats)=>error||stats.hasErrors()?reject(error??Error(stats.toString())):resolve()));
function cssFiles(dir){if(!fs.existsSync(dir))return [];return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?cssFiles(path.join(dir,e.name)):e.name.endsWith('.css')?[path.join(dir,e.name)]:[]);}
const css=cssFiles(path.join(root,'.next/static')).map(file=>fs.readFileSync(file,'utf8')).join('\n');
assert(css.includes('hook-card-top'),'Run the frontend build before browser acceptance.');
const server=http.createServer((req,res)=>{if(req.url==='/bundle.js'){res.setHeader('Content-Type','text/javascript');res.end(fs.readFileSync(path.join(temp,'bundle.js')));}else{res.setHeader('Content-Type','text/html');res.end('<html lang="en"><head><meta name="viewport" content="width=device-width, initial-scale=1"/><style>'+css+'</style></head><body><main class="page-container"><div id="root"></div></main><script src="/bundle.js"></script></body></html>');}});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin='http://127.0.0.1:'+server.address().port;
let browser;
try {
 browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1100}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>route.request().url().startsWith(origin)?route.continue():route.abort());
 await page.goto(origin);await page.getByRole('heading',{name:'Hook & Message Insights'}).waitFor();
 assert.equal(await page.locator('.hook-message-card').count(),2);
 assert.equal(await page.locator('.hook-experiment').count(),1);
 assert.equal(await page.locator('blockquote').count(),2);
 await page.getByText('Partial review',{exact:true}).waitFor();
 await page.getByText('Inspected speech 0-5s',{exact:false}).waitFor();
 assert.equal(await page.locator('details,select').count(),0);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:path.join(temp,'hook-message-desktop.png'),fullPage:true});
 await page.getByRole('link',{name:'View source evidence'}).first().focus();
 assert.equal(await page.evaluate(()=>document.activeElement?.getAttribute('href')),'/analyze#evidence');
 await page.setViewportSize({width:390,height:844});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:path.join(temp,'hook-message-mobile.png'),fullPage:true});
 await page.goto(origin+'?missing');await page.getByText('Evidence limited',{exact:true}).first().waitFor();
 assert.equal(await page.locator('.hook-experiment,blockquote').count(),0);
 assert.equal(await page.locator('.hook-coverage-note').count(),2);
 assert.deepEqual(errors,[]);
 console.log('PASS: real cards at desktop/mobile widths, partial scope, exact source grouping, one experiment, keyboard evidence link, no dropdowns, missing-evidence state and no external requests.');
 console.log('Screenshots: '+temp);
} finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
