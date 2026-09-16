// Keep progress modes separate; raw trophy values are never substituted across modes.
const finite=v=>typeof v==='number'&&Number.isFinite(v);
export function profileMetrics(player,ts=new Date().toISOString()){
 const rows=[];
 const seasonal=Object.entries(player.progress||{}).filter(([key])=>/^seasonal-trophy-road-\d{6}$/.test(key)).sort(([a],[b])=>b.localeCompare(a))[0];
 if(seasonal&&player.trophies>=14000&&finite(seasonal[1].trophies))rows.push({metric:'seasonal',season:seasonal[0],value:seasonal[1].trophies,label:seasonal[1].arena?.name||'赛季竞技场'});
 const p=player.currentPathOfLegendSeasonResult;
 if(p&&finite(p.trophies)&&p.trophies>0)rows.push({metric:'ranked',season:ts.slice(0,7),value:p.trophies,label:'排位分'});
 if(p&&finite(p.leagueNumber)&&p.leagueNumber>0)rows.push({metric:'league',season:ts.slice(0,7),value:p.leagueNumber,label:'联赛等级'});
 return rows.map(r=>({...r,ts}));
}
export async function archiveProgress(sql,tag,player,ts=new Date().toISOString()){
 const rows=profileMetrics(player,ts).map(r=>({...r,id:`${tag}|${ts}|${r.metric}|${r.season}`,player_tag:tag}));
 if(rows.length)await sql.query('INSERT INTO progress_snapshots (id,player_tag,ts,metric,season,value,label) SELECT id,player_tag,ts,metric,season,value,label FROM json_to_recordset($1::json) AS x(id text,player_tag text,ts text,metric text,season text,value double precision,label text) ON CONFLICT (id) DO NOTHING',[JSON.stringify(rows)]);
}
export function battleTimestamp(t){if(!t)return null;const m=/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(?:\.(\d+))?Z?$/.exec(t);if(!m)return null;const iso=`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}.${(m[7]||'000').slice(0,3).padEnd(3,'0')}Z`;return Number.isFinite(Date.parse(iso))?iso:null;}
export function assembleTrends(battles,snapshots,progress){
 const series={road:[],seasonal:[],ranked:[],league:[]};
 const push=(key,time,value,season='',source='对战记录',label='')=>{const t=Date.parse(time);if(Number.isFinite(t)&&finite(value))series[key].push({time:new Date(t).toISOString(),value,season,source,label});};
 for(const s of snapshots)push('road',s.ts,s.trophies,'','采集快照');
 for(const s of progress)if(series[s.metric])push(s.metric,s.ts,s.value,s.season,'采集快照',s.label);
 for(const b of battles){const ts=battleTimestamp(b.battle_time);if(!ts)continue;const arena=b.arena||{};let key=null,season='';
  if(/^SeasonalArenas_\d{6}_/.test(arena.rawName||'')){key='seasonal';season='seasonal-trophy-road-'+arena.rawName.match(/\d{6}/)[0];}
  else if(b.type==='pathOfLegend'){key='ranked';season=ts.slice(0,7);}
  else if(b.type==='PvP'&&b.mode==='Ladder')key='road';
  if(!key)continue;
  if(key==='ranked'&&finite(b.league)&&b.league>0)push('league',ts,b.league,season,'对战记录','联赛等级');
  if(!finite(b.before))continue;
  // Two observed values for this battle, without inventing an earlier timestamp.
  push(key,ts,b.before,season,'对战前',arena.name||'');
  if(finite(b.change))push(key,ts,b.before+b.change,season,'对战后',arena.name||'');
 }
 for(const key of Object.keys(series)){
  const seen=new Set();series[key]=series[key].sort((a,b)=>a.time.localeCompare(b.time)).filter(p=>{const k=p.time+'|'+p.value+'|'+p.season;if(seen.has(k))return false;seen.add(k);return true;});
 }
 return series;
}
export async function trends(sql,tag){
 const [battles,snapshots,progress]=await Promise.all([
 sql.query(`SELECT battle_time,type,mode,raw::jsonb->'arena' AS arena,(raw::jsonb->'team'->0->>'startingTrophies')::double precision AS before,(raw::jsonb->'team'->0->>'trophyChange')::double precision AS change,(raw::jsonb->>'leagueNumber')::double precision AS league FROM battles WHERE player_tag=$1 AND (type='PvP' OR type='pathOfLegend' OR raw::jsonb->'arena'->>'rawName' LIKE 'SeasonalArenas_%') ORDER BY battle_time,id`,[tag]),
 sql.query('SELECT ts,trophies FROM snapshots WHERE player_tag=$1 ORDER BY ts,id',[tag]),
 sql.query('SELECT ts,metric,season,value,label FROM progress_snapshots WHERE player_tag=$1 ORDER BY ts,id',[tag])]);
 return {playerTag:tag,series:assembleTrends(battles,snapshots,progress)};
}
