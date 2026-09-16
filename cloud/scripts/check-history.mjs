import {trends} from '../src/trends.js';
import {database,subscriptions,history} from '../src/storage.js';
const sql=database(process.env);
const accounts=await subscriptions(sql);
const start=Date.now();
const h=await history(sql,accounts[0].tag);
if(!h.battles.length||h.totalStored<h.battles.length)throw new Error('Archive verification failed');
console.log(JSON.stringify({archiveRead:'success',stored:h.totalStored,displayed:h.battles.length,elapsedMs:Date.now()-start}));

const counts={road:0,seasonal:0,ranked:0,league:0};
for(const account of accounts){const t=await trends(sql,account.tag);for(const k of Object.keys(counts))counts[k]+=t.series[k].length;}
console.log(JSON.stringify({progressChartsRead:"success",points:counts}));
