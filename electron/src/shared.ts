export type JsonObject = Record<string, any>;
export interface ProjectSummary { name: string; path: string; modified: number; }
export interface AppInfo { version: string; root: string; projectsFolder: string; }
export interface EditorResult { kind: string; state?: JsonObject; project?: JsonObject; }
export interface JerseyApi {
  appInfo(): Promise<AppInfo>;
  listProjects(): Promise<ProjectSummary[]>;
  createProject(name: string): Promise<{ path: string; project: JsonObject }>;
  chooseProject(): Promise<{ path: string; project: JsonObject } | null>;
  loadProject(path: string): Promise<{ path: string; project: JsonObject }>;
  saveProject(path: string, project: JsonObject): Promise<string>;
  chooseFile(kind: string): Promise<string | null>;
  chooseFolder(): Promise<string | null>;
  saveFile(kind: string, suggestedName: string): Promise<string | null>;
  storeAsset(projectPath: string, sourcePath: string, category: string, label: string): Promise<string>;
  fileDataUrl(path: string): Promise<string>;
  readText(path: string): Promise<string>;
  writeText(path: string, text: string): Promise<void>;
  engine(method: string, params?: JsonObject): Promise<any>;
  openEditor(kind: string, options: JsonObject): Promise<EditorResult>;
  openBlender(project: JsonObject): Promise<void>;
  exportAiLogoPack(items: JsonObject[], folder: string): Promise<{ folder: string; count: number; prompt: string }>;
  copyText(text: string): Promise<void>;
  openExternal(path: string): Promise<void>;
  onProjectUpdate(listener: (project: JsonObject) => void): () => void;
  onStatus(listener: (message: string) => void): () => void;
}
