import { app, BrowserWindow, clipboard, dialog, ipcMain, shell } from 'electron';
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync, copyFileSync } from 'node:fs';
import { dirname, extname, join, parse, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { pathToFileURL } from 'node:url';
import type { JsonObject } from './shared';

declare const MAIN_WINDOW_VITE_DEV_SERVER_URL: string | undefined;
declare const MAIN_WINDOW_VITE_NAME: string;

let mainWindow: BrowserWindow | null = null;

const defaultProject = (): JsonObject => ({
  app: 'NBA 2K Jersey Modder', projectVersion: 3,
  creators: {
    logo: { reference: null, items: [], selectedId: null },
    trim: { reference: null, items: [], selectedId: null },
  },
  generator: {
    garment: 'Jersey', jerseyCut: 'Retro U', shortsTemplate: 'Retro shorts',
    colors: {
      front_color: '#ffffff', back_color: '#ffffff', left_panel_color: '', right_panel_color: '',
      shorts_left_panel_color: '', shorts_right_panel_color: '',
      collar_background_color: '#ffffff', waistband_color: '#ffffff',
      left_arm_hole_trim_color: '#ffffff', right_arm_hole_trim_color: '#ffffff', collar_trim_color: '#ffffff',
    },
    images: {
      left_panel_image: null, right_panel_image: null, shorts_left_panel_image: null,
      shorts_right_panel_image: null, waistband_image: null, jersey_background_image: null,
      front_wordmark_image: null, left_arm_hole_trim_image: null,
      right_arm_hole_trim_image: null, collar_trim_image: null,
    },
    frontWordmark: { offsetX: 0, offsetY: 0, scalePercent: 100, scaleWidthPercent: 100, scaleHeightPercent: 100, lockAspect: true },
    jerseyBackground: { tile: false, tileScalePercent: 100 }, logos: [], trimPathLayers: [], trimPathPattern: null, trimPlacements: {},
    backgroundCleanup: { removeWhite: false, removeBlack: false, outsideOnly: true, tolerance: 32 },
    fabricOverlay: { preset: 'None', customPath: null, blendMode: 'multiply', opacity: 0 },
    uvOverlay: { enabled: true, opacity: 45 },
    numberPreview: { enabled: true, text: '15', x: 1160, y: 780, scale: 100, scaleWidth: 100, scaleHeight: 100 },
    webEditor: { layerOrder: [], layerCleanup: {} },
  },
});

function mergeDefaults(target: JsonObject, defaults: JsonObject): JsonObject {
  for (const [key, value] of Object.entries(defaults)) {
    if (target[key] === undefined || target[key] === null) target[key] = structuredClone(value);
    else if (value && typeof value === 'object' && !Array.isArray(value) && typeof target[key] === 'object' && !Array.isArray(target[key])) mergeDefaults(target[key], value);
  }
  target.projectVersion = 3;
  return target;
}

function migratePanelColors(target: JsonObject): JsonObject {
  const generator = target.generator;
  if (!generator || typeof generator !== 'object' || Array.isArray(generator)) return target;
  const colors = generator.colors;
  if (!colors || typeof colors !== 'object' || Array.isArray(colors)) return target;
  if (colors.shorts_left_panel_color === undefined) colors.shorts_left_panel_color = colors.left_panel_color ?? '';
  if (colors.shorts_right_panel_color === undefined) colors.shorts_right_panel_color = colors.right_panel_color ?? '';
  return target;
}

function findRoot(): string {
  const candidates = [process.env.JERSEY_MODDER_ROOT, resolve(__dirname, '..', '..', '..'), process.cwd(), dirname(process.execPath)];
  for (const candidate of candidates) {
    if (!candidate) continue;
    let folder = resolve(candidate);
    for (let depth = 0; depth < 7; depth += 1) {
      if (existsSync(join(folder, 'main.py')) && existsSync(join(folder, 'tools', 'wpf_engine.py'))) return folder;
      const parent = dirname(folder); if (parent === folder) break; folder = parent;
    }
  }
  throw new Error('The Jersey Modder application folder could not be found.');
}

const root = findRoot();
const projectsFolder = join(root, 'projects');
const assetFolders = ['logos', 'trims', 'numbers', 'textures'];

function safeName(value: string): string {
  return value.trim().replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').replace(/[. ]+$/g, '');
}

function ensureProjectStructure(projectPath: string): void {
  const folder = dirname(resolve(projectPath));
  mkdirSync(folder, { recursive: true });
  for (const category of assetFolders) mkdirSync(join(folder, 'assets', category), { recursive: true });
  mkdirSync(join(folder, 'references'), { recursive: true });
  mkdirSync(join(folder, 'exports'), { recursive: true });
}

function loadProject(path: string): JsonObject {
  const payload = JSON.parse(readFileSync(path, 'utf8'));
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) throw new Error('Project JSON is invalid.');
  return mergeDefaults(migratePanelColors(payload), defaultProject());
}

