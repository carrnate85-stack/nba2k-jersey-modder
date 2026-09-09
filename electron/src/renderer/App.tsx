import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Aperture, Archive, Blend, Box, ChevronDown, ChevronRight, CircleOff, Download, Copy, FileImage, FileText, FolderOpen, Grid3X3, Image as ImageIcon, Layers3, Palette, Pipette, Play, Plus, RefreshCw, Save, Scissors, Search, Settings2, Shirt, SlidersHorizontal, Sparkles, Upload, WandSparkles, X, } from 'lucide-react';
import type { AppInfo, JsonObject, ProjectSummary } from '../shared';
import { PageKey, PAGE_META, imageRows, jerseyColors, logoTypes, trimTypes, shortsColors, clone, filename, projectName, Nav, IconButton, PageHeader, Accordion, ColorRow, AssetRow, Range, PathImage, ColorControl, parseName, TweakSlider, extnameKind } from './components';
import { Generator } from './pages/Generator';
import { Creator } from './pages/Creator';
import { TrimPaths } from './pages/TrimPaths';
import { NumberEditor } from './pages/NumberEditor';
import { TweakEditor } from './pages/TweakEditor';
import { TextureCreator } from './pages/TextureCreator';
import { IffEditor } from './pages/IffEditor';
import { RdatEditor } from './pages/RdatEditor';
import { TemplateEditor } from './pages/TemplateEditor';
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
    const [recoveryStatus, setRecoveryStatus] = useState('');
    const projectRef = useRef(project);
    projectRef.current = project;
    useEffect(() => {
        Promise.all([window.jersey.appInfo(), window.jersey.listProjects()]).then(async ([appInfo, projects]) => {
            setInfo(appInfo);
            setRecent(projects);
            setStatus('Python engine ready.');
            try {
                setIcon(await window.jersey.fileDataUrl(`${appInfo.root}\\wpf\\JerseyModder.Wpf\\Assets\\app-icon.png`));
            }
            catch { /* icon has CSS fallback */ }
        }).catch((error) => setStatus(error.message));
        const removeProject = window.jersey.onProjectUpdate((payload) => { setProject(payload); setDirty(true); });
        const removeStatus = window.jersey.onStatus(setStatus);
        return () => { removeProject(); removeStatus(); };
    }, []);
    const openLoaded = useCallback((loaded: {
        path: string;
        project: JsonObject;
        recovered?: boolean;
    }) => {
        loaded.project.generator.garment = 'Jersey';
        setProject(loaded.project);
        setProjectPath(loaded.path);
        setDirty(Boolean(loaded.recovered));
        setPage('generator');
        setStartup(false);
        setStatus(`Opened ${projectName(loaded.path)}.`);
    }, []);
    const create = async () => {
        if (!newName.trim())
            return;
        if (!await leaveProject()) return;
        setBusy(true);
        try {
            openLoaded(await window.jersey.createProject(newName));
            setRecent(await window.jersey.listProjects());
            setNewName('');
        }
        catch (error: any) {
            setStatus(error.message);
        }
        finally {
            setBusy(false);
        }
    };
    const chooseOpen = async () => {
        if (!await leaveProject()) return;
        try { const loaded = await window.jersey.chooseProject(); if (loaded) openLoaded(loaded); }
        catch (error: any) { setStatus(error.message); }
    };
    const save = async () => { if (!project || !projectPath)
        return false; setBusy(true); try {
        await window.jersey.saveProject(projectPath, project);
        if (projectRef.current === project) setDirty(false);
        setStatus(`Saved ${projectName(projectPath)}.`);
        return projectRef.current === project;
    }
    catch (error: any) {
        setStatus(error.message);
        return false;
    }
    finally {
        setBusy(false);
    } };
    const leaveProject = async () => {
        if (!dirty || !projectPath) return true;
        const answer = await window.jersey.confirmLeave();
        if (answer === 'cancel') return false;
        if (answer === 'save') return await save();
        await window.jersey.discardRecovery(projectPath);
        setDirty(false);
        return true;
    };
    useEffect(() => {
        void window.jersey.setDirty(dirty);
        if (!dirty || !project || !projectPath) { setRecoveryStatus(''); return; }
        setRecoveryStatus('Recovery pending');
        const timer = setTimeout(() => {
            window.jersey.saveRecovery(projectPath, project).then(() => setRecoveryStatus('Recovery saved')).catch(error => setRecoveryStatus(`Recovery failed: ${error.message}`));
        }, 700);
        return () => clearTimeout(timer);
    }, [project, projectPath, dirty]);
    useEffect(() => window.jersey.onCloseRequest(() => { void leaveProject().then(ok => { if (ok) void window.jersey.closeApp(); }); }), [dirty, project, projectPath]);
    useEffect(() => {
        const key = (event: KeyboardEvent) => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); void save(); } };
        window.addEventListener('keydown', key);
        return () => window.removeEventListener('keydown', key);
    }, [project, projectPath]);
    const updateProject = useCallback((updater: (next: JsonObject) => void) => { setProject((current) => { if (!current)
        return current; const next = clone(current); updater(next); return next; }); setDirty(true); }, []);
    const setScope = (key: 'garment' | 'template', value: string) => updateProject((next) => {
        if (key === 'garment') {
            next.generator.garment = value;
            next.generator[value === 'Shorts' ? 'shortsTemplate' : 'jerseyCut'] = value === 'Shorts' ? 'Retro shorts' : 'Retro U';
        }
        else
            next.generator[next.generator.garment === 'Shorts' ? 'shortsTemplate' : 'jerseyCut'] = value;
    });
    const exportPackage = async () => { if (!project)
        return; const folder = await window.jersey.chooseFolder(); if (!folder)
        return; setBusy(true); try {
        const result = await window.jersey.engine('export_package', { project, folder });
        setStatus(`Package created: ${result.path}`);
    }
    catch (error: any) {
        setStatus(error.message);
    }
    finally {
        setBusy(false);
    } };
    const blender = async () => { if (!project)
        return; setBusy(true); try {
        await window.jersey.openBlender(project);
        setStatus('Blender preview opened.');
    }
    catch (error: any) {
        setStatus(error.message);
    }
    finally {
        setBusy(false);
    } };
    const scopeTemplate = project?.generator.garment === 'Shorts' ? project?.generator.shortsTemplate : project?.generator.jerseyCut;
    return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark">{icon ? <img src={icon}/> : <Shirt />}</div><div><span>NBA 2K</span><strong>Jersey Modder</strong><small>Uniform workspace</small></div></div>
      <nav className="navigation">
        {(Object.keys(PAGE_META) as PageKey[]).slice(0, 7).map((key) => <Nav key={key} active={page === key} item={PAGE_META[key]} onClick={() => setPage(key)}/>)}
      </nav>
      <div className="advanced"><div className="advanced-title"><Settings2 size={15}/> Advanced</div>{(['iff', 'rdat', 'template'] as PageKey[]).map((key) => <Nav key={key} compact active={page === key} item={PAGE_META[key]} onClick={() => setPage(key)}/>)}<small>Electron + Python engine</small></div>
    </aside>
    <main className="workspace">
      <header className="topbar">
        <div className="project-title" title={projectPath || ''}><strong>{projectName(projectPath)}</strong><span className={dirty ? 'dirty-indicator' : ''}>{dirty ? 'Unsaved changes' : projectPath ? 'Saved' : 'No project open'}</span></div>
        <label className="top-field"><span>Garment</span><select disabled={!project} value={project?.generator.garment || 'Jersey'} onChange={(event) => setScope('garment', event.target.value)}><option>Jersey</option><option>Shorts</option></select></label>
        <label className="top-field template-field"><span>Template</span><select disabled={!project} value={scopeTemplate || 'Retro U'} onChange={(event) => setScope('template', event.target.value)}>{project?.generator.garment === 'Shorts' ? <><option>Retro shorts</option><option>Classic shorts</option><option>Modern shorts</option></> : <option>Retro U</option>}</select></label>
        <div className="top-actions"><IconButton title="New project" onClick={() => setStartup(true)}><Plus /></IconButton><IconButton title="Open project" onClick={chooseOpen}><FolderOpen /></IconButton><IconButton title="Save project" disabled={!project || !dirty} onClick={save}><Save /></IconButton><button className="command" disabled={!project || busy} onClick={exportPackage}><Download />Export Package</button><button className="primary command" disabled={!project || busy} onClick={blender}><Box />Blender Preview</button></div>
      </header>
      <section className="page-host">
        {!project ? <EmptyWorkspace onOpen={() => setStartup(true)}/> : <Page page={page} project={project} projectPath={projectPath!} update={updateProject} setPage={setPage} status={setStatus}/>}
      </section>
      <footer role="status"><span className={busy ? 'working' : ''}>{busy ? 'Working... ' : ''}{status}</span><span>{recoveryStatus} · v{info?.version || '1.2.0'}</span></footer>
    </main>
    {startup && <Startup info={info} recent={recent} newName={newName} setNewName={setNewName} busy={busy} create={create} open={chooseOpen} openRecent={async (path: string) => { if (await leaveProject()) { try { openLoaded(await window.jersey.loadProject(path)); } catch (error: any) { setStatus(error.message); } } }} close={project ? () => setStartup(false) : undefined} icon={icon}/>}
  </div>;
}
function Page({ page, project, projectPath, update, setPage, status }: any) {
    const common = { project, projectPath, update, status };
    if (page === 'generator')
        return <Generator {...common} setPage={setPage}/>;
    if (page === 'logo')
        return <Creator kind="logo" {...common} setPage={setPage}/>;
    if (page === 'trim')
        return <Creator kind="trim" {...common} setPage={setPage}/>;
    if (page === 'paths')
        return <TrimPaths {...common}/>;
    if (page === 'number')
        return <NumberEditor {...common}/>;
    if (page === 'tweak')
        return <TweakEditor {...common}/>;
    if (page === 'texture')
        return <TextureCreator project={project} status={status}/>;
    if (page === 'iff')
        return <IffEditor status={status}/>;
    if (page === 'rdat')
        return <RdatEditor status={status}/>;
    return <TemplateEditor status={status}/>;
}
function EmptyWorkspace({ onOpen }: {
    onOpen: () => void;
}) { return <div className="empty"><Shirt /><h2>Open a jersey project</h2><p>Your generator, staged assets, and exports stay together in one project folder.</p><button className="primary command" onClick={onOpen}><FolderOpen />Choose project</button></div>; }
function Startup({ info, recent, newName, setNewName, busy, create, open, openRecent, close, icon }: any) {
    return <div className="startup"><div className="startup-panel"><div className="startup-brand">{icon ? <img src={icon}/> : <Shirt />}<div><span>NBA 2K</span><h1>Jersey Modder</h1><p>Start a uniform project or continue where you left off.</p></div>{close && <IconButton title="Close" onClick={close}><X /></IconButton>}</div><div className="startup-grid"><section><h2>New project</h2><p>A project folder will be created in the app's projects folder.</p><label className="field"><span>Project name</span><input autoFocus value={newName} onChange={(event) => setNewName(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && create()} placeholder="Detroit 1962 Home"/></label><button className="primary command full" disabled={busy || !newName.trim()} onClick={create}><Plus />Create Project</button><button className="command full" disabled={busy} onClick={open}><FolderOpen />Open Existing Project</button><small className="path-note">{info?.projectsFolder}</small></section><section className="recent"><h2>Recent projects</h2>{recent.length ? recent.slice(0, 7).map((item: ProjectSummary) => <button key={item.path} onClick={() => openRecent(item.path)}><Shirt /><span><strong>{item.name}</strong><small>{new Date(item.modified).toLocaleString()}</small></span><ChevronRight /></button>) : <div className="no-recent">No projects yet.</div>}</section></div><div className="startup-version">NBA 2K Jersey Modder v{info?.version || '1.1.0'} Electron</div></div></div>;
}
