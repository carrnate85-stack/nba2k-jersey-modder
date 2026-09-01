import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Aperture, Archive, Blend, Box, ChevronDown, ChevronRight, CircleOff, Download,
  Copy, FileImage, FileText, FolderOpen, Grid3X3, Image as ImageIcon, Layers3, Palette, Pipette,
  Play, Plus, RefreshCw, Save, Scissors, Search, Settings2, Shirt, SlidersHorizontal,
  Sparkles, Upload, WandSparkles, X,
} from 'lucide-react';
import type { AppInfo, JsonObject, ProjectSummary } from '../shared';

type PageKey = 'generator' | 'logo' | 'trim' | 'paths' | 'number' | 'tweak' | 'texture' | 'iff' | 'rdat' | 'template';
const PAGE_META: Record<PageKey, { label: string; icon: typeof Shirt; description: string }> = {
  generator: { label: 'Generator', icon: Shirt, description: 'Build jersey and shorts textures from reusable template zones.' },
  logo: { label: 'Logo Creator', icon: Aperture, description: 'Select, clean, stage, and place logos from a reference image.' },
  trim: { label: 'Trim Creator', icon: Scissors, description: 'Create straight trim strips from uniform reference photos.' },
  paths: { label: 'Trim Path Lab', icon: Blend, description: 'Draw curved and mirrored trim paths directly over the uniform.' },
  number: { label: 'Number Editor', icon: Sparkles, description: 'Load game number sheets and recolor fill and outline cleanly.' },
  tweak: { label: 'Tweak Editor', icon: SlidersHorizontal, description: 'Edit front number position and size inside tweak IFF files.' },
  texture: { label: 'Texture Creator', icon: Layers3, description: 'Create color, region, and normal textures from the current design.' },
  iff: { label: 'IFF Textures', icon: Archive, description: 'Inspect, export, replace, and repack DDS and TXTR resources.' },
  rdat: { label: 'RDAT Editor', icon: FileText, description: 'Open and edit RDAT text directly or from an IFF container.' },
  template: { label: 'Template Editor', icon: Grid3X3, description: 'Maintain master images and color-coded template zones.' },
};

const imageRows = [
  ['jersey_background_image', 'Background jersey image'],
  ['left_panel_image', 'Left side panel'], ['right_panel_image', 'Right side panel'],
  ['shorts_left_panel_image', 'Left shorts panel'], ['shorts_right_panel_image', 'Right shorts panel'],
  ['collar_trim_image', 'Collar trim'], ['left_arm_hole_trim_image', 'Left armhole trim'],
  ['right_arm_hole_trim_image', 'Right armhole trim'], ['waistband_image', 'Waistband image'],
] as const;
const jerseyColors = [
  ['front_color', 'Front base'], ['back_color', 'Back base'], ['collar_background_color', 'Collar background'],
  ['left_panel_color', 'Left side panel'], ['right_panel_color', 'Right side panel'],
  ['collar_trim_color', 'Collar trim'], ['left_arm_hole_trim_color', 'Left armhole'], ['right_arm_hole_trim_color', 'Right armhole'],
] as const;
const logoTypes = [
  ['Front Wordmark', 'front_wordmark'], ['Center Chest Logo', 'front_center_chest_logo'],
  ['Left Chest Logo', 'front_left_chest_logo'], ['Right Chest Logo', 'front_right_chest_logo'],
  ['Wrap Image', 'wrap_across_front_back_logo'], ['Back Neck Logo', 'back_neck_logo'],
  ['Back Center Logo', 'back_center_logo'], ['Belt Buckle Logo', 'shorts_belt_buckle_logo'],
] as const;
const trimTypes = [
  ['Collar Trim', 'collar_trim_image'], ['Left Arm Hole Trim', 'left_arm_hole_trim_image'],
  ['Right Arm Hole Trim', 'right_arm_hole_trim_image'], ['Waistband', 'waistband_image'],
  ['Trim Path', 'trim_path_pattern'],
] as const;
const shortsColors = [
  ['left_panel_color', 'Left shorts panel'], ['right_panel_color', 'Right shorts panel'],
  ['waistband_color', 'Waistband'],
] as const;

function clone<T>(value: T): T { return structuredClone(value); }
function filename(path?: string | null): string { return path ? path.replaceAll('\\', '/').split('/').pop() || path : 'None selected'; }
function projectName(path?: string | null): string { return filename(path).replace('.nba2kproject.json', '').replace('.json', '') || 'Untitled project'; }

