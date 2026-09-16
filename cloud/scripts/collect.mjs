import {database,subscriptions,archive} from '../src/storage.js';
import {api} from '../src/api.js';
const env=process.env;
if(!env.CR_API_TOKEN||!env.DATABASE_URL)throw new Error('Missing required cloud secrets');
const sql=database(env),started=new Date().toISOString();
const accounts=await subscriptions(sql);
const [run]=await sql.query("INSERT INTO collection_runs (started_at,status,account_count) VALUES ($1,'running',$2) RETURNING id",[started,accounts.length]);
let success=0,added=0;
for(const account of accounts){
 try{
  const path='players/'+encodeURIComponent(account.tag);
  const player=await api(env,path),battles=await api(env,path+'/battlelog');
  if(!Array.isArray(battles))throw new Error('Invalid battle response');
  added+=await archive(sql,account.tag,player,battles);success++;
 }catch(e){console.error('Account collection failed',e.status||e.code||e.name);}
}
await sql.query('UPDATE collection_runs SET finished_at=$2,status=$3,success_count=$4,new_battles=$5 WHERE id=$1',[run.id,new Date().toISOString(),success===accounts.length?'success':'partial_failure',success,added]);
console.log(JSON.stringify({accounts:accounts.length,success,newBattles:added}));
if(success!==accounts.length)process.exitCode=1;
