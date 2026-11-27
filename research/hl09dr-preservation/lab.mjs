import {ShaderMount, defaultObjectSizing, ShaderFitOptions, liquidMetalFragmentShader, flutedGlassFragmentShader,
  getShaderColorFromString as color, LiquidMetalShapes, GlassGridShapes, GlassDistortionShapes, toProcessedLiquidMetal}
  from '/node_modules/@paper-design/shaders/dist/index.js';

const sources = {
  metal:['Paper Shaders · Liquid Metal','https://shaders.paper.design/liquid-metal'],
  glass:['Paper Shaders · Fluted Glass','https://shaders.paper.design/fluted-glass'],
  three:['Three.js r187 · Clearcoat','https://threejs.org/examples/webgl_materials_physical_clearcoat.html'],
  pair:['Paper Shaders · 並排','https://github.com/paper-design/shaders'],
  reference:['assistant-ui · Approval card / Artifacts','https://www.assistant-ui.com/elements/approval-card']
};
const get = id => document.getElementById(id);
const stage = get('stage'), metrics = get('metrics'), slider = get('slider');
let mounts = [], demo, frame, playing, selection = 0, reading, lastFrame, frameCount = 0, lastTime = performance.now();
let processed;
function image(src) { const img = new Image(); img.src = src; return img.decode().then(() => img); }
function metalImage() {
  return processed ??= toProcessedLiquidMetal('/upstream/diamond.svg').then(async ({pngBlob}) => {
    const url = URL.createObjectURL(pngBlob);
    try {return await image(url);} finally {URL.revokeObjectURL(url);}
  });
}
function sizing(fit, scale = defaultObjectSizing.scale) {
  const d = defaultObjectSizing;
  return {u_fit:ShaderFitOptions[fit],u_scale:scale,u_rotation:d.rotation,
    u_originX:d.originX,u_originY:d.originY,u_offsetX:d.offsetX,u_offsetY:d.offsetY,u_worldWidth:d.worldWidth,u_worldHeight:d.worldHeight};
}
async function paper(kind, id) {
  const metal = kind === 'metal';
  const texture = await (metal ? metalImage() : image('/upstream/flowers.webp'));
  if (id !== selection) return;
  const surface = document.createElement('div');
  surface.className = 'paper';
  const figure = document.createElement('figure');
  const caption = document.createElement('figcaption');
  caption.textContent = sources[kind][0] + ' · 0.0.82';
  figure.append(surface, caption);
  stage.append(figure);
  const uniforms = metal ? {
    ...sizing('contain',.6),u_colorBack:color('#aaaaac'),u_colorTint:color('#ffffff'),u_image:texture,u_isImage:true,
    u_shape:LiquidMetalShapes.diamond,u_repetition:2,u_softness:.1,u_shiftRed:.3,u_shiftBlue:.3,u_distortion:.07,u_contour:.4,u_angle:70
  } : {
    ...sizing('cover'),u_image:texture,u_colorBack:color('#00000000'),u_colorShadow:color('#000000'),u_colorHighlight:color('#ffffff'),
    u_size:.5,u_shadows:.25,u_highlights:.1,u_shape:GlassGridShapes.lines,u_angle:0,u_distortionShape:GlassDistortionShapes.prism,
    u_distortion:.5,u_shift:0,u_stretch:0,u_blur:0,u_edges:.25,u_marginLeft:0,u_marginRight:0,u_marginTop:0,u_marginBottom:0,u_grainMixer:0,u_grainOverlay:0
  };
  const mount = new ShaderMount(surface,metal ? liquidMetalFragmentShader : flutedGlassFragmentShader,uniforms,undefined,metal && playing ? 1 : 0,0,undefined,undefined,['u_image']);
  mounts.push({kind, mount});
}
function setMotion() {
  for (const {kind,mount} of mounts) mount.setSpeed(kind === 'metal' && playing ? Number(slider.value) : 0);
  if (frame) frame.contentWindow.postMessage(playing ? 'play' : 'pause', location.origin);
  get('pause').textContent = playing ? '暫停' : '繼續';
}
async function show(kind) {
  const id = ++selection;
  for (const {mount} of mounts) mount.dispose();
  mounts = []; frame = null; reading = null; lastFrame = null;
  stage.replaceChildren(); metrics.textContent = "";
  demo = kind; playing = true; setMotion();
  stage.className = kind === 'pair' ? 'pair' : '';
  get('name').textContent = sources[kind][0]; get('official').href = sources[kind][1];
  document.querySelectorAll('[data-demo]').forEach(btn => btn.setAttribute('aria-pressed', String(btn.dataset.demo === kind)));
  get('pause').hidden = kind === 'glass' || kind === 'reference';
  get('reset').hidden = kind === 'reference';
  get('slider-label').hidden = kind === 'three' || kind === 'reference';
  get('parameter').textContent = kind === 'glass' ? 'Distortion' : 'Speed';
  slider.min = '0'; slider.max = kind === 'glass' ? '1' : '2'; slider.value = kind === 'glass' ? '.5' : '1';
  if (kind === 'reference') {
    const copy = document.createElement('p');
    copy.textContent = '官方唯讀參考。Approval Card 的無後端版本仍使用 React 與元件樣式工具鏈。';
    const link = document.createElement('a');
    link.textContent = '官方 Artifacts 示範'; link.href = 'https://www.assistant-ui.com/examples/artifacts';
    link.target = '_blank'; link.rel = 'noopener noreferrer'; stage.append(copy,link);
  } else if (kind === 'three') {
    frame = document.createElement('iframe'); frame.title = 'Three.js Clearcoat';
    frame.setAttribute('sandbox','allow-scripts allow-same-origin');
    frame.src = '/upstream/clearcoat.html'; frame.addEventListener('load',setMotion,{once:true}); stage.append(frame);
  } else {
    try {
      for (const effect of kind === 'pair' ? ['metal','glass'] : [kind]) await paper(effect,id);
    } catch (error) { if (id === selection) stage.append('渲染失敗 · ' + error.message); }
  }
}
addEventListener('message', event => {
  if (event.origin === location.origin && event.source === frame?.contentWindow && event.data?.clearcoat) reading = event.data;
});
document.querySelectorAll('[data-demo]').forEach(button => button.onclick = () => show(button.dataset.demo));
get('pause').onclick = () => { playing = !playing; setMotion(); };
get('reset').onclick = () => show(demo);
slider.oninput = () => {
  if (demo === 'glass') mounts[0]?.mount.setUniforms({u_distortion:Number(slider.value)});
  else setMotion();
};
function monitor() { frameCount++; requestAnimationFrame(monitor); }
requestAnimationFrame(monitor);
let visibility = document.visibilityState, hiddenAt, clockAtHide, lastHidden = '';
function shaderClock() { return mounts.find(item=>item.kind==='metal')?.mount.getCurrentFrame(); }
document.addEventListener('visibilitychange', () => {
  visibility = document.visibilityState;
  if (document.hidden) {hiddenAt=performance.now(); clockAtHide=shaderClock();}
  else if (hiddenAt !== undefined) {
    lastHidden = '隱藏 '+Math.round(performance.now()-hiddenAt)+' ms · Metal 動畫時鐘前進 '+Math.round((shaderClock() ?? 0)-(clockAtHide ?? 0))+' ms';
  }
});
setInterval(() => {
  const now = performance.now(), fps = Math.round(frameCount * 1000 / (now - lastTime));
  frameCount = 0; lastTime = now;
  const reports = mounts.map(({kind,mount})=>{
    const canvas=mount.canvasElement,gl=canvas.getContext('webgl2'), info=gl?.getExtension('WEBGL_debug_renderer_info');
    return kind+' · '+canvas.width+' × '+canvas.height+' px · '+gl?.getParameter(gl.VERSION)+' · '+
      (info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : gl?.getParameter(gl.RENDERER))+' · 動畫時鐘 '+Math.round(mount.getCurrentFrame())+' ms';
  });
  if (reading) {
    reports.push(reading.webgl+' · '+reading.renderer+' · '+reading.pixels.join(' × ')+' px · 累計 '+reading.count+' 幀'+
      (lastFrame===null ? '' : ' · 最近樣本增加 '+(reading.count-lastFrame)+' 幀'));
    lastFrame = reading.count;
  }
  metrics.textContent = demo === 'reference' ? '' : [visibility+' · 頁面 RAF '+fps+' 次/秒',...reports,lastHidden].filter(Boolean).join('\n');
},1000);
const initial = new URLSearchParams(location.search).get('demo');
show(Object.hasOwn(sources, initial) ? initial : 'metal');