export function App() {
  const [info, setInfo] = useState<AppInfo | null>(null);
  const [recent, setRecent] = useState<ProjectSummary[]>([]);
  const [project, setProject] = useState<JsonObject | null>(null);
  const [projectPath, setProjectPath] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [page, setPage] = useState<PageKey>('generator');
  const [status, setStatus] = useState('Starting workspace...');
  const [startup, setStartup] = useState(true);
  const [newName, setNewName] = useState('');
  const [busy, setBusy] = useState(false);
  const [icon, setIcon] = useState('');

  useEffect(() => {
    Promise.all([window.jersey.appInfo(), window.jersey.listProjects()]).then(async ([appInfo, projects]) => {
      setInfo(appInfo); setRecent(projects); setStatus('Python engine ready.');
      try { setIcon(await window.jersey.fileDataUrl(`${appInfo.root}\\wpf\\JerseyModder.Wpf\\Assets\\app-icon.png`)); } catch { /* icon has CSS fallback */ }
    }).catch((error) => setStatus(error.message));
    const removeProject = window.jersey.onProjectUpdate((payload) => { setProject(payload); setDirty(true); });
    const removeStatus = window.jersey.onStatus(setStatus);
    return () => { removeProject(); removeStatus(); };
  }, []);

  const openLoaded = useCallback((loaded: { path: string; project: JsonObject }) => {
    loaded.project.generator.garment = 'Jersey';
    setProject(loaded.project); setProjectPath(loaded.path); setDirty(false); setPage('generator'); setStartup(false); setStatus(`Opened ${projectName(loaded.path)}.`);
  }, []);

  const create = async () => {
    if (!newName.trim()) return; setBusy(true);
    try { openLoaded(await window.jersey.createProject(newName)); setRecent(await window.jersey.listProjects()); setNewName(''); }
    catch (error: any) { setStatus(error.message); } finally { setBusy(false); }
  };
  const chooseOpen = async () => { const loaded = await window.jersey.chooseProject(); if (loaded) openLoaded(loaded); };
  const save = async () => { if (!project || !projectPath) return; setBusy(true); try { await window.jersey.saveProject(projectPath, project); setDirty(false); setStatus(`Saved ${projectName(projectPath)}.`); } catch (error: any) { setStatus(error.message); } finally { setBusy(false); } };
  const updateProject = useCallback((updater: (next: JsonObject) => void) => { setProject((current) => { if (!current) return current; const next = clone(current); updater(next); return next; }); setDirty(true); }, []);
  const setScope = (key: 'garment' | 'template', value: string) => updateProject((next) => {
    if (key === 'garment') { next.generator.garment = value; next.generator[value === 'Shorts' ? 'shortsTemplate' : 'jerseyCut'] = value === 'Shorts' ? 'Retro shorts' : 'Retro U'; }
    else next.generator[next.generator.garment === 'Shorts' ? 'shortsTemplate' : 'jerseyCut'] = value;
  });
  const exportPackage = async () => { if (!project) return; const folder = await window.jersey.chooseFolder(); if (!folder) return; setBusy(true); try { const result = await window.jersey.engine('export_package', { project, folder }); setStatus(`Package created: ${result.path}`); } catch (error: any) { setStatus(error.message); } finally { setBusy(false); } };
  const blender = async () => { if (!project) return; setBusy(true); try { await window.jersey.openBlender(project); setStatus('Blender preview opened.'); } catch (error: any) { setStatus(error.message); } finally { setBusy(false); } };

  const scopeTemplate = project?.generator.garment === 'Shorts' ? project?.generator.shortsTemplate : project?.generator.jerseyCut;
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark">{icon ? <img src={icon} /> : <Shirt />}</div><div><span>NBA 2K</span><strong>Jersey Modder</strong><small>Uniform workspace</small></div></div>
      <nav className="navigation">
        {(Object.keys(PAGE_META) as PageKey[]).slice(0, 7).map((key) => <Nav key={key} active={page === key} item={PAGE_META[key]} onClick={() => setPage(key)} />)}
      </nav>
      <div className="advanced"><div className="advanced-title"><Settings2 size={15}/> Advanced</div>{(['iff', 'rdat', 'template'] as PageKey[]).map((key) => <Nav key={key} compact active={page === key} item={PAGE_META[key]} onClick={() => setPage(key)} />)}<small>Electron + Python engine</small></div>
    </aside>
    <main className="workspace">
      <header className="topbar">
        <div className="project-title"><strong>{projectName(projectPath)}</strong><span>{dirty ? 'Unsaved changes' : projectPath ? 'Saved' : 'No project open'}</span></div>
        <label className="top-field"><span>Garment</span><select disabled={!project} value={project?.generator.garment || 'Jersey'} onChange={(event) => setScope('garment', event.target.value)}><option>Jersey</option><option>Shorts</option></select></label>
        <label className="top-field template-field"><span>Template</span><select disabled={!project} value={scopeTemplate || 'Retro U'} onChange={(event) => setScope('template', event.target.value)}>{project?.generator.garment === 'Shorts' ? <><option>Retro shorts</option><option>Classic shorts</option><option>Modern shorts</option></> : <option>Retro U</option>}</select></label>
        <div className="top-actions"><IconButton title="New project" onClick={() => setStartup(true)}><Plus/></IconButton><IconButton title="Open project" onClick={chooseOpen}><FolderOpen/></IconButton><IconButton title="Save project" disabled={!project || !dirty} onClick={save}><Save/></IconButton><button className="command" disabled={!project || busy} onClick={exportPackage}><Download/>Export Package</button><button className="primary command" disabled={!project || busy} onClick={blender}><Box/>Blender Preview</button></div>
      </header>
      <section className="page-host">
        {!project ? <EmptyWorkspace onOpen={() => setStartup(true)} /> : <Page page={page} project={project} projectPath={projectPath!} update={updateProject} setPage={setPage} status={setStatus} />}
      </section>
      <footer><span className={busy ? 'working' : ''}>{busy ? 'Working... ' : ''}{status}</span><span>v{info?.version || '1.1.0'} Electron</span></footer>
    </main>
    {startup && <Startup info={info} recent={recent} newName={newName} setNewName={setNewName} busy={busy} create={create} open={chooseOpen} openRecent={async (path: string) => openLoaded(await window.jersey.loadProject(path))} close={project ? () => setStartup(false) : undefined} icon={icon} />}
  </div>;
}

function Nav({ active, item, onClick, compact }: { active: boolean; item: { label: string; icon: typeof Shirt }; onClick: () => void; compact?: boolean }) { const Icon = item.icon; return <button className={`nav-item ${active ? 'active' : ''} ${compact ? 'compact' : ''}`} onClick={onClick}><Icon/><span>{item.label}</span></button>; }
function IconButton({ title, onClick, disabled, children }: any) { return <button className="icon-button" title={title} aria-label={title} disabled={disabled} onClick={onClick}>{children}</button>; }
function Page({ page, project, projectPath, update, setPage, status }: any) {
  const common = { project, projectPath, update, status };
  if (page === 'generator') return <Generator {...common} setPage={setPage}/>;
  if (page === 'logo') return <Creator kind="logo" {...common} setPage={setPage}/>;
  if (page === 'trim') return <Creator kind="trim" {...common} setPage={setPage}/>;
  if (page === 'paths') return <TrimPaths {...common}/>;
  if (page === 'number') return <NumberEditor status={status}/>;
  if (page === 'tweak') return <TweakEditor status={status}/>;
  if (page === 'texture') return <TextureCreator project={project} status={status}/>;
  if (page === 'iff') return <IffEditor status={status}/>;
  if (page === 'rdat') return <RdatEditor status={status}/>;
  return <TemplateEditor status={status}/>;
}

function PageHeader({ page, actions }: { page: PageKey; actions?: any }) { const meta = PAGE_META[page]; return <div className="page-header"><div><h1>{meta.label}</h1><p>{meta.description}</p></div>{actions && <div className="page-actions">{actions}</div>}</div>; }
function EmptyWorkspace({ onOpen }: { onOpen: () => void }) { return <div className="empty"><Shirt/><h2>Open a jersey project</h2><p>Your generator, staged assets, and exports stay together in one project folder.</p><button className="primary command" onClick={onOpen}><FolderOpen/>Choose project</button></div>; }

