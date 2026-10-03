"use strict";
// A renderer, not a simulation of Workflow. Only coordinates and visual tweens live here.
class SanctuaryWorld {
  constructor(canvas, onSelect) {
    this.canvas=canvas;this.ctx=canvas.getContext("2d");this.onSelect=onSelect;
    this.rooms=[
      {id:"library",name:"LIBRARY",sub:"安靜的知識空間",x:1,y:1,w:6,d:6,color:"#c8a370"},
      {id:"research",name:"RESEARCH WING",sub:"等待可核對的研究活動",x:9,y:1,w:6,d:6,color:"#77c3dc"},
      {id:"test",name:"TEST BENCH",sub:"可辨識的測試活動",x:17,y:1,w:6,d:6,color:"#88cafa"},
      {id:"review",name:"REVIEW BAY",sub:"成果與審查證據",x:1,y:10,w:6,d:7,color:"#b6a3e2"},
      {id:"core",name:"COMMAND CORE",sub:"工作進入基地的地方",x:9,y:10,w:6,d:6,color:"#8bcdbd"},
      {id:"workshop",name:"WORKSHOP",sub:"Builder 的工作區",x:17,y:10,w:6,d:7,color:"#d9ae7d"},
    ];
    this.stations={core:[11.5,12.4],workshop:[20,14],test:[20,5.6],review:[4.7,14.5]};
    this.actor=[11.5,12.4];this.package=[11.5,12.4];this.actorTween=null;this.packageTween=null;
    this.world={pose:"uncertain",station:"core",semantic_motion:false,artifact:null,identity:{}};
    this.key="";this.selected=null;this.t=0;this.last=0;this.frames=0;this.size={scale:1,x:0,y:0};
    this.reduced=matchMedia("(prefers-reduced-motion: reduce)");
    this.resizeObserver=new ResizeObserver(()=>this.resize());this.resizeObserver.observe(canvas);
    this.handleClick=e=>{const r=canvas.getBoundingClientRect(),x=(e.clientX-r.left-this.size.x)/this.size.scale,y=(e.clientY-r.top-this.size.y)/this.size.scale;
      for(const [kind,position,visible] of [["artifact",this.package,!!this.world.artifact],["actor",this.actor,this.world.actor==="builder"]]){
        const p=this.objectPoint(kind);
        if(visible&&Math.hypot(x-p[0],y-p[1])<16){this.onSelect(this.world.station,kind);return;}
      }
      const dx=(x-670)/25.5,dy=(y-125)/13.7,wx=(dx+dy)/2,wy=(dy-dx)/2;const zone=this.rooms.find(r=>wx>=r.x&&wx<=r.x+r.w&&wy>=r.y&&wy<=r.y+r.d);if(zone)this.onSelect(zone.id,"station");};
    canvas.addEventListener("click",this.handleClick);
    this.motionChanged=()=>{if(this.reduced.matches){if(this.actorTween)this.actor=this.actorTween.path.at(-1).slice();if(this.packageTween)this.package=this.packageTween.path.at(-1).slice();this.actorTween=null;this.packageTween=null;}};
    this.reduced.addEventListener("change",this.motionChanged);
    const loop=now=>{const dt=this.last?Math.min(.08,(now-this.last)/1000):0;this.last=now;if(!this.reduced.matches)this.t+=dt;this.advance(dt);this.draw();this.frame=requestAnimationFrame(loop);};
    this.frame=requestAnimationFrame(loop);
  }
  point(x,y,z=0){return [670+(x-y)*25.5,125+(x+y)*13.7-z];}
  objectPoint(kind){return kind==="actor"?this.point(...this.actor,48):this.point(this.package[0]+(this.world.semantic_motion?.47:0),this.package[1]-(this.world.semantic_motion?.15:0),36);}
  path(from,to){const a=from[0]<9?8:16,b=to[0]<9?8:16;const path=[from.slice(),[a,from[1]]];if(a!==b||((from[1]<9)!==(to[1]<9)))path.push([a,8],[b,8]);path.push([b,to[1]],to.slice());return path.filter((p,i)=>!i||Math.hypot(p[0]-path[i-1][0],p[1]-path[i-1][1])>.01);}
  tween(from,to){if(Math.hypot(from[0]-to[0],from[1]-to[1])<.01)return null;const path=this.path(from,to),lengths=path.slice(1).map((p,i)=>Math.hypot(p[0]-path[i][0],p[1]-path[i][1]));return{path,lengths,total:lengths.reduce((a,b)=>a+b,0),distance:0};}
  interpolate(tween){let d=tween.distance;for(let i=0;i<tween.lengths.length;i++){if(d<=tween.lengths[i]||i===tween.lengths.length-1){const u=Math.min(1,d/tween.lengths[i]);return tween.path[i].map((v,k)=>v+(tween.path[i+1][k]-v)*u);}d-=tween.lengths[i];}return tween.path.at(-1).slice();}
  clearTransition(){this.actorTween=null;this.packageTween=null;this.actor=this.stations.core.slice();this.package=this.stations.core.slice();this.key="";}
  update(world){
    const first=!this.key;
    this.world=world;
    const key=JSON.stringify([world.identity,world.station,world.pose,world.artifact]);
    if(world.pose==="settled"){this.actorTween=null;this.packageTween=null;this.key=key;return;}
    if(world.pose==="accepted"){this.actorTween=null;this.packageTween=null;this.package=this.stations.review.slice();this.key=key;return;}
    if(world.pose==="uncertain"||world.pose==="blocked"||world.health!=="online"){
      this.actorTween=null;this.packageTween=null;
      if(world.artifact)this.package=(this.stations[world.station]||this.stations.core).slice();
      this.key=key;return;
    }
    if(key===this.key)return;
    this.key=key;
    const dest=this.stations[world.station]||this.stations.core;
    // Initial load/reconnect shows the current place, never replays historical travel.
    if(first){this.actorTween=null;this.packageTween=null;if(world.actor==="builder")this.actor=dest.slice();this.package=dest.slice();return;}
    if(world.semantic_motion&&world.actor==="builder"){
      if(this.reduced.matches)this.actor=dest.slice();else this.actorTween=this.tween(this.actor,dest);
      this.packageTween=null;this.package=this.actor.slice();
    }else{
      this.actorTween=null;
      if(world.artifact){if(this.reduced.matches)this.package=dest.slice();else this.packageTween=this.tween(this.package,dest);}
    }
  }
  advance(dt){
    for(const [name,key]of[["actor","actorTween"],["package","packageTween"]]){
      const tween=this[key];if(!tween)continue;
      tween.distance=Math.min(tween.total,tween.distance+dt*6.5);this[name]=this.interpolate(tween);
      if(tween.distance>=tween.total)this[key]=null;
    }
    if(this.world.semantic_motion)this.package=this.actor.slice();
  }
  focus(zone){this.selected=zone;}
  inspect(){return{pose:this.world.pose,station:this.world.station,semanticMotion:this.world.semantic_motion,activity:this.world.activity||null,actor:this.actor.slice(),artifact:this.package.slice(),actorMoving:!!this.actorTween,artifactMoving:!!this.packageTween,reducedMotion:this.reduced.matches,identity:this.world.identity,frames:this.frames,selected:this.selected,canvasSize:[this.canvas.width,this.canvas.height],targets:{actor:this.objectPoint("actor").map((v,i)=>v*this.size.scale+(i?this.size.y:this.size.x)),artifact:this.objectPoint("artifact").map((v,i)=>v*this.size.scale+(i?this.size.y:this.size.x))}};}
  resize(){const r=this.canvas.getBoundingClientRect();this.width=r.width;this.height=r.height;this.dpr=Math.min(devicePixelRatio,2);this.canvas.width=Math.round(r.width*this.dpr);this.canvas.height=Math.round(r.height*this.dpr);const scale=Math.min(r.width/1310,(r.height-20)/820);this.size={scale,x:(r.width-1310*scale)/2,y:(r.height-820*scale)/2+18};this.frames=0;this.draw();}
  poly(points,fill,stroke,width=1){const c=this.ctx;c.beginPath();points.forEach((p,i)=>i?c.lineTo(...p):c.moveTo(...p));c.closePath();if(fill){c.fillStyle=fill;c.fill();}if(stroke){c.strokeStyle=stroke;c.lineWidth=width;c.stroke();}}
  line(points,color,width=1){const c=this.ctx;c.beginPath();points.forEach((p,i)=>i?c.lineTo(...p):c.moveTo(...p));c.lineWidth=width;c.strokeStyle=color;c.lineCap="round";c.lineJoin="round";c.stroke();}
  ellipse(x,y,rx,ry,color,stroke){const c=this.ctx;c.beginPath();c.ellipse(x,y,rx,ry,0,0,Math.PI*2);if(color){c.fillStyle=color;c.fill();}if(stroke){c.strokeStyle=stroke;c.lineWidth=1;c.stroke();}}
  rect(x,y,w,h,color,r=0){const c=this.ctx;c.fillStyle=color;c.beginPath();c.roundRect(x,y,w,h,r);c.fill();}
  text(s,x,y,size,color,align="left"){const c=this.ctx;c.font=`${size}px 'Segoe UI', 'Microsoft JhengHei', sans-serif`;c.fillStyle=color;c.textAlign=align;c.fillText(s,x,y);}
  glow(x,y,r,color){const c=this.ctx,g=c.createRadialGradient(x,y,0,x,y,r);g.addColorStop(0,color);g.addColorStop(1,"transparent");c.fillStyle=g;c.fillRect(x-r,y-r,r*2,r*2);}
  floor(x,y,w,d,color,stroke){this.poly([this.point(x,y),this.point(x+w,y),this.point(x+w,y+d),this.point(x,y+d)],color,stroke);}
  box(x,y,w,d,h,top="#53616a",left="#2d3d49",right="#20333f",z=0){const a=this.point(x,y,z+h),b=this.point(x+w,y,z+h),c=this.point(x+w,y+d,z+h),e=this.point(x,y+d,z+h);this.poly([e,c,this.point(x+w,y+d,z),this.point(x,y+d,z)],left,"#06141b70");this.poly([b,c,this.point(x+w,y+d,z),this.point(x+w,y,z)],right,"#06141b70");this.poly([a,b,c,e],top,"#cfe4e715");}
  desk(x,y,w=3,d=1.2){for(const [xx,yy]of[[x+.1,y+.1],[x+w-.2,y+.1],[x+.1,y+d-.2],[x+w-.2,y+d-.2]])this.box(xx,yy,.12,.12,25,"#7a8483","#364751","#2a3841");this.box(x,y,w,d,5,"#ae8c62","#6b5946","#4f443b",25);}
  monitor(x,y,w=42,h=29,active=false,color="#8bcbf2"){const p=this.point(x,y,32);this.line([[p[0],p[1]+3],[p[0],p[1]-9]],"#647c85",3);this.poly([[p[0]-w/2,p[1]-h],[p[0]+w/2,p[1]-h+8],[p[0]+w/2,p[1]+4],[p[0]-w/2,p[1]-4]],active?"#25506a":"#1e384c",color+"a0");for(let i=0;i<4;i++)this.line([[p[0]-w/2+5,p[1]-h+7+i*4],[p[0]-w/2+5+w*(.24+(i%3)*.13),p[1]-h+10+i*4]],color+(active?"d0":"55"));if(active)this.glow(p[0],p[1]-20,43,color+"30");}
  plant(x,y,size=1){const p=this.point(x,y);this.ellipse(...p,11*size,5*size,"#0010187a");this.box(x-.2,y-.2,.4,.4,14*size,"#829185","#4a6254","#354e44");this.line([[p[0],p[1]-8],[p[0],p[1]-40*size]],"#809c68",2);for(let i=0;i<8;i++){const a=i*2.4;this.ctx.save();this.ctx.translate(p[0]+Math.cos(a)*11*size,p[1]-22*size-i*2);this.ctx.rotate(Math.sin(a)*.55);this.ellipse(0,0,9*size,4.5*size,["#4e8165","#769e73","#386554"][i%3]);this.ctx.restore();}}
  lamp(x,y){const p=this.point(x,y);this.line([p,[p[0],p[1]-62]],"#788681",3);this.ellipse(...p,8,4,"#3b4a4c");this.poly([[p[0]-11,p[1]-62],[p[0]-6,p[1]-72],[p[0]+6,p[1]-72],[p[0]+11,p[1]-62]],"#f6ce93");this.ellipse(p[0],p[1]-62,11,3,"#ffe8b9");this.glow(p[0],p[1]-62,39,"#ffc3723b");this.glow(...p,85,"#eab46721");}
  shelf(x,y,w){this.box(x,y,w,.6,61,"#82725a","#4f483b","#3c3f38");for(let row=0;row<3;row++){for(let i=0;i<w*6;i++){const p=this.point(x+.12+i*.16,y+.62,8+row*18);this.line([p,[p[0],p[1]-10-(i*3%6)]],["#d2ad7a","#8ba697","#b28766","#bdc2a1"][i%4],3);}this.line([this.point(x,y+.64,5+row*18),this.point(x+w,y+.64,5+row*18)],"#dfc092",2);}}
  chair(x,y){this.box(x-.25,y-.25,.5,.6,14,"#8c8f79","#46544b","#2e4545");const p=this.point(x,y,17);this.rect(p[0]-8,p[1]-15,17,21,"#677e73",5);}
  cup(x,y){const p=this.point(x,y,31);this.rect(p[0]-3,p[1]-7,6,7,"#daceaf",2);this.ellipse(p[0]+4,p[1]-4,2,2,null,"#daceaf");}
  background(){
    for(let i=0;i<72;i++)this.ellipse((i*173+21)%1310,(i*67)%610,1,1,"#b9d3e526");
    this.poly([[0,360],[130,320],[250,350],[405,245],[545,355],[720,275],[925,310],[1070,228],[1220,300],[1310,260],[1310,720],[0,720]],"#142736");
    for(let i=0;i<52;i++)this.rect(730+(i*47)%550,280+(i*37)%250,2,1,i%3?"#ebaf6550":"#7dcced57");
    this.ellipse(735,624,535,144,"#020c1480");
    const p=this.point(4,-2.3);this.box(1.7,-4,5,3.7,18,"#38544f","#1e3e40","#18303c",-18);this.ellipse(...p,72,34,"#2c5150","#74a99a77");
    for(let i=0;i<6;i++){const a=i*Math.PI/3;this.plant(4+Math.cos(a)*1.4,-2.3+Math.sin(a)*1.1,.72);}
    const c=this.ctx;c.beginPath();c.ellipse(p[0],p[1]-6,74,91,0,Math.PI,2*Math.PI);c.ellipse(p[0],p[1]-6,74,30,0,0,Math.PI);c.fillStyle="#8bd9e817";c.fill();c.strokeStyle="#89c8d56a";c.stroke();
    for(let i=0;i<3;i++){c.beginPath();c.ellipse(p[0],p[1]-6,16+i*23,91,0,Math.PI,Math.PI*2);c.strokeStyle="#97cce061";c.stroke();}
    this.ellipse(p[0],p[1]-42,67,18,null,"#7ac4ce60");this.ellipse(p[0],p[1]-69,47,11,null,"#7ac4ce60");this.glow(p[0],p[1]-65,48,"#66cde530");this.line([[p[0],p[1]-87],[p[0],p[1]-68]],"#bbeef3",4);
  }
  architecture(){
    this.box(-.5,-.5,25,21,27,"#263e49","#1b3540","#142934",-27);
    for(let x=0;x<24;x++)for(let y=0;y<20;y++)this.floor(x,y,1,1,(x+y)%2?"#2d4650":"#304952","#c3d5cf10");
    for(const r of this.rooms){
      this.floor(r.x,r.y,r.w,r.d,"#384d54","#92a5a141");
      for(let i=0;i<r.w;i++)for(let j=0;j<r.d;j++)this.floor(r.x+i,r.y+j,1,1,(i+j)%2?"#394f54":"#3d5155","#b3c8c713");
      const p=this.point(r.x+r.w*.5,r.y+r.d*.55);this.ctx.save();this.poly([this.point(r.x,r.y),this.point(r.x+r.w,r.y),this.point(r.x+r.w,r.y+r.d),this.point(r.x,r.y+r.d)]);this.ctx.clip();this.glow(...p,140,r.id==="test"||r.id==="research"?"#5ab2e631":"#e7b36b45");this.ctx.restore();
      if(r.id==="library"||r.id==="workshop")for(let k=.3;k<r.d;k+=.45)this.line([this.point(r.x,r.y+k),this.point(r.x+r.w,r.y+k)],"#dbc39518");
      this.box(r.x,r.y,r.w,.13,56,"#6b7875","#33494f","#294047");this.box(r.x,r.y,.13,1.6,56,"#788480","#3d5256","#2b414a");
      for(let x=.3;x<r.w;x+=1.4){const p=this.point(r.x+x,r.y+.15,36);this.rect(p[0]-9,p[1]-12,20,17,"#182f3c");this.rect(p[0]-7,p[1]-10,7,13,r.id==="library"?"#edc384ad":"#a3c4bd65");this.rect(p[0]+2,p[1]-10,7,13,"#caa97769");}
      const active=r.id===this.world.station&&this.world.pose!=="uncertain";this.line([this.point(r.x,r.y+r.d),this.point(r.x+r.w,r.y+r.d),this.point(r.x+r.w,r.y)],r.color+(active?"d0":"51"),active?2:1);
      if(this.selected===r.id)this.line([this.point(r.x,r.y),this.point(r.x,r.y+r.d),this.point(r.x+r.w,r.y+r.d),this.point(r.x+r.w,r.y),this.point(r.x,r.y)],"#d5e6bca0",2);
    }
    for(const y of[7.7,8.3])this.line([this.point(1,y),this.point(23,y)],"#c4b48a40");
    for(const x of[7.7,8.3,15.7,16.3])this.line([this.point(x,7.5),this.point(x,19)],"#91b9b346");
    for(let x=17.4;x<23;x+=.85)for(let y=2.5;y<6.8;y+=.85)this.floor(x,y,.77,.77,"#6fc6eb15","#86cee42b");
    for(let i=0;i<12;i++){const p=this.point(i*2+.3,20.08,-14);this.line([p,[p[0]+19,p[1]+10]],i%3?"#71afc063":"#d2b07c77",4);}
  }
  worker(){const p=this.point(...this.actor),walking=!!this.actorTween,working=this.world.semantic_motion&&!walking;const step=walking?Math.sin(this.t*14)*6:0,bob=walking?Math.abs(Math.sin(this.t*14))*2:Math.sin(this.t*2)*.4;const x=p[0],y=p[1]-bob;
    this.ellipse(...p,18,8,"#04101b80",working?"#a8ded584":"#667e8660");
    this.line([[x-5,y-17],[x-5+step,y-2]],"#253e4e",7);this.line([[x+5,y-17],[x+5-step,y-2]],"#253e4e",7);this.line([[x-7+step,y],[x-1+step,y]],"#a7b5b3",4);this.line([[x+3-step,y],[x+9-step,y]],"#a7b5b3",4);
    this.rect(x-12,y-39,24,24,"#d9b27c",7);this.rect(x-7,y-35,14,21,"#365163",3);this.rect(x-14,y-34,7,18,"#587481",2);
    const swing=working?Math.sin(this.t*12)*4:0;this.line([[x-11,y-34],[x-17-step*.3,y-21-swing]],"#e0be8f",6);this.line([[x+11,y-34],[x+19+step*.3,y-26-swing]],"#e0be8f",6);
    this.ellipse(x,y-50,11,12,"#ebc9a7");this.ellipse(x-1,y-56,12,7,"#253742");this.rect(x-12,y-58,25,5,"#f0bd77",2);this.ellipse(x,y-59,10,5,"#d3a15f");this.line([[x-6,y-50],[x+7,y-50]],working?"#b5f1ed":"#95bbc7",3);this.ellipse(x+4,y-50,1.4,1.4,"#edffff");
    this.rect(x-24,y+11,48,17,"#112936e0",4);this.text("BUILDER",x,y+23,8,"#e5c592","center");
  }
  furniture(){
    const t=this.t,active=this.world.semantic_motion,activity=this.world.activity;const objects=[];const add=(x,y,draw)=>objects.push({depth:x+y,draw});
    add(4,1.7,()=>this.shelf(1.6,1.5,4.8));
    add(4.5,4.6,()=>{this.desk(3.1,4,2.8,1.1);const p=this.point(4.4,4.5,32);this.poly([[p[0]-16,p[1]-4],[p[0],p[1]],[p[0]+16,p[1]-4],[p[0]+16,p[1]+7],[p[0],p[1]+11],[p[0]-16,p[1]+7]],"#e9d7b3","#b69f7a");this.line([[p[0],p[1]],[p[0],p[1]+11]],"#a48b6c");this.cup(5.2,4.4);});
    add(12,2.3,()=>{this.box(9.7,2,4.5,.85,26,"#5d7f8e","#344e5d","#253e50");for(let i=0;i<3;i++)this.monitor(10.3+i*1.45,2.3,43,29,false);});
    add(12,4.2,()=>{this.desk(10.7,3.9,3.2,1);const p=this.point(12,4.3,31);this.ellipse(...p,25,12,"#244c61","#6bafc57a");this.ellipse(p[0],p[1]-19,14,19,"#72c4dd19","#80c9d647");this.cup(13.3,4.3);});
    add(20,2.1,()=>{for(let i=0;i<3;i++){this.box(18+i*1.5,1.5,1,.75,49,"#627a86","#314f61","#233a4c");for(let j=0;j<5;j++){const p=this.point(18.45+i*1.5,2.26,9+j*7);this.line([[p[0]-7,p[1]],[p[0]+7,p[1]+5]],"#78b9d876",2);this.ellipse(p[0]-9,p[1],1.3,1.3,"#9bc8c5");}}});
    add(20,4.3,()=>{this.box(18.5,3.6,3.3,1.3,24,"#638b9a","#315569","#213e54");const a=this.point(18.8,3.75,28),b=this.point(21.6,3.75,28);this.line([a,[a[0],a[1]-51],[b[0],b[1]-51],b],"#99b7c1",5);this.line([[a[0],a[1]-47],[b[0],b[1]-47]],"#82d7f4",2);if(active&&activity==="test"&&!this.actorTween){const x=19+(Math.sin(t*2.6)+1);this.poly([this.point(x,3.75,75),this.point(x,4.7,75),this.point(x,4.7,28),this.point(x,3.75,28)],"#87ddf845","#b1e6f0a0");this.glow(...this.point(20,4.3,30),65,"#87d9f02f");}});
    add(11.5,10.8,()=>{const p=this.point(11.5,10.5);this.ellipse(...p,50,26,"#1d3943");this.rect(p[0]-50,p[1]-21,100,21,"#455e5b");this.ellipse(p[0],p[1]-21,50,25,"#839187","#d0c9a080");this.ellipse(p[0],p[1]-22,33,16,"#244d57","#9adccc");for(let i=0;i<3;i++)this.monitor(10+i*1.15,9.85,31,24,false,"#9eddd8");const rot=t*.2;this.line([[p[0]-Math.cos(rot)*19,p[1]-43],[p[0],p[1]-71],[p[0]+Math.cos(rot)*19,p[1]-43],[p[0]-Math.cos(rot)*19,p[1]-43]],"#9adcce88",1.5);});
    add(20,10.9,()=>{this.box(18.1,10.3,4.1,.6,45,"#8d785a","#5c4e3f","#41413a");for(let i=0;i<7;i++){const p=this.point(18.5+i*.48,10.93,30);this.line([[p[0],p[1]],[p[0]+5,p[1]-14]],i%2?"#c0c8bd":"#e0b076",3);}});
    add(20,12.5,()=>{this.desk(18.3,12.1,3.9,1.15);this.monitor(18.9,12.5,31,25,active&&activity!=="test","#e4c495");this.cup(21.4,12.45);const p=this.point(21.7,12.5,32);const work=active&&activity!=="test"&&!this.actorTween;const a=work?Math.sin(t*5)*.6:.3,elbow=[p[0]-Math.cos(a)*15,p[1]-29],tip=[p[0]-36,p[1]-9+Math.sin(a)*10];this.ellipse(...p,10,5,"#60777d");this.line([p,elbow,tip],"#e1b580",7);this.ellipse(...elbow,5,5,"#688994");this.line([tip,[tip[0]-3,tip[1]+9]],"#c5e0dc",3);
      if(work&&activity==="command"){for(let i=0;i<5;i++){const f=(t*3+i/5)%1;this.line([[tip[0]-6+Math.cos(i*2)*f*23,tip[1]+9+f*12],[tip[0]-7+Math.cos(i*2)*f*26,tip[1]+12+f*17]],"#ffda8990",1.5);}}
      if(work&&(activity==="file"||activity==="tool")){const q=this.point(20,12.6,43);for(let i=0;i<3;i++){const yy=q[1]-20-i*10+Math.sin(t*3+i)*3;this.rect(q[0]-10+i*8,yy,22,18,activity==="file"?"#acdace3c":"#7bb9ed3c",2);this.line([[q[0]-6+i*8,yy+6],[q[0]+7+i*8,yy+6]],"#bde1e4a0");}}
    });
    add(4.4,10.9,()=>{this.shelf(1.6,10.5,2.5);this.monitor(5.5,10.7,37,34,false,"#c5b1f2");});
    add(4.5,13.1,()=>{this.desk(3.1,12.5,3,1.2);this.cup(5.5,12.9);for(let i=0;i<3;i++)this.box(3.35,12.8,.6,.4,3,["#947794","#c6af83","#728f84"][i],"#6e6660","#49565a",31+i*3);});
    add(3.2,18.1,()=>{this.box(1.7,17.5,2.8,.85,16,"#b29a75","#75634f","#595342");this.box(1.7,17.5,2.8,.18,29,"#bba17a","#827255","#5d604d");for(let i=0;i<3;i++)this.box(1.9+i*.8,17.8,.66,.44,4,"#c0a77e","#8f7a5a","#5f6754",16);this.box(5,18.3,.75,.65,14,"#a58b6c","#6a6350","#4b5046");});
    add(20.4,16.1,()=>{this.box(18.3,15.7,1,.75,20,"#9c8763","#746448","#514a3a");this.box(19.55,15.8,.8,.65,13,"#9c8763","#746448","#514a3a");this.chair(21.4,15.9);});
    for(const [x,y]of[[2.1,5.7],[10,14.3]])add(x,y,()=>this.chair(x,y));
    for(const [x,y,size]of[[1.5,6.5,1.3],[6.5,2,1],[6.6,6.5,1.2],[9.5,6.5,1],[14.4,6.5,1.2],[22.6,6.5,1.2],[17.4,6.5,.9],[1.5,16.6,1.2],[6.5,16.5,1.2],[9.5,15.3,1.2],[14.4,15.2,1.4],[17.5,16.5,1],[22.6,16.6,1.2],[7.8,19,1.1],[16,19,1.1]])add(x,y,()=>this.plant(x,y,size));
    for(const [x,y]of[[2,5.4],[6.6,2.5],[14.4,2],[1.5,14],[13.8,15.3],[22.4,10.8],[5.8,18.7]])add(x,y,()=>this.lamp(x,y));
    if(this.world.actor==="builder")add(...this.actor,()=>this.worker());
    const bot=[8,9.3+(Math.sin(t*.13)+1)*4.2];add(...bot,()=>{const p=this.point(...bot);this.ellipse(...p,10,5,"#061724");this.rect(p[0]-9,p[1]-16,18,13,"#91a4aa",5);this.rect(p[0]-6,p[1]-12,12,5,"#263d4c",2);this.line([[p[0]-3,p[1]-10],[p[0]+3,p[1]-10]],"#afcaca",2);this.ellipse(p[0]-6,p[1]-1,3,3,"#1c3444");this.ellipse(p[0]+6,p[1]-1,3,3,"#1c3444");});
    objects.sort((a,b)=>a.depth-b.depth).forEach(o=>o.draw());
  }
  artifact(){if(!this.world.artifact)return;const kind=this.world.artifact;let z=36;const carrying=this.world.semantic_motion;let p=this.point(this.package[0]+(carrying?.47:0),this.package[1]-(carrying?.15:0),z);
    const color=kind==="accepted"?"#b1e6c1":kind==="needs_attention"?"#f0c480":kind==="candidate"||kind==="result"?"#c6b3f0":kind==="blocked"?"#dd9b82":"#f6d494";
    if(!carrying){this.ellipse(p[0],p[1]+38,27,13,"#20384a",color+"90");this.line([[p[0],p[1]+15],[p[0],p[1]+36]],color+"50",1);}
    this.glow(...p,35,color+"35");this.poly([[p[0],p[1]-13],[p[0]+13,p[1]-5],[p[0],p[1]+3],[p[0]-13,p[1]-5]],color,color);this.poly([[p[0]-13,p[1]-5],[p[0],p[1]+3],[p[0],p[1]+19],[p[0]-13,p[1]+11]],"#8e7b63",color);this.poly([[p[0],p[1]+3],[p[0]+13,p[1]-5],[p[0]+13,p[1]+11],[p[0],p[1]+19]],"#4b6669",color);
    if(kind==="accepted"){this.ellipse(p[0],p[1]-40,14,14,"#25493f",color);this.line([[p[0]-6,p[1]-40],[p[0]-1,p[1]-35],[p[0]+7,p[1]-46]],color,2.5);this.text("已接受",p[0],p[1]+66,10,color,"center");}
    else if(kind==="needs_attention"){this.ellipse(p[0],p[1]-43,15,15,"#4b4030",color);this.ellipse(p[0],p[1]-47,4,4,color);this.ctx.beginPath();this.ctx.arc(p[0],p[1]-34,7,Math.PI,0);this.ctx.fillStyle=color;this.ctx.fill();this.text("技術處理待辦",p[0],p[1]+66,10,color,"center");}
    else if(kind==="candidate"||kind==="result"){this.ellipse(p[0],p[1]-40,13,13,"#33384e",color);this.line([[p[0],p[1]-48],[p[0],p[1]-40],[p[0]+5,p[1]-36]],color,2);this.text(this.world.pose==="review"?"等待 ChatGPT 審查":"執行結果 · 尚未接受",p[0],p[1]+64,9,color,"center");}
  }
  routes(){for(const tween of[this.actorTween,this.packageTween]){if(!tween)continue;this.line(tween.path.map(p=>this.point(...p)),"#d3bc7b28",6);this.ctx.setLineDash([3,8]);this.line(tween.path.map(p=>this.point(...p)),"#e6cd9270",1.5);this.ctx.setLineDash([]);for(let i=0;i<5;i++){const p=this.point(...this.interpolate({...tween,distance:Math.max(0,tween.distance-i*.42)}));this.ellipse(...p,2.7-i*.3,1.4,"#eed6a3b0");}}}
  labels(){for(const r of this.rooms){const p=this.point(r.x+.2,r.y+.2,71);this.ctx.font="10px 'Segoe UI'";const width=Math.max(118,this.ctx.measureText(r.name).width+23);this.rect(p[0]-9,p[1]-20,width,36,"#0b1b27ed",5);this.text(r.name,p[0],p[1]-5,10,"#d8e5e1");this.text(r.sub,p[0],p[1]+7,7,r.color);}if(this.world.pose==="uncertain"){const p=this.point(11.5,12.4,85);this.rect(p[0]-36,p[1]-19,72,25,"#203344ee",5);this.text("訊號未確認",p[0],p[1]-2,9,"#bbc7cc","center");}}
  draw(){if(!this.width)return;const c=this.ctx;c.setTransform(this.dpr,0,0,this.dpr,0,0);c.clearRect(0,0,this.width,this.height);c.translate(this.size.x,this.size.y);c.scale(this.size.scale,this.size.scale);this.background();this.architecture();this.routes();this.furniture();this.artifact();for(let x=0;x<=24;x+=2)this.line([this.point(x,20),this.point(x,20,18)],"#799a97",2);this.line([this.point(0,20,18),this.point(24,20,18)],"#94b6a9",2);for(let y=0;y<=20;y+=2)this.line([this.point(24,y),this.point(24,y,18)],"#6e969e",2);this.line([this.point(24,0,18),this.point(24,20,18)],"#8bb1b5",2);this.labels();this.frames++;}
  destroy(){cancelAnimationFrame(this.frame);this.resizeObserver.disconnect();this.canvas.removeEventListener("click",this.handleClick);this.reduced.removeEventListener("change",this.motionChanged);}
}