function saveProject(path: string, project: JsonObject): string {
  ensureProjectStructure(path);
  writeFileSync(path, `${JSON.stringify(mergeDefaults(migratePanelColors(project), defaultProject()), null, 2)}\n`, 'utf8');
  return path;
}

function findPython(): string {
  const bundled = join(process.env.USERPROFILE || '', '.cache', 'codex-runtimes', 'codex-primary-runtime', 'dependencies', 'python', 'python.exe');
  const candidates = [join(root, '.venv', 'Scripts', 'python.exe'), bundled, 'python'];
  return candidates.find((candidate) => candidate === 'python' || existsSync(candidate)) || 'python';
}

class PythonEngine {
  private process: ChildProcessWithoutNullStreams | null = null;
  private nextId = 0;
  private pending = new Map<number, { resolve: (value: any) => void; reject: (error: Error) => void }>();

  start(): void {
    if (this.process && !this.process.killed) return;
    this.process = spawn(findPython(), ['-u', join(root, 'tools', 'wpf_engine.py')], { cwd: root, windowsHide: true });
    let buffer = '';
    this.process.stdout.setEncoding('utf8');
    this.process.stdout.on('data', (chunk: string) => {
      buffer += chunk;
      let newline = buffer.indexOf('\n');
      while (newline >= 0) {
        const line = buffer.slice(0, newline).trim(); buffer = buffer.slice(newline + 1); newline = buffer.indexOf('\n');
        if (!line) continue;
        try {
          const response = JSON.parse(line); const pending = this.pending.get(response.id);
          if (!pending) continue; this.pending.delete(response.id);
          if (response.ok) pending.resolve(response.result); else pending.reject(new Error(response.error || 'Python engine failed.'));
        } catch { /* Python diagnostics are written to stderr. */ }
      }
    });
    this.process.stderr.setEncoding('utf8');
    this.process.stderr.on('data', (message: string) => console.error(`[python] ${message.trimEnd()}`));
    this.process.on('exit', () => {
      for (const pending of this.pending.values()) pending.reject(new Error('The Python engine stopped.'));
      this.pending.clear(); this.process = null;
    });
  }

  call(method: string, params: JsonObject = {}): Promise<any> {
    this.start(); const id = ++this.nextId;
    return new Promise((resolveCall, reject) => {
      this.pending.set(id, { resolve: resolveCall, reject });
      this.process!.stdin.write(`${JSON.stringify({ id, method, params })}\n`);
    });
  }

  stop(): void {
    if (!this.process) return;
    this.process.stdin.write('{"id":0,"method":"shutdown","params":{}}\n');
    setTimeout(() => this.process?.kill(), 1000).unref();
  }
}

const engine = new PythonEngine();

function dataUrl(path: string): string {
  const mime: Record<string, string> = { '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif', '.bmp': 'image/bmp', '.dds': 'image/vnd-ms.dds' };
  return `data:${mime[extname(path).toLowerCase()] || 'application/octet-stream'};base64,${readFileSync(path).toString('base64')}`;
}