function Startup({ info, recent, newName, setNewName, busy, create, open, openRecent, close, icon }: any) {
  return <div className="startup"><div className="startup-panel"><div className="startup-brand">{icon ? <img src={icon}/> : <Shirt/>}<div><span>NBA 2K</span><h1>Jersey Modder</h1><p>Start a uniform project or continue where you left off.</p></div>{close && <IconButton title="Close" onClick={close}><X/></IconButton>}</div><div className="startup-grid"><section><h2>New project</h2><p>A project folder will be created in the app's projects folder.</p><label className="field"><span>Project name</span><input autoFocus value={newName} onChange={(event) => setNewName(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && create()} placeholder="Detroit 1962 Home" /></label><button className="primary command full" disabled={busy || !newName.trim()} onClick={create}><Plus/>Create Project</button><button className="command full" disabled={busy} onClick={open}><FolderOpen/>Open Existing Project</button><small className="path-note">{info?.projectsFolder}</small></section><section className="recent"><h2>Recent projects</h2>{recent.length ? recent.slice(0, 7).map((item: ProjectSummary) => <button key={item.path} onClick={() => openRecent(item.path)}><Shirt/><span><strong>{item.name}</strong><small>{new Date(item.modified).toLocaleString()}</small></span><ChevronRight/></button>) : <div className="no-recent">No projects yet.</div>}</section></div><div className="startup-version">NBA 2K Jersey Modder v{info?.version || '1.1.0'} Electron</div></div></div>;
}

function Generator({ project, projectPath, update, setPage, status }: any) {
  const [preview, setPreview] = useState(''); const [rendering, setRendering] = useState(false); const renderId = useRef(0);
  const render = useCallback(async () => { const id = ++renderId.current; setRendering(true); try { const result = await window.jersey.engine('render', { project, kind: 'preview' }); const url = await window.jersey.fileDataUrl(result.path); if (id === renderId.current) { setPreview(url); status('Preview updated.'); } } catch (error: any) { status(error.message); } finally { if (id === renderId.current) setRendering(false); } }, [project, status]);
  useEffect(() => { const timer = setTimeout(render, 180); return () => clearTimeout(timer); }, [render]);
  const openEditor = async () => { try { const result = await window.jersey.openEditor('layer', { project, projectPath }); if (result.project) update((next: any) => Object.assign(next, result.project)); } catch (error: any) { status(error.message); } };
  const colors = project.generator.garment === 'Shorts' ? shortsColors : jerseyColors;
  const visibleImages: (readonly [string, string])[] = imageRows.filter(([key]) => project.generator.garment === 'Jersey' ? !key.startsWith('shorts_') && key !== 'waistband_image' : key.startsWith('shorts_') || key === 'waistband_image');
  if (project.generator.garment === 'Jersey') visibleImages.splice(1, 0, ['wrap_across_front_back_logo', 'Wrap image']);
  const visibleLogoTypes = logoTypes.filter(([, target]) => project.generator.garment === 'Shorts' ? target === 'shorts_belt_buckle_logo' : target !== 'shorts_belt_buckle_logo' && target !== 'wrap_across_front_back_logo');
  const setColor = (key: string, value: string) => update((next: any) => { next.generator.colors[key] = value; });
  const chooseImage = async (key: string, label: string) => { const source = await window.jersey.chooseFile('image'); if (!source) return; const stored = await window.jersey.storeAsset(projectPath, source, key.includes('trim') || key.includes('waistband') ? 'trims' : 'logos', label); update((next: any) => { next.generator.images[key] = stored; }); };
  const chooseLogo = async (target: string, label: string) => { const source = await window.jersey.chooseFile('logo'); if (!source) return; const stored = await window.jersey.storeAsset(projectPath, source, 'logos', label); update((next: any) => { if (target === 'front_wordmark') { next.generator.images.front_wordmark_image = stored; next.generator.frontWordmark.lockAspect = true; return; } const placement = { path: stored, targetName: target, offsetX: 0, offsetY: 0, scalePercent: 100, scaleWidthPercent: 100, scaleHeightPercent: 100, lockAspect: true, stretchX: target === 'wrap_across_front_back_logo' }; const existing = next.generator.logos.findIndex((logo: any) => logo.targetName === target); if (existing >= 0) next.generator.logos[existing] = placement; else next.generator.logos.push(placement); }); };
  const logoPath = (target: string) => target === 'front_wordmark' ? project.generator.images.front_wordmark_image : project.generator.logos.find((logo: any) => logo.targetName === target)?.path || null;
  const clearLogo = (target: string) => update((next: any) => { if (target === 'front_wordmark') next.generator.images.front_wordmark_image = null; else next.generator.logos = next.generator.logos.filter((logo: any) => logo.targetName !== target); });
  return <div className="page generator-page"><PageHeader page="generator" actions={<button className="primary command wide-editor" onClick={openEditor}><Layers3/>Open Web Layer Editor</button>}/><div className="generator-grid"><div className="control-rail"><Accordion title="Template" open><label className="check"><input type="checkbox" checked={project.generator.uvOverlay.enabled} onChange={(event) => update((next: any) => { next.generator.uvOverlay.enabled = event.target.checked; })}/>Show UV overlay</label>{project.generator.uvOverlay.enabled && <Range label="UV opacity" value={project.generator.uvOverlay.opacity} min={0} max={100} onChange={(value: number) => update((next: any) => { next.generator.uvOverlay.opacity = value; })}/>}<button className="primary command full" onClick={render}><RefreshCw/>Generate Preview</button></Accordion><Accordion title="Colors">{colors.map(([key, label]: any) => <ColorRow key={key} label={label} value={project.generator.colors[key] || ''} onChange={(value: string) => setColor(key, value)} allowNone={key.includes('panel')}/>)}</Accordion><Accordion title="Base Images">{visibleImages.map(([key, label]) => key === 'wrap_across_front_back_logo' ? <AssetRow key={key} label={label} path={logoPath(key)} choose={() => chooseLogo(key, label)} clear={() => clearLogo(key)}/> : <AssetRow key={key} label={label} path={project.generator.images[key]} choose={() => chooseImage(key, label)} clear={() => update((next: any) => { next.generator.images[key] = null; })}/>)}</Accordion><Accordion title="Logos">{visibleLogoTypes.map(([label, target]) => <AssetRow key={target} label={label} path={logoPath(target)} choose={() => chooseLogo(target, label)} clear={() => clearLogo(target)}/>)}</Accordion><Accordion title="Trim Paths"><p className="muted">{project.generator.trimPathLayers.filter((item: any) => item.garment === project.generator.garment).length} path layer(s) for this garment.</p><button className="command full" onClick={() => setPage('paths')}><Blend/>Open Trim Path Lab</button></Accordion><Accordion title="Preview Number"><label className="check"><input type="checkbox" checked={project.generator.numberPreview.enabled && project.generator.garment === 'Jersey'} disabled={project.generator.garment === 'Shorts'} onChange={(event) => update((next: any) => { next.generator.numberPreview.enabled = event.target.checked; })}/>Show in previews only</label><label className="field"><span>Number</span><input maxLength={4} value={project.generator.numberPreview.text} onChange={(event) => update((next: any) => { next.generator.numberPreview.text = event.target.value; })}/></label></Accordion></div><div className="preview-panel"><div className="preview-toolbar"><span>{rendering ? 'Updating preview...' : `${project.generator.garment} / ${project.generator.garment === 'Jersey' ? project.generator.jerseyCut : project.generator.shortsTemplate}`}</span><button onClick={render} title="Refresh preview"><RefreshCw/></button></div><div className="preview-stage">{preview ? <img src={preview}/> : <div className="preview-loading"><RefreshCw/>Preparing preview...</div>}</div></div></div></div>;
}

