"use strict";
const $=id=>document.getElementById(id);
const names={1:"浏览",2:"收藏",3:"加购",4:"购买"};
const cohorts={all:"全部用户",low_activity:"低活跃",high_activity:"高活跃",new_observed:"新近观测",high_value_proxy:"高价值代理",potential_proxy:"潜力代理",at_risk_proxy:"近期风险代理",dormant_proxy:"沉睡代理"};
const colors={1:"#4384a1",2:"#8a6aa3",3:"#c09a36",4:"#d47b3e"};
const num=v=>Number(v||0).toLocaleString("zh-CN");
const pct=v=>v===null||v===undefined?"—":(100*v).toFixed(2)+"%";
const esc=v=>String(v).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let current=null,options=null,requestNumber=0;
/** 读取尚未应用的全局筛选。Returns: URLSearchParams，供统计请求使用。 */
function query(){return new URLSearchParams(Object.fromEntries(["start","end","cohort","category","item"].map(k=>[k,$(k).value])));}
/** 创建带固定viewBox的独立SVG。Args: content图形标记；height视图高度。Returns: SVG字符串。 */
function svg(content,height=280){return `<svg viewBox="0 0 560 ${height}" role="img">${content}</svg>`;}
/** 显示缺乏支持量的状态。Args: id为目标容器；不把不可估计值绘成零。 */
function empty(id){$(id).innerHTML="<p class='definition'>当前筛选没有足够的观测记录。</p>";}
/** 绘制带精确数值的横条图。Args: id容器；rows数据；label标签列；value数值列；formatter显示函数。 */
function bars(id,rows,label,value,formatter=num){
 if(!rows.length){empty(id);return;}
 const max=Math.max(...rows.map(r=>Number(r[value]||0)),1e-12),height=rows.length*25+20;
 $(id).innerHTML=svg(rows.map((r,i)=>{const y=i*25+14,w=320*Number(r[value]||0)/max;return `<text x="0" y="${y+4}">${esc(r[label])}</text><rect x="105" y="${y-10}" width="${w}" height="16" rx="2" fill="#d08a4d"/><text x="${112+w}" y="${y+3}">${formatter(r[value])}</text>`;}).join(""),height);
}
/** 绘制日期或排名趋势。Args: id容器；labels横轴；series曲线；percent是否比例。 */
function linePlot(id,labels,series,percent=false){
 if(!labels.length){empty(id);return;}
 const finite=series.flatMap(s=>s.values).filter(v=>v!==null&&Number.isFinite(v)),max=Math.max(...finite,1e-8),sx=i=>55+i*465/Math.max(labels.length-1,1),sy=v=>225-180*v/max;
 let text="";
 for(let i=0;i<5;i++){const value=max*i/4,y=sy(value);text+=`<line x1="55" y1="${y}" x2="525" y2="${y}" stroke="#e1e8ed"/><text x="48" y="${y+3}" text-anchor="end">${percent?pct(value):num(Math.round(value))}</text>`;}
 labels.forEach((l,i)=>{if(i%Math.max(1,Math.ceil(labels.length/7))===0||i===labels.length-1)text+=`<text x="${sx(i)}" y="245" text-anchor="middle">${esc(l)}</text>`;});
 series.forEach((s,j)=>{const points=s.values.map((v,i)=>v===null?null:`${sx(i)},${sy(v)}`).filter(Boolean).join(" ");text+=`<polyline points="${points}" fill="none" stroke="${s.color}" stroke-width="2"/><text x="${60+j*110}" y="20" style="fill:${s.color}">${esc(s.name)}</text>`;});
 $(id).innerHTML=svg(text,265);
}
/** 绘制7×24热力图。Args: id容器；values小时值；percent比例开关。空分母另色显示。 */
function heatmap(id,values,percent=false){
 const max=Math.max(...values.map(r=>r.value||0),1e-12);let body="";
 ["周一","周二","周三","周四","周五","周六","周日"].forEach((name,i)=>body+=`<text x="0" y="${45+i*25}">${name}</text>`);
 for(let h=0;h<24;h++)body+=`<text x="${51+h*20}" y="18" text-anchor="middle">${h}</text>`;
 for(let w=0;w<7;w++)for(let h=0;h<24;h++){const r=values.find(x=>x.weekday===w&&x.hour===h),v=r?r.value:null,t=v===null?0:Math.min(1,v/max),fill=v===null?"#edf1f3":`rgb(${245-25*t},${239-120*t},${229-178*t})`;body+=`<rect x="${42+h*20}" y="${28+w*25}" width="19" height="24" fill="${fill}"><title>${w+1} / ${h}时：${v===null?"不可用":percent?pct(v):Number(v).toFixed(2)}</title></rect>`;}
 body+=`<text x="42" y="229">浅色至深色：${percent?"购买用户覆盖率":"日均记录数"}，最大 ${percent?pct(max):num(Math.round(max))}；空白为无分母</text>`;
 $(id).innerHTML=svg(body,245);
}
/** 按行为切换时段量，使用已返回的日期分母；购买覆盖保持独立口径。 */
function renderHeat(){
 const b=$("heatBehavior").value,totals=new Map();
 current.heatmap.filter(r=>b==="all"||String(r.behavior_type)===b).forEach(r=>{const key=r.weekday+":"+r.hour;totals.set(key,(totals.get(key)||0)+r.records);});
 const rows=[...totals].map(([key,value])=>{const [weekday,hour]=key.split(":").map(Number);return {weekday,hour,value:value/(current.weekday_days[weekday]||1)};});
 heatmap("heat",rows);heatmap("hourRate",current.hour_coverage.map(r=>({...r,value:r.users?r.buying_users/r.users:null})),true);
}
/** 渲染可下钻排名。Args: id容器；rows排序结果；key为类目或商品ID字段。 */
function rankTable(id,rows,key){
 $(id).innerHTML="<table><thead><tr><th>"+(key==="category_id"?"类目":"商品")+"</th><th>记录数</th><th>浏览组合</th><th>购买覆盖</th></tr></thead><tbody>"+rows.map(r=>`<tr data-${key==="category_id"?"category":"item"}="${esc(r[key])}"><td>${esc(r[key])}</td><td>${num(r.records)}</td><td>${num(r.viewed_pairs)}</td><td>${pct(r.purchase_coverage)}</td></tr>`).join("")+"</tbody></table>";
}
/** 在当前全局结果内切换记录量和购买覆盖排名，覆盖排名遵守支持量门槛。 */
function renderRanks(){
 const metric=$("rankMetric").value,rows=current.categories.filter(r=>metric!=="purchase_coverage"||r.viewed_pairs>=200).sort((a,b)=>(b[metric]||0)-(a[metric]||0));
 rankTable("categoryRank",rows.slice(0,20),"category_id");rankTable("itemRank",current[metric==="records"?"items_volume":"items_conversion"],"item_id");
}
/** 用全量支持商品的中位阈值绘制四象限，展示最多1500个商品并保留ID下钻。 */
function scatter(){
 const rows=current.item_quadrants;if(!rows.length){empty("quadrants");return;}
 const max=Math.max(...rows.map(r=>Math.log10(1+r.pv_records))),sx=v=>50+470*Math.log10(1+v)/Math.max(max,1),sy=v=>235-200*v;
 const thresholds=current.quadrant_thresholds||{pv_records:0,purchase_coverage:0};
 let text=`<line x1="50" y1="235" x2="525" y2="235" stroke="#b8cbd6"/><line x1="50" y1="35" x2="50" y2="235" stroke="#b8cbd6"/><text x="50" y="18">购买覆盖（0–100%）</text><text x="240" y="265">浏览记录量（对数坐标）</text>`;
 text+=`<line x1="${sx(thresholds.pv_records)}" x2="${sx(thresholds.pv_records)}" y1="30" y2="235" stroke="#aabac5" stroke-dasharray="4"/><line x1="50" x2="525" y1="${sy(thresholds.purchase_coverage)}" y2="${sy(thresholds.purchase_coverage)}" stroke="#aabac5" stroke-dasharray="4"/>`;
 rows.forEach(r=>text+=`<circle data-item="${esc(r.item_id)}" cx="${sx(r.pv_records)}" cy="${sy(r.purchase_coverage||0)}" r="3" fill="#c97e43" opacity=".45"><title>商品${esc(r.item_id)}：浏览${num(r.pv_records)}，浏览组合${num(r.viewed_pairs)}，购买覆盖${pct(r.purchase_coverage)}</title></circle>`);
 $("quadrants").innerHTML=svg(text,280);
}
/** 按浏览量排序全部类目，分别累计浏览和购买贡献；无购买分母时保留不可用。 */
function renderTail(){
 const rows=[...current.categories].sort((a,b)=>b.pv_records-a.pv_records),totalPV=rows.reduce((a,r)=>a+r.pv_records,0),totalBuy=rows.reduce((a,r)=>a+(r.buy_records||0),0);let p=0,b=0;
 const pv=[],buy=[],labels=[];rows.forEach((r,i)=>{p+=r.pv_records;b+=(r.buy_records||0);pv.push(totalPV?p/totalPV:0);buy.push(totalBuy?b/totalBuy:null);labels.push(String(i+1));});
 linePlot("tail",labels,[{name:"浏览记录",values:pv,color:colors[1]},{name:"购买记录",values:buy,color:colors[4]}],true);
}
/** 独立展示用户商品对或用户的未来7天目标，未成熟时不生成零购买率。 */
function renderForward(){
 const f=current.forward;$("forward").replaceChildren();
 if(!f.available){$("forwardNote").textContent="所选历史截点的未来7天尚未完整观测，结果不可用。可将结束日期调整至2025-12-11或之前再探索。";return;}
 $("forwardNote").textContent=`截点 ${f.anchor.slice(0,10)}，最近7天交互候选 ${num(f.rows)} 对，未来购买 ${num(f.positives)} 对，正例率 ${pct(f.rows?f.positives/f.rows:null)}。横轴次数按当前所选历史窗口统计。`;
 const userTarget=$("forwardTarget").value==="user";
 const displayed=userTarget?f.user_bins:f.bins;
 if(userTarget)$("forwardNote").textContent=`用户级补充：历史筛选用户 ${num(f.user_balance.rows)} 人，未来任意商品购买 ${num(f.user_balance.positives)} 人；这不是同商品候选标签。`;
 const order=["0","1","2-4","5-9","10-19","20+"];
 for(const behavior of ["pv","cart","fav"]){const id="forward_"+behavior,box=document.createElement("article");box.innerHTML=`<h3>${({pv:"浏览",cart:"加购",fav:"收藏"})[behavior]}深度与未来购买率</h3><div id="${id}"></div>`;$("forward").append(box);const data=displayed.filter(r=>r.behavior===behavior).sort((a,b)=>order.indexOf(a.bin)-order.indexOf(b.bin));bars(id,data,"bin","purchase_rate",pct);}
}
/** 用同一查询响应更新全部模块。Args: data为后端完整全局筛选结果。 */
function render(data){
 current=data;const m=data.overview;
 const cards=[["有效日志记录",num(m.records)],["不同四元组",num(m.four_tuple_keys)],["用户",num(m.users)],["商品",num(m.items)],["类目",num(m.categories)],["同期购买用户占比",pct(m.users?m.buying_users/m.users:null)],["人均交互商品组合",m.users?(data.total_pairs/m.users).toFixed(2):"—"],["活跃用户日平均观测小时桶",m.active_user_days?(m.observed_user_hours/m.active_user_days).toFixed(2):"—"]];
 $("cards").innerHTML=cards.map(([label,value])=>`<div class="card"><span>${label}</span><strong>${value}</strong></div>`).join("");
 $("scope").textContent=`当前统计：${data.filters.start} 至 ${data.filters.end}；${cohorts[data.filters.cohort]}；类目 ${data.filters.category||"全部"}${data.filters.item?"；商品 "+data.filters.item:""}。分层先按日期窗口内全类目历史确定。`;
 $("drill").hidden=!data.filters.item;if(data.filters.item)$("drill").innerHTML=`商品 ${esc(data.filters.item)} 明细 <button id="clearItem" class="secondary">返回全部商品</button>`;
 bars("behavior",data.behaviors.map(r=>({...r,label:names[r.behavior_type]})),"label","records");
 bars("activity",data.user_distribution.map(r=>({...r,rate:r.users?r.buying_users/r.users:null})),"bin","rate",pct);
 const dates=[];for(let day=new Date(data.filters.start+"T00:00:00Z");day<=new Date(data.filters.end+"T00:00:00Z");day.setUTCDate(day.getUTCDate()+1))dates.push(day.toISOString().slice(0,10));
 linePlot("daily",dates.map(d=>d.slice(5)),[1,3,2,4].map(b=>({name:names[b],color:colors[b],values:dates.map(d=>data.daily.find(r=>r.day===d&&r.behavior_type===b)?.records||0)})));
 linePlot("dailyRate",dates.map(d=>d.slice(5)),[{name:"购买用户/活跃用户",color:colors[4],values:dates.map(d=>{const r=data.daily_coverage.find(v=>v.day===d);return r&&r.users?r.buying_users/r.users:null;})}],true);
 renderHeat();renderRanks();renderTail();scatter();
 const activity=data.activity_exact,maxX=Math.max(...activity.map(r=>Math.log10(r.records)),1),maxY=Math.max(...activity.map(r=>r.users),1);
 let logChart='<line x1="50" y1="230" x2="525" y2="230" stroke="#becdd5"/>';
 activity.forEach(r=>{logChart+=`<circle cx="${50+470*Math.log10(r.records)/maxX}" cy="${230-190*r.users/maxY}" r="2" fill="#4384a1"><title>记录数${num(r.records)}：${num(r.users)}人</title></circle>`;});
 for(let i=0;i<=Math.floor(maxX);i++)logChart+=`<text x="${50+470*i/maxX}" y="250">${num(10**i)}</text>`;
 logChart+='<text x="50" y="20">用户数</text><text x="230" y="275">日志记录数（对数坐标）</text>';
 $("activityLog").innerHTML=svg(logChart,290);
 const buckets=new Map();data.purchase_distribution.forEach(r=>{const b=r.buy_records===0?"0":r.buy_records===1?"1":r.buy_records<5?"2-4":r.buy_records<10?"5-9":"10+";buckets.set(b,(buckets.get(b)||0)+r.users);});bars("purchases",[...buckets].map(([bin,users])=>({bin,users})),"bin","users");
 $("preferences").innerHTML="<table><tr><th>活跃层</th><th>类目</th><th>四元组数</th></tr>"+data.preferences.map(r=>`<tr><td>${esc(r.activity)}</td><td>${esc(r.category_id)}</td><td>${num(r.keys)}</td></tr>`).join("")+"</table>";
 const stages=["成熟浏览组合","后续跨小时加购","再跨小时收藏","再跨小时购买"];bars("funnel",data.funnel.stage_counts.map((count,i)=>({label:stages[i],count})),"label","count");
 $("pathNote").textContent=`漏斗分母为具有完整7天随访的浏览组合。直接浏览后跨小时购买 ${num(data.funnel.pv_to_buy_strict)} 对；允许同小时的候选购买路径 ${num(data.funnel.pv_to_buy_same_hour_candidates)} 对。收藏不是购买的必经步骤。转移采用筛选记录中间隔不超过24小时的下一个观测活跃小时，多标签行和可能大于100%，不解释为退出概率。`;
 $("transitions").innerHTML="<table><tr><th>当前/下一小时</th>"+[1,3,2,4].map(i=>"<th>"+names[i]+"</th>").join("")+"</tr>"+[1,3,2,4].map(i=>"<tr><td>"+names[i]+"</td>"+[1,3,2,4].map(j=>"<td>"+pct(data.transitions.find(r=>r.current===i&&r.following===j)?.rate)+"</td>").join("")+"</tr>").join("")+"</table>";renderForward();
}
/** 请求完整重算；响应序号阻止旧请求覆盖新结果，失败时保留明确的未更新状态。 */
async function apply(){
 const token=++requestNumber;$("status").className="";$("status").textContent="正在按三个全局条件重新计算所有统计…";$("controls").querySelector("button").disabled=true;
 try{const response=await fetch("/api/data?"+query()),data=await response.json();if(token!==requestNumber)return;if(!response.ok)throw new Error(data.error||"数据未更新");render(data);$("status").textContent=`已更新。当前记录 ${num(data.overview.records)} 条；所有核心模块使用同一筛选。`;}
 catch(error){$("status").className="error";$("status").textContent="统计未更新："+error.message;}
 finally{if(token===requestNumber)$("controls").querySelector("button").disabled=false;}
}
$("controls").addEventListener("submit",event=>{event.preventDefault();$("item").value="";apply();});
$("reset").addEventListener("click",()=>{$("start").value=options.start;$("end").value=options.end;$("cohort").value="all";$("category").value="";$("item").value="";apply();});
$("forwardTarget").addEventListener("change",()=>current&&renderForward());
$("heatBehavior").addEventListener("change",()=>current&&renderHeat());$("rankMetric").addEventListener("change",()=>current&&renderRanks());
document.addEventListener("click",event=>{const category=event.target.closest("[data-category]"),item=event.target.closest("[data-item]");if(category){$("category").value=category.dataset.category;$("item").value="";apply();}if(item){$("item").value=item.dataset.item;apply();}if(event.target.id==="clearItem"){$("item").value="";apply();}});
$("download").addEventListener("click",()=>{if(!current)return;const p=new URLSearchParams(current.filters);p.set("table",$("exportTable").value);const a=document.createElement("a");a.href="/api/export?"+p;a.download="eda_"+$("exportTable").value+".csv";a.click();});
(async()=>{try{options=await(await fetch("/api/options")).json();$("start").value=options.start;$("end").value=options.end;for(const id of ["start","end"]){$(id).min=options.start;$(id).max=options.end;}$("categories").innerHTML=options.categories.map(v=>`<option value="${esc(v)}"></option>`).join("");await apply();}catch(error){$("status").className="error";$("status").textContent="请通过本地看板服务打开此页面。";}})();