async function startWebEditor(kind: string, options: JsonObject): Promise<{ process: ChildProcessWithoutNullStreams; url: string; statePath: string }> {
  const folder = join(tmpdir(), 'nba2k_jersey_modder', 'electron', `${kind}_${Date.now()}_${Math.random().toString(16).slice(2)}`);
  mkdirSync(folder, { recursive: true });
  const statePath = join(folder, 'state.json');
  let tool = ''; const args: string[] = [];
  if (kind === 'layer') {
    const projectPath = join(folder, 'project.json'); writeFileSync(projectPath, JSON.stringify(options.project), 'utf8');
    tool = 'wpf_layer_web.py'; args.push('--project', projectPath, '--state', statePath);
  } else if (kind === 'logo' || kind === 'trim') {
    if (!options.reference || !existsSync(options.reference)) throw new Error('Choose a reference image first.');
    const initialPath = join(folder, 'initial.json');
    writeFileSync(initialPath, JSON.stringify({ items: options.items || [], selectedId: options.selectedId || null }), 'utf8');
    tool = kind === 'logo' ? 'wpf_logo_web.py' : 'wpf_trim_web.py';
    args.push('--reference', options.reference, '--state', statePath, '--initial-state', initialPath);
  } else if (kind === 'paths') {
    if (!options.pattern || !existsSync(options.pattern)) throw new Error('Choose a trim pattern first.');
    const projectPath = join(folder, 'project.json'); writeFileSync(projectPath, JSON.stringify(options.project), 'utf8');
    tool = 'wpf_trim_path_lab.py';
    args.push('--project', projectPath, '--pattern', options.pattern, '--state', statePath, '--project-folder', dirname(options.projectPath));
  } else throw new Error(`Unknown editor: ${kind}`);

  const child = spawn(findPython(), ['-u', join(root, 'tools', tool), ...args], { cwd: root, windowsHide: true });
  child.stderr.setEncoding('utf8'); child.stderr.on('data', (message: string) => console.error(`[${kind} editor] ${message.trimEnd()}`));
  const url = await new Promise<string>((resolveUrl, reject) => {
    let buffer = ''; const timer = setTimeout(() => reject(new Error('The web editor took too long to start.')), 20000);
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', (chunk: string) => {
      buffer += chunk; const newline = buffer.indexOf('\n'); if (newline < 0) return;
      clearTimeout(timer);
      try { resolveUrl(JSON.parse(buffer.slice(0, newline)).url); } catch { reject(new Error('The web editor returned an invalid address.')); }
    });
    child.on('exit', (code) => { clearTimeout(timer); if (code) reject(new Error('The web editor could not start.')); });
  });
  return { process: child, url, statePath };
}