function Accordion({ title, children, open = false }: any) { const [expanded, setExpanded] = useState(open); return <section className="accordion"><button className="accordion-head" onClick={() => setExpanded(!expanded)}>{expanded ? <ChevronDown/> : <ChevronRight/>}<span>{title}</span></button>{expanded && <div className="accordion-body">{children}</div>}</section>; }
function ColorRow({ label, value, onChange, allowNone }: any) { const active = value || '#ffffff'; return <div className="color-row"><span>{label}</span>{allowNone ? <button className={`none-color ${!value ? 'selected' : ''}`} title="No color" onClick={() => onChange('')}><CircleOff/></button> : <span className="none-color-spacer" aria-hidden="true"/>}<input className="hex" value={value || ''} placeholder="No color" onChange={(event) => onChange(event.target.value)}/><input type="color" value={active} onChange={(event) => onChange(event.target.value)}/></div>; }
function AssetRow({ label, path, choose, clear }: any) { return <div className="asset-row"><div><strong>{label}</strong><small title={path}>{filename(path)}</small></div><IconButton title={`Choose ${label}`} onClick={choose}><Upload/></IconButton><IconButton title={`Clear ${label}`} disabled={!path} onClick={clear}><X/></IconButton></div>; }
function Range({ label, value, min, max, onChange }: any) { return <label className="range"><span>{label}</span><input type="range" min={min} max={max} value={value} onChange={(event) => onChange(Number(event.target.value))}/><input type="number" min={min} max={max} value={value} onChange={(event) => onChange(Number(event.target.value))}/></label>; }

