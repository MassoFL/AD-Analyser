// Run with node --test tests/test_ui.cjs. Only synthetic ads and mocked HTTP.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function fixture(){
 const elements=new Map(),requests=[];
 const element=s=>{if(!elements.has(s))elements.set(s,{content:'test-csrf',value:'',innerHTML:'',textContent:'',hidden:false});return elements.get(s);};
 const sandbox={document:{querySelector:element,querySelectorAll:()=>[]},window:{addEventListener(){}},URLSearchParams,Map,console,
 setTimeout:()=>1,clearTimeout(){},setInterval(){},queueMicrotask(){},fetch:(path,options)=>new Promise(resolve=>requests.push({path,options,resolve}))};
 vm.createContext(sandbox);
 const code=fs.readFileSync(require('node:path').join(__dirname,'../static/app.js'),'utf8').replace('refresh();setInterval(', 'setInterval(');
 vm.runInContext(code,sandbox);
 const board={columns:{inbox:[],review:[{id:'a',stage:'review',revision:0,raw:'Lampe',reach:'1M',analyst:'',analysis:null},{id:'b',stage:'review',revision:0,raw:'Table',reach:'2M',analyst:'',analysis:null}],kept:[],rejected:[]},counts:{inbox:0,review:2,kept:0,rejected:0},totals:{inbox:0,review:2,kept:0,rejected:0},settings:{has_key:true},import:{},job:{}};
 sandbox.initial=structuredClone(board);vm.runInContext('board=initial;renderBoard()',sandbox);
 const run=s=>vm.runInContext(s,sandbox);
 const reply=(index,ok,data)=>requests[index].resolve({ok,json:async()=>data});
 return {run,requests,reply,elements,board};
}
test('review cards have two decision buttons and move before HTTP returns',async()=>{
 const f=fixture();assert.match(f.elements.get('#board').innerHTML,/>Retenir<\/button>/);assert.match(f.elements.get('#board').innerHTML,/>Écarter<\/button>/);
 const pending=f.run("move('a','kept')");
 assert.equal(f.run('board.columns.kept[0].id'),'a');assert.equal(f.run('board.totals.review'),1);assert.equal(f.run("pendingMoves.has('a')"),true);
 await f.run("move('a','rejected')");assert.equal(f.requests.length,1);
 f.reply(0,true,{ok:true});await pending;assert.equal(f.run('board.columns.kept[0].revision'),1);assert.equal(f.run('pendingMoves.size'),0);
});
test('failed decision rolls back only that card while another decision succeeds',async()=>{
 const f=fixture(),a=f.run("move('a','kept')"),b=f.run("move('b','rejected')");
 f.reply(1,true,{ok:true});await b;f.reply(0,false,{error:'Conflit'});await a;
 assert.equal(f.run('board.columns.review[0].id'),'a');assert.equal(f.run('board.columns.rejected[0].id'),'b');
 assert.equal(f.run('board.totals.kept'),0);assert.match(f.elements.get('#toast').textContent,/Conflit/);
});
test('a delayed poll cannot undo an optimistic decision',async()=>{
 const f=fixture(),poll=f.run('refresh()'),move=f.run("move('a','kept')");
 f.reply(0,true,f.board);await poll;assert.equal(f.run('board.columns.kept[0].id'),'a');
 f.reply(1,true,{ok:true});await move;assert.equal(f.run('board.columns.kept[0].id'),'a');
});
