import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const html=fs.readFileSync(new URL('../../app/templates/admin/dashboard.html',import.meta.url),'utf8');
const script=html.slice(html.indexOf('let isScanPaused = false;'),html.indexOf('function onAdminCodeInput('));
const elements=new Map(),listeners=new Map();
function el(){return {style:{},textContent:'',append(){},replaceChildren(){},scrollIntoView(){},addEventListener(){}};}
const document={getElementById(id){if(!elements.has(id))elements.set(id,el());return elements.get(id);},createElement:el};
const files=[{name:'unknown.txt',text:async()=> 'Email: None found\n.netflix.com\tTRUE\t/\tTRUE\t0\tNetflixId\tsynthetic-one'},
             {name:'known.txt',text:async()=> 'Email: known@example.test\n.netflix.com\tTRUE\t/\tTRUE\t0\tNetflixId\tsynthetic-two'}];
document.getElementById('bulkFolderInput').files=files;
let records,releaseOld;
const pendingOld=new Promise(resolve=>{releaseOld=resolve;});
const newJob={run:{id:'new-job',kind:'import',status:'running',total:2},processed:1,processing:[],counts:{LIVE:1},recent:[],history:[]};
const context=vm.createContext({document,console,decodeURIComponent,unescape,
 window:{addEventListener(name,fn){listeners.set(name,fn);},dispatchEvent(e){listeners.get(e.type)?.(e);}},
 CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}},
 alert(){throw new Error('Unexpected alert');},setTimeout(){return 1;},clearTimeout(){},
 async fetch(url,opt){
  if(url==='/admin/jobs/import'){records=JSON.parse(opt.body).accounts;return {ok:true,redirected:false,json:async()=>({id:'new-job'})};}
  if(url.includes('?id=new-job'))return {ok:true,redirected:false,json:async()=>newJob};
  return pendingOld;
 }});
vm.runInContext(fs.readFileSync(new URL('../../app/static/js/inventory-jobs.js',import.meta.url),'utf8'),context);
await vm.runInContext(script+'\nstartBulkScan()',context);
await new Promise(resolve=>setImmediate(resolve));
assert.equal(records.length,2);
assert.equal(records[0].email,null);
assert.equal(records[1].email,'known@example.test');
assert.equal(document.getElementById('scanCountText').textContent,'1 / 2');
assert.equal(document.getElementById('scanProgressBar').style.width,'50%');
assert.equal(document.getElementById('scanLiveCount').textContent,1);
releaseOld({ok:true,redirected:false,json:async()=>({...newJob,run:{...newJob.run,total:317,status:'completed'},processed:317})});
await new Promise(resolve=>setImmediate(resolve));
assert.equal(document.getElementById('scanCountText').textContent,'1 / 2');
console.log('Placeholder import and fresh job progress verified');