function Creator({ kind, project, projectPath, update, status, setPage }: any) {
  const isLogo = kind === "logo";
  const typeOptions: readonly (readonly [string, string])[] = isLogo
    ? logoTypes
    : trimTypes;
  const creatorState = project.creators?.[kind] || {};
  const reference = creatorState.reference || null;
  const items: any[] = Array.isArray(creatorState.items)
    ? creatorState.items
    : [];
  const selected: string | null = creatorState.selectedId || null;
  const [referenceUrl, setReferenceUrl] = useState("");
  const [sampleColor, setSampleColor] = useState("#ffffff");
  const [assetTarget, setAssetTarget] = useState<string>(typeOptions[0][1]);
  const saveCreator = (changes: Record<string, any>) =>
    update((next: any) => {
      next.creators ??= {};
      next.creators[kind] ??= {};
      Object.assign(next.creators[kind], changes);
    });
  useEffect(() => {
    let active = true;
    if (!reference) {
      setReferenceUrl("");
      return () => {
        active = false;
      };
    }
    window.jersey
      .fileDataUrl(reference)
      .then((value) => {
        if (active) setReferenceUrl(value);
      })
      .catch(() => {
        if (active) setReferenceUrl("");
      });
    return () => {
      active = false;
    };
  }, [reference]);
  const chooseReference = async () => {
    const source = await window.jersey.chooseFile(isLogo ? "logo" : "trim");
    if (!source) return;
    const stored = await window.jersey.storeAsset(
      projectPath,
      source,
      "references",
      `${kind}_reference`,
    );
    saveCreator({ reference: stored });
  };
  const persistSessionItems = async (staged: any[]) =>
    Promise.all(
      staged.map(async (item) => {
        const stored = await window.jersey.storeAsset(
          projectPath,
          item.path,
          isLogo ? "logos" : "trims",
          item.typeLabel || kind,
        );
        let storedSource: string | null = null;
        if (item.sourcePath) {
          try {
            storedSource = await window.jersey.storeAsset(
              projectPath,
              item.sourcePath,
              isLogo ? "logos" : "trims",
              `${item.typeLabel || kind}_source`,
            );
          } catch {
            storedSource = null;
          }
        }
        return {
          ...item,
          path: stored,
          thumbnailPath: stored,
          sourcePath: storedSource,
        };
      }),
    );
  const open = async (editItemId?: string) => {
    if (!reference) {
      await chooseReference();
      return;
    }
    try {
      const result = await window.jersey.openEditor(kind, {
        reference,
        items,
        selectedId: editItemId || selected,
        startInEditor: Boolean(editItemId),
      });
      const staged = await persistSessionItems(result.state?.items || []);
      saveCreator({
        items: staged,
        selectedId:
          result.state?.selectedId || staged.at(-1)?.id || null,
      });
    } catch (error: any) {
      status(error.message);
    }
  };
  const importImage = async () => {
    const source = await window.jersey.chooseFile(isLogo ? "logo" : "trim");
    if (!source) return;
    try {
      const option =
        typeOptions.find((entry) => entry[1] === assetTarget) || typeOptions[0];
      const stored = await window.jersey.storeAsset(
        projectPath,
        source,
        isLogo ? "logos" : "trims",
        `imported_${option[0]}`,
      );
      const item = {
        id: `imported-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        typeLabel: option[0],
        target: option[1],
        path: stored,
        thumbnailPath: stored,
        sourcePath: stored,
        imported: true,
        scale: 1,
      };
      saveCreator({ items: [...items, item], selectedId: item.id });
      status(`Imported ${filename(stored)} as ${option[0]}.`);
    } catch (error: any) {
      status(error.message);
    }
  };
  const send = async () => {
    if (!items.length) return;
    try {
      const storedItems = await Promise.all(
        items.map(async (item) => ({
          item,
          stored: await window.jersey.storeAsset(
            projectPath,
            item.path,
            isLogo ? "logos" : "trims",
            item.typeLabel || kind,
          ),
        })),
      );
      update((next: any) => {
        for (const { item, stored } of storedItems) {
          if (!isLogo) {
            if (item.target === "trim_path_pattern") {
              next.generator.trimPathPattern = stored;
              continue;
            }
            next.generator.images[item.target] = stored;
            continue;
          }
          if (item.target === "front_wordmark") {
            next.generator.images.front_wordmark_image = stored;
            next.generator.frontWordmark.lockAspect = true;
            continue;
          }
          const placement = {
            path: stored,
            targetName: item.target || "front_center_chest_logo",
            offsetX: 0,
            offsetY: 0,
            scalePercent: 100,
            scaleWidthPercent: 100,
            scaleHeightPercent: 100,
            lockAspect: true,
            stretchX: item.target === "wrap_across_front_back_logo",
          };
          const existing = next.generator.logos.findIndex(
            (logo: any) =>
              logo.path === stored && logo.targetName === placement.targetName,
          );
          if (existing >= 0) next.generator.logos[existing] = placement;
          else next.generator.logos.push(placement);
        }
      });
      const destinations = storedItems
        .map(({ item }) => item.typeLabel || (isLogo ? "Logo" : "Trim"))
        .join(", ");
      const hasTrimPath = !isLogo && storedItems.some(({ item }) => item.target === "trim_path_pattern");
      status(hasTrimPath
        ? `Loaded ${destinations}. The Trim Path Lab is ready to draw with this pattern.`
        : `Sent to Generator: ${destinations}. Open the Web Layer Editor to position them.`);
      setPage(hasTrimPath ? "paths" : "generator");
    } catch (error: any) {
      status(error.message);
    }
  };
  const exportToAi = async () => {
    if (!isLogo || !items.length) return;
    const folder = await window.jersey.chooseFolder();
    if (!folder) return;
    try {
      const result = await window.jersey.exportAiLogoPack(items, folder);
      status(`AI logo pack saved with ${result.count} reference(s).`);
    } catch (error: any) {
      status(error.message);
    }
  };
  const pickColor = async () => {
    try {
      const EyeDropper = (window as any).EyeDropper;
      if (!EyeDropper) {
        status("Use the color swatch to choose a color on this system.");
        return;
      }
      const result = await new EyeDropper().open();
      setSampleColor(String(result.sRGBHex || "#ffffff").toLowerCase());
    } catch {
      /* Canceling the eyedropper is not an error. */
    }
  };
  const copyColor = async () => {
    await window.jersey.copyText(sampleColor.toUpperCase());
    status(`Copied ${sampleColor.toUpperCase()} to the clipboard.`);
  };
  const changeAssetType = (target: string) => {
    setAssetTarget(target);
    const option = typeOptions.find((entry) => entry[1] === target);
    if (!selected || !option) return;
    saveCreator({
      items: items.map((item) =>
        item.id === selected
          ? { ...item, target: option[1], typeLabel: option[0] }
          : item,
      ),
    });
  };
  const removeItem = (item: any) => {
    if (
      !window.confirm(
        `Remove ${item.typeLabel || kind} from the staged list?\n\nThe saved image will remain in this project's ${isLogo ? "logos" : "trims"} folder.`,
      )
    )
      return;
    const remaining = items.filter((candidate) => candidate.id !== item.id);
    let nextSelected = selected;
    if (selected === item.id) {
      const next = remaining.at(-1);
      nextSelected = next?.id || null;
      if (next?.target) setAssetTarget(next.target);
    }
    saveCreator({ items: remaining, selectedId: nextSelected });
    status(`Removed ${filename(item.path)} from the staged list.`);
  };
  const duplicateTrim = (item: any) => {
    if (isLogo) return;
    const duplicate = {
      ...item,
      id: `duplicate-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    };
    const index = items.findIndex((candidate) => candidate.id === item.id);
    const nextItems = [...items];
    nextItems.splice(index < 0 ? nextItems.length : index + 1, 0, duplicate);
    saveCreator({ items: nextItems, selectedId: duplicate.id });
    setAssetTarget(duplicate.target || typeOptions[0][1]);
    status(`Duplicated ${item.typeLabel || "trim"}. Choose another trim type or edit the copy.`);
  };
  const current = items.find((item) => item.id === selected);
  return (
    <div className="page creator-page">
      <PageHeader
        page={kind as PageKey}
        actions={
          <>
            <div className="header-reference-color">
              <strong>Reference color</strong>
              <button
                className="icon-button"
                title="Pick from image"
                onClick={pickColor}
              >
                <Pipette />
              </button>
              <input
                type="color"
                value={sampleColor}
                onChange={(event) => setSampleColor(event.target.value)}
              />
              <input
                className="hex"
                value={sampleColor}
                onChange={(event) => setSampleColor(event.target.value)}
              />
              <button
                className="icon-button"
                title="Copy hex color"
                onClick={copyColor}
              >
                <Copy />
              </button>
            </div>
            <button className="primary command large-editor" onClick={() => open()}>
              <WandSparkles />
              {reference
                ? `Open Web ${isLogo ? "Logo" : "Trim"} Editor`
                : "Choose Reference and Start"}
            </button>
          </>
        }
      />
      <div className="creator-grid">
        <div className="creator-left">
          <div className="reference-panel">
            <div className="panel-title">
              <strong>Reference</strong>
              <div>
                <IconButton title="Upload reference" onClick={chooseReference}>
                  <Upload />
                </IconButton>
                <IconButton
                  title={`Import finished ${kind}`}
                  onClick={importImage}
                >
                  <Plus />
                </IconButton>
              </div>
            </div>
            <div className="reference-image">
              {referenceUrl ? (
                <img src={referenceUrl} />
              ) : (
                <div>
                  <ImageIcon />
                  <span>Upload a uniform reference photo</span>
                </div>
              )}
            </div>
            <small>{filename(reference)}</small>
          </div>
          <div className="selected-preview">
            <strong>Selected {isLogo ? "logo" : "trim"}</strong>
            {current ? (
              <>
                <PathImage path={current.path} />
                <span>{current.typeLabel}</span>
              </>
            ) : (
              <div className="empty-preview">Select a staged item</div>
            )}
          </div>
        </div>
        <div className="creator-right">
          <section className="tool-panel">
            <h2>Staged {isLogo ? "Logos" : "Trims"}</h2>
            <p>
              Use the web editor for selection, or reimport a finished image
              directly into the staged list.
            </p>
            <div className={`stage-actions ${isLogo ? "three" : ""}`}>
              <button className="command" onClick={() => open()}>
                <WandSparkles />
                Reopen Web Editor
              </button>
              <button
                className="primary command"
                disabled={!items.length}
                onClick={send}
              >
                <Layers3 />
                Send Staged to Generator
              </button>
              {isLogo && (
                <button
                  className="command"
                  disabled={!items.length}
                  onClick={exportToAi}
                >
                  <Download />
                  Export to AI
                </button>
              )}
            </div>
            <div className="creator-import">
              <label className="field">
                <span>{isLogo ? "Logo" : "Trim"} type</span>
                <select
                  value={assetTarget}
                  onChange={(event) => changeAssetType(event.target.value)}
                >
                  {typeOptions.map(([label, target]) => (
                    <option key={target} value={target}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <button className="command" onClick={importImage}>
                <Upload />
                Import Finished {isLogo ? "Logo" : "Trim"}
              </button>
            </div>
            <div className="staged-list">
              {items.length ? (
                items.map((item) => (
                  <div
                    className={`staged-item ${!isLogo ? "has-duplicate" : ""} ${item.id === selected ? "selected" : ""}`}
                    key={item.id}
                  >
                    <button
                      className="staged-select"
                      onClick={() => {
                        saveCreator({ selectedId: item.id });
                        setAssetTarget(item.target || typeOptions[0][1]);
                      }}
                      onDoubleClick={() => open(item.id)}
                      title={`Double-click to edit ${item.typeLabel || kind}`}
                    >
                      <FileImage />
                      <span>
                        <strong>{item.typeLabel}</strong>
                        <small>{filename(item.path)}</small>
                      </span>
                      <ChevronRight />
                    </button>
                    {!isLogo && (
                      <button
                        className="staged-duplicate"
                        title={`Duplicate ${item.typeLabel || "trim"}`}
                        onClick={() => duplicateTrim(item)}
                      >
                        <Copy />
                      </button>
                    )}
                    <button
                      className="staged-edit"
                      title={`Edit ${item.typeLabel || kind}`}
                      onClick={() => open(item.id)}
                    >
                      <SlidersHorizontal />
                      <span>Edit</span>
                    </button>
                    <button
                      className="staged-remove"
                      title={`Remove ${item.typeLabel || kind}`}
                      onClick={() => removeItem(item)}
                    >
                      <X />
                    </button>
                  </div>
                ))
              ) : (
                <div className="no-items">
                  Nothing staged yet. Select multiple{" "}
                  {isLogo
                    ? "logos with the lasso or box tool"
                    : "trim lines with the two-point selector"}{" "}
                  in the web editor, or import a finished image above.
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function PathImage({ path }: { path: string }) { const [src, setSrc] = useState(''); useEffect(() => { let active = true; window.jersey.fileDataUrl(path).then((value) => active && setSrc(value)).catch(() => setSrc('')); return () => { active = false; }; }, [path]); return src ? <img src={src}/> : <div className="empty-preview">Loading preview...</div>; }

function TrimPaths({ project, projectPath, update, status }: any) {
  const pattern: string | null = project.generator.trimPathPattern || null;
  const choose = async (): Promise<string | null> => {
    const source = await window.jersey.chooseFile('trim');
    if (!source) return null;
    const stored = await window.jersey.storeAsset(projectPath, source, 'trims', 'trim_path_pattern');
    update((next: any) => { next.generator.trimPathPattern = stored; });
    status(`Loaded ${filename(stored)} as the Trim Path pattern.`);
    return stored;
  };
  const clear = () => update((next: any) => { next.generator.trimPathPattern = null; });
  const open = async () => {
    const selectedPattern = pattern || await choose();
    if (!selectedPattern) return;
    try {
      const editorProject = clone(project);
      editorProject.generator.trimPathPattern = selectedPattern;
      const result = await window.jersey.openEditor('paths', { project: editorProject, projectPath, pattern: selectedPattern });
      if (result.project) update((next: any) => Object.assign(next, result.project));
    } catch (error: any) {
      status(error.message);
    }
  };
  return <div className="page"><PageHeader page="paths" actions={<button className="primary command large-editor" onClick={open}><Blend/>{pattern ? 'Open Web Trim Path Lab' : 'Choose Trim Pattern'}</button>}/><div className="two-column"><section className="tool-panel"><h2>Trim source</h2><AssetRow label="Straight trim pattern" path={pattern} choose={choose} clear={clear}/><p className="muted">Choose Trim Path in the Trim Creator to send a staged strip here automatically. The pattern bends continuously along straight segments, smooth curves, T junctions, and mirrored paths.</p></section><section className="tool-panel"><h2>Current project paths</h2><div className="stat-number">{project.generator.trimPathLayers.filter((item: any) => item.garment === project.generator.garment).length}</div><p>{project.generator.garment} trim path layer(s) on {project.generator.garment === 'Jersey' ? project.generator.jerseyCut : project.generator.shortsTemplate}.</p><button className="command full" onClick={open}><Play/>Continue Editing</button></section></div></div>;
}

function NumberEditor({ status }: any) { const [source, setSource] = useState<string | null>(null); const [preview, setPreview] = useState(''); const [fill, setFill] = useState(''); const [outline, setOutline] = useState(''); const [edge, setEdge] = useState(0); const [thickness, setThickness] = useState(0); const open = async () => { const path = await window.jersey.chooseFile('iff'); if (!path) return; try { const result = await window.jersey.engine('font_open', { path }); setSource(result.source); setPreview(await window.jersey.fileDataUrl(result.preview)); status(`Loaded ${filename(path)} (${result.width} x ${result.height}).`); } catch (error: any) { status(error.message); } }; const recolor = async () => { if (!source) return; try { const result = await window.jersey.engine('font_recolor', { source, fill: fill || null, outline: outline || null, edge, thickness }); setPreview(await window.jersey.fileDataUrl(result.path)); status('Number recolor preview updated.'); } catch (error: any) { status(error.message); } }; useEffect(() => { if (!source) return; const timer = setTimeout(recolor, 180); return () => clearTimeout(timer); }, [fill, outline, edge, thickness]); const save = async () => { if (!source) return; const destination = await window.jersey.saveFile('iff', `${parseName(source)}_recolor.iff`); if (!destination) return; try { await window.jersey.engine('font_save', { source, destination, fill: fill || null, outline: outline || null, edge, thickness }); status(`Saved ${filename(destination)}.`); } catch (error: any) { status(error.message); } }; return <div className="page"><PageHeader page="number" actions={<><button className="command" onClick={open}><FolderOpen/>Open Font IFF</button><button className="primary command" disabled={!source} onClick={save}><Save/>Save Font IFF As</button></>}/><div className="editor-split"><div className="image-workspace">{preview ? <img src={preview}/> : <div className="preview-loading"><Sparkles/>Open a font IFF to preview its number sheet.</div>}</div><div className="right-controls"><section className="tool-panel"><h2>Recolor</h2><ColorControl label="Fill" value={fill} setValue={setFill}/><ColorControl label="Outline" value={outline} setValue={setOutline}/><Range label="Edge protection" value={edge} min={0} max={100} onChange={setEdge}/><Range label="Outline thickness" value={thickness} min={0} max={20} onChange={setThickness}/><p className="muted">No change is the default for both colors. Entering a hex value enables that recolor automatically.</p></section></div></div></div>; }
function ColorControl({ label, value, setValue }: any) { return <div className="color-control"><div><strong>{label}</strong><label className="check"><input type="checkbox" checked={!value} onChange={(event) => setValue(event.target.checked ? '' : '#ffffff')}/>No change</label></div><div><input className="hex" value={value} disabled={!value} placeholder="#ffffff" onChange={(event) => setValue(event.target.value)}/><input type="color" value={value || '#ffffff'} onChange={(event) => setValue(event.target.value)}/></div></div>; }
function parseName(path: string) { const base = filename(path); return base.includes('.') ? base.slice(0, base.lastIndexOf('.')) : base; }

function TweakEditor({ status }: any) { const [source, setSource] = useState<string | null>(null); const [values, setValues] = useState({ x: 0, y: 0, width: 0, height: 0 }); const [lock, setLock] = useState(false); const open = async () => { const path = await window.jersey.chooseFile('iff'); if (!path) return; try { const result = await window.jersey.engine('tweak_open', { path }); setSource(path); setValues({ x: result.x.value, y: result.y.value, width: result.width.value, height: result.height.value }); status(`Loaded ${filename(path)}.`); } catch (error: any) { status(error.message); } }; const change = (key: string, value: number) => setValues((current) => { const next: any = { ...current, [key]: value }; if (lock && key === 'width') next.height = value; if (lock && key === 'height') next.width = value; return next; }); const save = async () => { if (!source) return; const destination = await window.jersey.saveFile('iff', `${parseName(source)}_edited.iff`); if (!destination) return; try { await window.jersey.engine('tweak_save', { source, destination, ...values }); status(`Saved ${filename(destination)}.`); } catch (error: any) { status(error.message); } }; return <div className="page"><PageHeader page="tweak" actions={<><button className="command" onClick={open}><FolderOpen/>Open Tweak IFF</button><button className="primary command" disabled={!source} onClick={save}><Save/>Save Tweak IFF As</button></>}/><section className="tool-panel tweak-panel"><div className="tweak-heading"><div><h2>Front number placement</h2><p>{source ? filename(source) : 'Open a tweak IFF to edit its front number.'}</p></div><label className="check"><input type="checkbox" checked={lock} onChange={(event) => setLock(event.target.checked)}/>Lock width and height</label></div><TweakSlider label="X position" help="Left moves number left, right moves number right" value={values.x} onChange={(value: number) => change('x', value)}/><TweakSlider label="Y position" help="Left moves number down, right moves number up" value={values.y} onChange={(value: number) => change('y', value)}/><TweakSlider label="Width" help="Left makes narrower, right makes wider" value={values.width} onChange={(value: number) => change('width', value)}/><TweakSlider label="Height" help="Left makes shorter, right makes taller" value={values.height} onChange={(value: number) => change('height', value)}/></section></div>; }
function TweakSlider({ label, help, value, onChange }: any) { return <div className="tweak-row"><div><strong>{label}</strong><small>{help}</small></div><input type="range" min={value - 2 || -2} max={value + 2 || 2} step="0.001" value={value} onChange={(event) => onChange(Number(event.target.value))}/><input type="number" step="0.001" value={value} onChange={(event) => onChange(Number(event.target.value))}/></div>; }

function TextureCreator({ project, status }: any) { const [kind, setKind] = useState('Color Texture'); const [strength, setStrength] = useState(15); const [preview, setPreview] = useState(''); const refresh = useCallback(async () => { try { const result = await window.jersey.engine('render', { project, kind, strength }); setPreview(await window.jersey.fileDataUrl(result.path)); } catch (error: any) { status(error.message); } }, [project, kind, strength]); useEffect(() => { const timer = setTimeout(refresh, 180); return () => clearTimeout(timer); }, [refresh]); const save = async (format: 'png' | 'dds' | 'psd') => { const path = await window.jersey.saveFile(format, `${project.generator.garment.toLowerCase()}_${kind.toLowerCase().replace(' texture', '')}.${format}`); if (!path) return; try { await window.jersey.engine('save_texture', { project, path, kind, format: `.${format}`, strength }); status(`Saved ${filename(path)}.`); } catch (error: any) { status(error.message); } }; return <div className="page"><PageHeader page="texture" actions={<button className="command" onClick={refresh}><RefreshCw/>Refresh Preview</button>}/><div className="editor-split"><div className="image-workspace">{preview ? <img src={preview}/> : <div className="preview-loading">Preparing texture...</div>}</div><div className="right-controls"><section className="tool-panel"><label className="field"><span>Texture type</span><select value={kind} onChange={(event) => setKind(event.target.value)}><option>Color Texture</option><option>Region Texture</option><option>Normal Texture</option></select></label>{kind === 'Normal Texture' && <Range label="Logo and trim strength" value={strength} min={0} max={100} onChange={setStrength}/>}<div className="export-stack"><button className="primary command" onClick={() => save('png')}><Save/>Save PNG As</button><button className="command" onClick={() => save('dds')}><Save/>Save DDS BC1 As</button><button className="command" disabled={kind !== 'Color Texture'} onClick={() => save('psd')}><Layers3/>Layered PSD Export</button></div></section></div></div></div>; }

function IffEditor({ status }: any) { const [source, setSource] = useState<string | null>(null); const [rows, setRows] = useState<any[]>([]); const open = async () => { const path = await window.jersey.chooseFile('iff'); if (!path) return; try { const result = await window.jersey.engine('iff_scan', { path }); setSource(path); setRows(result.pairs); status(`Loaded ${filename(path)}: ${result.pairs.length} texture pair(s).`); } catch (error: any) { status(error.message); } }; return <div className="page"><PageHeader page="iff" actions={<button className="primary command" onClick={open}><FolderOpen/>Import IFF</button>}/><section className="tool-panel table-panel"><div className="source-line"><strong>{source ? filename(source) : 'No IFF loaded'}</strong><span>{rows.length} resource pair(s)</span></div><div className="data-table"><div className="table-head"><span>Texture</span><span>DDS</span><span>TXTR</span><span>Status</span></div>{rows.map((row, index) => <div className="table-row" key={`${row.key}-${index}`}><span>{row.key}</span><span>{row.dds?.name || ''}</span><span>{row.txtr?.name || ''}</span><span>{row.status}</span></div>)}</div></section></div>; }

function RdatEditor({ status }: any) { const [source, setSource] = useState<string | null>(null); const [entry, setEntry] = useState<string | null>(null); const [encoding, setEncoding] = useState('utf-8'); const [text, setText] = useState(''); const open = async () => { const path = await window.jersey.chooseFile('rdat'); if (!path) return; try { const result = await window.jersey.engine('rdat_read', { path }); setSource(path); setEntry(result.entry); setEncoding(result.encoding); setText(result.text); status(`Loaded ${result.entry || filename(path)} (${result.encoding}).`); } catch (error: any) { status(error.message); } }; const save = async (as: boolean) => { if (!source) return; const destination = as ? await window.jersey.saveFile(extnameKind(source), filename(source)) : source; if (!destination) return; try { await window.jersey.engine('rdat_write', { source, destination, entry, encoding, text }); setSource(destination); status(`Saved ${filename(destination)}.`); } catch (error: any) { status(error.message); } }; return <div className="page"><PageHeader page="rdat" actions={<><button className="command" onClick={open}><FolderOpen/>Open RDAT or IFF</button><button className="command" disabled={!source} onClick={() => save(false)}><Save/>Save</button><button className="primary command" disabled={!source} onClick={() => save(true)}><Save/>Save As</button></>}/><textarea className="text-editor" spellCheck={false} value={text} onChange={(event) => setText(event.target.value)} placeholder="Open an RDAT file or an IFF containing an RDAT entry."/></div>; }
function extnameKind(path: string): string { return path.toLowerCase().endsWith('.iff') ? 'iff' : 'rdat'; }

function TemplateEditor({ status }: any) { const [catalog, setCatalog] = useState<any>(null); const [garment, setGarment] = useState('Jersey'); const [variant, setVariant] = useState('Retro U'); const [map, setMap] = useState('Jersey color'); const [data, setData] = useState<any>(null); const [preview, setPreview] = useState(''); useEffect(() => { window.jersey.engine('template_catalog').then(setCatalog).catch((error) => status(error.message)); }, []); useEffect(() => { if (!catalog) return; const variants = Object.keys(catalog[garment]); const nextVariant = variants.includes(variant) ? variant : variants[0]; setVariant(nextVariant); const maps = catalog[garment][nextVariant]; setMap(maps.includes(map) ? map : maps[0]); }, [catalog, garment, variant]); const load = async () => { try { const result = await window.jersey.engine('template_load', { garment, variant, map }); setData(result); setPreview(await window.jersey.fileDataUrl(result.image)); status(`Loaded ${variant} ${map} master.`); } catch (error: any) { status(error.message); } }; useEffect(() => { if (catalog) load(); }, [catalog, garment, variant, map]); const save = async () => { if (!data) return; const path = await window.jersey.saveFile('rdat', filename(data.zonesPath)); if (!path) return; try { await window.jersey.engine('template_save', { path, image: data.image, zones: data.zones }); status(`Saved ${data.zones.length} zones.`); } catch (error: any) { status(error.message); } }; return <div className="page"><PageHeader page="template" actions={<button className="primary command" disabled={!data} onClick={save}><Save/>Save Zone Map As</button>}/><div className="template-controls"><label className="field"><span>Garment</span><select value={garment} onChange={(event) => setGarment(event.target.value)}><option>Jersey</option><option>Shorts</option></select></label><label className="field"><span>Template</span><select value={variant} onChange={(event) => setVariant(event.target.value)}>{catalog && Object.keys(catalog[garment]).map((item) => <option key={item}>{item}</option>)}</select></label><label className="field"><span>Map</span><select value={map} onChange={(event) => setMap(event.target.value)}>{catalog?.[garment]?.[variant]?.map((item: string) => <option key={item}>{item}</option>)}</select></label></div><div className="template-grid"><div className="image-workspace">{preview && <img src={preview}/>}</div><div className="zone-list">{data?.zones.map((zone: any, index: number) => <button key={`${zone.name}-${index}`}><span className="swatch" style={{ background: zone.color || '#ffffff' }}/><span><strong>{zone.name}</strong><small>{zone.x}, {zone.y} / {zone.width} x {zone.height}</small></span></button>)}</div></div></div>; }
