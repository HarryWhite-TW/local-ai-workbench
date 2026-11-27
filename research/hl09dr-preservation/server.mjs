import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname } from 'node:path';
const host = '127.0.0.1:47809';
const root = new URL('./', import.meta.url);
const page = (await readFile(new URL('upstream/clearcoat-original.html', root), 'utf8'))
  .replace('../build/three.module.js', '/node_modules/three/build/three.module.js')
  .replace('./jsm/', '/node_modules/three/examples/jsm/')
  .replace('let container, stats;', 'let container, stats; let renderCount = 0, running = true;')
  .replace('renderer.setAnimationLoop( animate );', `renderer.setAnimationLoop( animate );
    function sync() { renderer.setAnimationLoop(running && !document.hidden ? animate : null); }
    document.addEventListener('visibilitychange', sync);
    window.addEventListener('message', event => {
      if (event.origin !== location.origin || event.source !== parent) return;
      if (event.data === 'pause' || event.data === 'play') { running = event.data === 'play'; sync(); }
    });
    setInterval(() => {
      const gl = renderer.getContext(), dbg = gl.getExtension('WEBGL_debug_renderer_info');
      parent.postMessage({clearcoat:true, count:renderCount, pixels:[gl.drawingBufferWidth,gl.drawingBufferHeight],
        webgl:gl.getParameter(gl.VERSION), renderer:dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)}, location.origin);
    }, 500);`)
  .replace('stats.update();', 'stats.update(); renderCount++;');
const types = {'.html':'text/html; charset=utf-8','.css':'text/css','.mjs':'text/javascript','.js':'text/javascript','.svg':'image/svg+xml','.webp':'image/webp','.jpg':'image/jpeg','.png':'image/png','.hdr':'application/octet-stream'};
const assets = /^\/(?:node_modules\/(?:@paper-design\/shaders\/dist|three\/(?:build|examples\/jsm))|upstream\/textures)\/[\w./@-]+$/;
const files = new Set(['/index.html','/lab.css','/lab.mjs','/upstream/main.css','/upstream/diamond.svg','/upstream/flowers.webp']);
const policy = "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self'; frame-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'; object-src 'none'";
createServer(async (req,res) => {
  if (req.headers.host !== host || req.method !== 'GET') {res.writeHead(403).end(); return;}
  const path = new URL(req.url, 'http://' + host).pathname;
  const file = path === '/' ? '/index.html' : path;
  const type = types[extname(file)];
  res.setHeader('Content-Security-Policy', policy);
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'no-referrer');
  if (file === '/upstream/clearcoat.html') {res.writeHead(200, {'Content-Type':types['.html']}).end(page); return;}
  const workspace = new Map([['/workspace/','app.html'],['/workspace/main.js','dist/main.js'],
    ['/workspace/main.css','dist/main.css'],['/workspace/upstream.css','dist/upstream.css']]);
  if (workspace.has(file)) {
    const resource = workspace.get(file);
    res.setHeader('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'none'; frame-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'; object-src 'none'");
    try {
      const body = await readFile(new URL('workspace-composition/' + resource, root));
      res.writeHead(200, {'Content-Type':types[extname(resource)]}).end(body);
    } catch { res.writeHead(404).end(); }
    return;
  }
  if (!type || (!files.has(file) && !assets.test(file))) {res.writeHead(404).end();return;}
  try {
    const body = await readFile(new URL('.' + file, root));
    res.writeHead(200, {'Content-Type':type}).end(body);
  } catch {res.writeHead(404).end();}
}).listen(47809, '127.0.0.1', () => console.log('Visual Lab: http://' + host + '/'));

