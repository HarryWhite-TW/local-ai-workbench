import { createRoot } from 'react-dom/client';
import { useEffect, useRef, useState } from 'react';
import {
  AssistantRuntimeProvider, AuiConfig, AuiProvider, unstable_Interactables, useAui,
  useLocalRuntime, type ChatModelAdapter, type ThreadMessageLike
} from '@assistant-ui/react';
import { Thread } from '@/components/assistant-ui/elements/thread.aui';
import { ApprovalCard, type ApprovalState } from '@/components/assistant-ui/elements/approval-card';
import { Button } from '@/components/ui/button';
import { PanelLeftIcon, FileTextIcon } from 'lucide-react';
import { ShaderMount, defaultObjectSizing, ShaderFitOptions, LiquidMetalShapes,
  liquidMetalFragmentShader, getShaderColorFromString as color } from '../node_modules/@paper-design/shaders/dist/index.js';
import { ArtifactSurface, ArtifactSurfaceProvider, useArtifactSurface } from './adapted/artifact-surface';
import { artifact } from './fixture';
import './host.css';

const messages: ThreadMessageLike[] = [
  { role:'user', content:'Review how the chat, approval and preview fit together before we change the workspace.' },
  { role:'assistant', content:'I prepared a sample workspace review. Open the workbench to read it alongside this conversation. The review focuses on composer access, approval receipts, and keeping a result tied to its discussion.' },
  { role:'user', content:'Keep the approval scoped. I want to see the result before we decide anything about the product.' },
  { role:'assistant', content:'The report is a local example using synthetic data. It does not change the product or start engineering work.' },
];

const offline: ChatModelAdapter = {
  async run() {
    return {content:[{type:'text',text:'Message received in this offline demo. You can continue reviewing the sample report or dismiss the workbench to return to the full thread.'}]};
  }
};

const composite = new URLSearchParams(location.search).get('mode') === 'composite';
const artifactTarget = {id:'workspace-review',name:'artifact' as const,messageId:'sample'};
const approvalText: Record<ApprovalState, string> = {
  request:'Waiting for a decision', running:'Approved', done:'Sample receipt recorded', denied:'Request declined'
};

function MaterialMark({enabled}: {enabled:boolean}) {
  const element = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!enabled || !element.current) return;
    const mountPoint = element.current;
    const sizing = defaultObjectSizing;
    let mount: ShaderMount | undefined;
    function sync(visible: boolean) {
      if (!visible || document.hidden) {
        mount?.dispose();
        mount = undefined;
        mountPoint.dataset.shader = 'released';
        return;
      }
      if (mount) return;
      const started = performance.now();
      try {
        mount = new ShaderMount(mountPoint,liquidMetalFragmentShader,{
          u_fit:ShaderFitOptions.contain,u_scale:.9,u_rotation:sizing.rotation,
          u_originX:sizing.originX,u_originY:sizing.originY,u_offsetX:sizing.offsetX,
          u_offsetY:sizing.offsetY,u_worldWidth:sizing.worldWidth,u_worldHeight:sizing.worldHeight,
          u_colorBack:color('#efefef'),u_colorTint:color('#fff'),u_isImage:false,
          u_shape:LiquidMetalShapes.diamond,u_repetition:2,u_softness:.1,u_shiftRed:.15,
          u_shiftBlue:.15,u_distortion:.07,u_contour:.4,u_angle:70
        },undefined,0,640,1,4096);
        mountPoint.dataset.shader = 'static';
        mountPoint.dataset.initMs = String(Math.round(performance.now()-started));
      } catch {
        mountPoint.dataset.shader = 'unavailable';
      }
    }
    let inView = false;
    const observer = new IntersectionObserver(([entry]) => {inView=entry.isIntersecting;sync(inView);});
    const visibility = () => sync(inView);
    observer.observe(mountPoint);
    document.addEventListener('visibilitychange',visibility);
    return () => {
      observer.disconnect();
      document.removeEventListener('visibilitychange',visibility);
      sync(false);
    };
  },[enabled]);
  return enabled ? <span className="material-mark" ref={element} aria-hidden="true">◇</span> : null;
}

function WorkPanel() {
  const [state,setState]=useState<ApprovalState>('request');
  return <aside id="work-panel" className="work-panel" aria-label="Work queue">
    <header><p className="panel-label">WORK QUEUE</p><h2>Workspace review</h2><p>WS-017 · Synthetic data</p></header>
    <ApprovalCard state={state} title="Review the sample"
      subtitle="One-time decision · Preview only"
      description="Review the attached layout report in this demo."
      details={[{label:'Scope',value:'Sample report'},{label:'Effect',value:'Local demo receipt'}]}
      allowOnceLabel="Approve once" denyLabel="Decline" statusLabel={approvalText[state]}
      onAllowOnce={()=>setState('done')} onDeny={()=>setState('denied')} />
    <section className="progress" aria-label="Work progress">
      <h3>Progress</h3>
      <ol><li><span>Review brief</span><span>Ready</span></li>
      <li><span>Report preview</span><span>Ready</span></li>
      <li><span>Approval</span><span aria-live="polite">{approvalText[state]}</span></li></ol>
    </section>
    {state !== 'request' && <Button variant="outline" onClick={()=>setState('request')}>Reset demo decision</Button>}
  </aside>;
}

function Experience() {
  const { active, open } = useArtifactSurface();
  const [work,setWork]=useState(true);
  const [material,setMaterial]=useState(true);
  return <div className="experience">
    <header className="demo-bar">
      {composite && <MaterialMark enabled={material}/>}
      <div className="demo-title">{composite?'Workspace review':'Artifacts example'}<small>OFFLINE DEMO</small></div>
      <div className="demo-actions">
        {composite && <>
          <Button variant="ghost" aria-expanded={work} aria-controls={work?'work-panel':undefined} onClick={()=>setWork(!work)}><PanelLeftIcon/>Work queue</Button>
          <label className="demo-toggle"><input type="checkbox" checked={material} onChange={e=>setMaterial(e.target.checked)}/> Material</label>
          <label>Model <select aria-label="Model"><option>Sol (demo)</option><option>Astra (demo)</option></select></label>
          <label>Effort <select aria-label="Effort"><option>Medium</option><option>High</option></select></label>
        </>}
        <Button variant="outline" onClick={()=>open(artifactTarget)}><FileTextIcon/>Open workbench</Button>
        <a href="/">Visual Lab</a>
      </div>
    </header>
    <main className="bg-background flex flex-1 min-h-0 overflow-hidden">
      <div hidden={!composite || !work}>{composite && <WorkPanel/>}</div>
      <section className={active?"bg-background hidden min-w-0 md:block md:w-[min(44vw,42rem)] md:shrink-0":"bg-background min-w-0 flex-1"}>
        <Thread autoFocus={false}/>
      </section>
      <ArtifactSurface />
    </main>
  </div>;
}

const config = AuiConfig({unstable_interactables:unstable_Interactables()});
function Scopes() {
  const aui = useAui();
  return <AuiProvider extends={aui} config={config}><ArtifactSurfaceProvider><Experience/></ArtifactSurfaceProvider></AuiProvider>;
}
function App() {
  const runtime = useLocalRuntime(offline,{initialMessages:messages});
  return <AssistantRuntimeProvider runtime={runtime}><Scopes/></AssistantRuntimeProvider>;
}
createRoot(document.getElementById('app')!).render(<App/>);