async function openEditor(kind: string, options: JsonObject): Promise<JsonObject> {
  mainWindow?.webContents.send('app:status', `Opening ${kind === 'paths' ? 'Trim Path Lab' : `${kind} editor`}...`);
  const session = await startWebEditor(kind, options);
  const editor = new BrowserWindow({
    parent: mainWindow || undefined, width: 1500, height: 940, minWidth: 960, minHeight: 650,
    title: kind === 'layer' ? 'Jersey Modder - Layer Editor' : `Jersey Modder - ${kind}`,
    icon: join(root, 'wpf', 'JerseyModder.Wpf', 'Assets', 'app-icon.ico'),
    backgroundColor: '#f4f6f5',
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  await editor.loadURL(options.startInEditor ? `${session.url}edit` : session.url);
  let lastRevision = -1;
  const monitor = setInterval(() => {
    if (!existsSync(session.statePath)) return;
    try {
      const state = JSON.parse(readFileSync(session.statePath, 'utf8'));
      if (state.project && state.revision !== lastRevision) {
        lastRevision = state.revision ?? lastRevision + 1;
        mainWindow?.webContents.send('project:external-update', state.project);
      }
      if (state.returnRequested) editor.close();
    } catch { /* State may be between atomic updates. */ }
  }, 250);
  return await new Promise((resolveResult) => {
    editor.on('closed', () => {
      clearInterval(monitor); if (!session.process.killed) session.process.kill();
      let state: JsonObject | undefined;
      try { state = JSON.parse(readFileSync(session.statePath, 'utf8')); } catch { state = undefined; }
      mainWindow?.show(); mainWindow?.focus(); mainWindow?.webContents.send('app:status', 'Returned to Jersey Modder.');
      resolveResult({ kind, state, project: state?.project });
    });
  });
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1540, height: 940, minWidth: 1080, minHeight: 700, show: false,
    title: 'NBA 2K Jersey Modder', icon: join(root, 'wpf', 'JerseyModder.Wpf', 'Assets', 'app-icon.ico'),
    backgroundColor: '#f4f6f5',
    webPreferences: { preload: join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  mainWindow.removeMenu();
  if (MAIN_WINDOW_VITE_DEV_SERVER_URL) mainWindow.loadURL(MAIN_WINDOW_VITE_DEV_SERVER_URL);
  else mainWindow.loadFile(join(__dirname, `../renderer/${MAIN_WINDOW_VITE_NAME}/index.html`));
  mainWindow.once('ready-to-show', () => mainWindow?.show());
  if (process.env.JERSEY_MODDER_SCREENSHOT) {
    mainWindow.webContents.once('did-finish-load', () => setTimeout(async () => {
      if (!mainWindow) return;
      if (process.env.JERSEY_MODDER_TEST_PROJECT) {
        await mainWindow.webContents.executeJavaScript(`(() => {
          const input = document.querySelector('.startup-grid input');
          const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
          setter.call(input, ${JSON.stringify(process.env.JERSEY_MODDER_TEST_PROJECT)});
          input.dispatchEvent(new Event('input', { bubbles: true }));
          setTimeout(() => document.querySelector('.startup-grid .primary.command.full').click(), 100);
        })()`);
        await new Promise((resolveWait) => setTimeout(resolveWait, 4500));
      }
      const image = await mainWindow.webContents.capturePage();
      writeFileSync(process.env.JERSEY_MODDER_SCREENSHOT!, image.toPNG());
      app.quit();
    }, 1800));
  }
  mainWindow.on('closed', () => { mainWindow = null; });
}

ipcMain.handle('app:info', () => ({ version: app.getVersion(), root, projectsFolder }));
ipcMain.handle('project:list', () => {
  mkdirSync(projectsFolder, { recursive: true });
  const values: JsonObject[] = [];
  for (const folder of readdirSync(projectsFolder, { withFileTypes: true })) {
    if (!folder.isDirectory()) continue;
    const directory = join(projectsFolder, folder.name);
    for (const file of readdirSync(directory)) if (file.endsWith('.nba2kproject.json')) {
      const path = join(directory, file); values.push({ name: folder.name, path, modified: statSync(path).mtimeMs });
    }
  }
  return values.sort((a, b) => b.modified - a.modified);
});
ipcMain.handle('project:create', (_event, rawName: string) => {
  const name = safeName(rawName); if (!name) throw new Error('Enter a project name.');
  const path = join(projectsFolder, name, `${name}.nba2kproject.json`); if (existsSync(path)) throw new Error('A project with this name already exists.');
  const project = defaultProject(); saveProject(path, project); return { path, project };
});
ipcMain.handle('project:choose', async () => {
  mkdirSync(projectsFolder, { recursive: true });
  const result = await dialog.showOpenDialog(mainWindow!, { title: 'Open jersey project', defaultPath: projectsFolder, properties: ['openFile'], filters: [{ name: 'NBA 2K projects', extensions: ['json'] }] });
  if (result.canceled || !result.filePaths[0]) return null; const path = result.filePaths[0]; ensureProjectStructure(path); return { path, project: loadProject(path) };
});
ipcMain.handle('project:load', (_event, path: string) => ({ path, project: loadProject(path) }));
ipcMain.handle('project:save', (_event, payload: JsonObject) => saveProject(payload.path, payload.project));
ipcMain.handle('file:choose', async (_event, kind: string) => {
  const filters: Record<string, Electron.FileFilter[]> = {
    image: [{ name: 'Images', extensions: ['png', 'jpg', 'jpeg', 'webp', 'bmp', 'dds', 'psd'] }],
    logo: [{ name: 'Logo images', extensions: ['png', 'jpg', 'jpeg', 'webp', 'bmp'] }],
    trim: [{ name: 'Trim images', extensions: ['png', 'jpg', 'jpeg', 'webp', 'bmp'] }],
    iff: [{ name: 'NBA 2K IFF', extensions: ['iff'] }], rdat: [{ name: 'RDAT or IFF', extensions: ['rdat', 'iff'] }],
    project: [{ name: 'NBA 2K projects', extensions: ['json'] }],
  };
  const result = await dialog.showOpenDialog(mainWindow!, { defaultPath: kind === 'project' ? projectsFolder : undefined, properties: ['openFile'], filters: filters[kind] || filters.image });
  return result.canceled ? null : result.filePaths[0] || null;
});
ipcMain.handle('folder:choose', async () => { const result = await dialog.showOpenDialog(mainWindow!, { properties: ['openDirectory', 'createDirectory'] }); return result.canceled ? null : result.filePaths[0] || null; });
ipcMain.handle('file:save-dialog', async (_event, payload: JsonObject) => {
  const filters: Record<string, Electron.FileFilter[]> = { png: [{ name: 'PNG image', extensions: ['png'] }], dds: [{ name: 'DDS texture', extensions: ['dds'] }], psd: [{ name: 'Photoshop document', extensions: ['psd'] }], iff: [{ name: 'NBA 2K IFF', extensions: ['iff'] }], rdat: [{ name: 'RDAT', extensions: ['rdat'] }] };
  const result = await dialog.showSaveDialog(mainWindow!, { defaultPath: payload.suggestedName, filters: filters[payload.kind] }); return result.canceled ? null : result.filePath || null;
});
ipcMain.handle('asset:store', (_event, payload: JsonObject) => {
  if (!existsSync(payload.sourcePath)) throw new Error('The selected file no longer exists.'); ensureProjectStructure(payload.projectPath);
  const category = safeName(payload.category).toLowerCase(); const destinationFolder = category === 'references' ? join(dirname(payload.projectPath), 'references') : join(dirname(payload.projectPath), 'assets', category);
  mkdirSync(destinationFolder, { recursive: true }); const source = resolve(payload.sourcePath);
  if (dirname(source).toLowerCase() === destinationFolder.toLowerCase()) return source;
  const hash = createHash('sha256').update(readFileSync(source)).digest('hex').slice(0, 10); const destination = join(destinationFolder, `${safeName(payload.label).toLowerCase()}_${hash}${extname(source).toLowerCase()}`);
  if (!existsSync(destination)) copyFileSync(source, destination); return destination;
});
ipcMain.handle('file:data-url', (_event, path: string) => dataUrl(path));
ipcMain.handle('file:read-text', (_event, path: string) => readFileSync(path, 'utf8'));
ipcMain.handle('file:write-text', (_event, payload: JsonObject) => { writeFileSync(payload.path, payload.text, 'utf8'); });
ipcMain.handle('engine:call', (_event, payload: JsonObject) => engine.call(payload.method, payload.params));
ipcMain.handle('editor:open', (_event, payload: JsonObject) => openEditor(payload.kind, payload.options));
ipcMain.handle('shell:open', async (_event, path: string) => { if (/^https?:/i.test(path)) await shell.openExternal(path); else await shell.openPath(path); });
ipcMain.handle('blender:open', async (_event, project: JsonObject) => {
  const result = await engine.call('blender_prepare', { project }); if (!result.blender) throw new Error('Blender was not found.');
  spawn(result.blender, [result.model, '--python', result.script, '--', result.color, result.normal, '0.35', result.settings], { cwd: root, detached: true, windowsHide: false }).unref();
});
ipcMain.handle('logo:export-ai-pack', (_event, payload: JsonObject) => {
  const folder = resolve(String(payload.folder || ''));
  if (!folder) throw new Error('Choose a folder for the AI logo pack.');
  mkdirSync(folder, { recursive: true });
  const items = Array.isArray(payload.items) ? payload.items.filter((item) => item?.path && existsSync(item.path)) : [];
  if (!items.length) throw new Error('Stage at least one logo before exporting an AI pack.');
  const logoTypes: string[] = [];
  items.forEach((item, index) => {
    const label = String(item.typeLabel || 'Logo');
    logoTypes.push(label);
    const stem = safeName(label).replaceAll(' ', '_').toLowerCase() || 'logo';
    copyFileSync(item.path, join(folder, `${String(index + 1).padStart(2, '0')}_${stem}_logo_reference.png`));
  });
  const prompt = [
    'Clean up and redraw these basketball jersey logos as transparent PNGs.',
    `Logo type(s): ${logoTypes.join(', ')}.`,
    'Keep the same design, colors, proportions, outline thickness, and visual style.',
    'If a reference is photographed on curved fabric or at an angle, correct the perspective and warping so the finished logo is flat, level, and viewed straight-on.',
    'Straighten accidental skew, uneven baselines, and wavy edges, but preserve intentional arches, italic lettering, curves, and asymmetry that are part of the original design.',
    'Remove background noise, jagged edges, compression artifacts, and blur.',
    'Use a true transparent background with an alpha channel.',
    'Do not put the logo on white, black, gray, checkerboard, or any solid-color background.',
    'Do not redesign it, change the wording, add extra effects, or place it on a jersey mockup.',
    'Output size should be 1024 x 1024 pixels.',
    'Keep it centered with a small transparent padding area.',
    'Return one finished PNG per uploaded reference, keeping the same order as the file names.',
  ].join('\n');
  const promptPath = join(folder, 'ai_logo_prompt.txt');
  writeFileSync(promptPath, prompt, 'utf8');
  return { folder, count: items.length, prompt: promptPath };
});
ipcMain.handle('clipboard:write', (_event, text: string) => { clipboard.writeText(String(text || '')); });

app.whenReady().then(() => { mkdirSync(projectsFolder, { recursive: true }); engine.start(); createWindow(); app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); }); });
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
app.on('before-quit', () => engine.stop());
