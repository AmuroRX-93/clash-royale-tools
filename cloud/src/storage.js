import {neon,neonConfig} from '@neondatabase/serverless';
import {battleRow,summarize} from './domain.js';
neonConfig.fetchFunction=(url,options)=>fetch(url,{...options,signal:AbortSignal.timeout(20000)});
export function database(env){if(!env.DATABASE_URL)throw new Error('database_unconfigured');return neon(env.DATABASE_URL);}
export async function subscriptions(sql){const rows=await sql.query('SELECT player_tag,name FROM subscriptions ORDER BY added_at ASC,player_tag ASC');return rows.map(r=>({tag:r.player_tag,name:r.name||r.player_tag}));}
export async function addSubscription(sql,tag,name){const rows=await sql.query('INSERT INTO subscriptions (player_tag,name,added_at) VALUES ($1,$2,$3) ON CONFLICT (player_tag) DO UPDATE SET name=EXCLUDED.name RETURNING (xmax=0) AS created',[tag,name||tag,new Date().toISOString()]);return rows[0].created;}
export async function removeSubscription(sql,tag){return (await sql.query('DELETE FROM subscriptions WHERE player_tag=$1 RETURNING player_tag',[tag])).length>0;}
export async function archive(sql,tag,player,battles){
 const payload=battles.filter(b=>b.battleTime).map(b=>{const r=battleRow(b);return {id:`${tag}|${b.battleTime}|${r.mode}`,player_tag:tag,battle_time:b.battleTime,mode:r.mode,type:r.type,my_crowns:r.myCrowns,opp_crowns:r.oppCrowns,result:r.result,opp_name:r.oppName,opp_tag:r.oppTag,raw:JSON.stringify(b)};});
 const inserts=payload.length?await sql.query(`INSERT INTO battles (id,player_tag,battle_time,mode,type,my_crowns,opp_crowns,result,opp_name,opp_tag,raw) SELECT id,player_tag,battle_time,mode,type,my_crowns,opp_crowns,result,opp_name,opp_tag,raw FROM json_to_recordset($1::json) AS x(id text,player_tag text,battle_time text,mode text,type text,my_crowns integer,opp_crowns integer,result text,opp_name text,opp_tag text,raw text) ON CONFLICT (id) DO NOTHING RETURNING id`,[JSON.stringify(payload)]):[];
 await sql.query(`WITH lock AS (SELECT pg_advisory_xact_lock(hashtext($1))), last AS (SELECT trophies,battle_count FROM snapshots,lock WHERE player_tag=$1 ORDER BY ts DESC LIMIT 1) INSERT INTO snapshots (player_tag,ts,trophies,best,wins,losses,battle_count,three_crown) SELECT $1,$2,$3,$4,$5,$6,$7,$8 FROM lock WHERE NOT EXISTS (SELECT 1 FROM last WHERE trophies IS NOT DISTINCT FROM $3 AND battle_count IS NOT DISTINCT FROM $7)`,[tag,new Date().toISOString(),player.trophies??null,player.bestTrophies??null,player.wins??null,player.losses??null,player.battleCount??null,player.threeCrownWins??null]);
 if(player.name)await sql.query('UPDATE subscriptions SET name=$2 WHERE player_tag=$1',[tag,player.name]);
 return inserts.length;
}
export async function history(sql,tag,limit=500){const [brows,snapshots,total]=await Promise.all([
 sql.query('SELECT raw,battle_time,type,mode FROM battles WHERE player_tag=$1 ORDER BY battle_time DESC LIMIT $2',[tag,limit]),
 sql.query('SELECT ts,trophies,wins,losses,battle_count FROM (SELECT ts,trophies,wins,losses,battle_count FROM snapshots WHERE player_tag=$1 ORDER BY ts DESC LIMIT 2000) s ORDER BY ts ASC',[tag]),
 sql.query('SELECT count(*)::integer AS count FROM battles WHERE player_tag=$1',[tag])]);
 const raw=brows.map(r=>{try{return JSON.parse(r.raw)}catch{return {battleTime:r.battle_time,type:r.type,gameMode:{name:r.mode}}}}),summary=summarize(raw),ladderTrend=[];
 for(const b of raw){const t=b.team?.[0];if(b.type==='PvP'&&b.gameMode?.name==='Ladder'&&t?.startingTrophies!=null&&t.trophyChange!=null)ladderTrend.push({battleTime:b.battleTime,before:t.startingTrophies,change:t.trophyChange,after:t.startingTrophies+t.trophyChange});}
 ladderTrend.sort((a,b)=>a.battleTime.localeCompare(b.battleTime));
 return {...summary,playerTag:tag,totalArchived:brows.length,totalStored:total[0].count,snapshots,ladderTrend};
}
