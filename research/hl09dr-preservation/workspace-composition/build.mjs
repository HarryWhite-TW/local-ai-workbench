import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { build } from 'esbuild';
import { execFileSync } from 'node:child_process';
const raw = await readFile('upstream/app/artifact-surface.tsx','utf8');
await mkdir('adapted',{recursive:true});
await mkdir('dist',{recursive:true});
const replacements = [
  ['"use client";','"use client";\nimport { artifact } from "../fixture";'],
  ['} from "./artifact-state";','} from "../upstream/app/artifact-state";'],
  ['initialState: emptyArtifact,','initialState: artifact,'],
  ['sandbox="allow-scripts allow-forms"','sandbox=""'],
  ['aria-label="Artifact title"','aria-label="Artifact title" readOnly'],
  ['aria-label="Artifact HTML source"','aria-label="Artifact HTML source" readOnly'],
  ['Live document','Static sample'],
];
let adapted = raw;
for(const [before,after] of replacements) {
  if(!adapted.includes(before)) throw Error('Missing upstream anchor: ' + before);
  adapted=adapted.replace(before,after);
}
await writeFile('adapted/artifact-surface.tsx',adapted);
const css=(await readFile('upstream/app/globals.css','utf8'))
  .replace('@source "../../../packages/ui/src";','@source "./packages/ui/src/components/react";\n@source "./adapted";\n@source "./main.tsx";');
await writeFile('upstream.css',css);
const result=await build({entryPoints:['main.tsx'],bundle:true,outfile:'dist/main.js',format:'esm',minify:true,metafile:true,define:{'process.env.NODE_ENV':'"production"'}});
await writeFile('dist/build-inputs.json',JSON.stringify(result.metafile,null,2));
execFileSync(process.execPath,['node_modules/@tailwindcss/cli/dist/index.mjs','-i','upstream.css','-o','dist/upstream.css','--minify'],{stdio:'inherit'});

