import { FolderOpen, Save, Sparkles, Search } from 'lucide-react';
import { useState } from 'react';
import { FontBrowser } from '../FontBrowser';
import { ColorControl, PageHeader, Range, filename, parseName } from '../components';
import { usePreview } from '../usePreview';

export function NumberEditor({ project, projectPath, update, status }: any) {
  const [browsing, setBrowsing] = useState(false);
  const settings = project.numberEditor || {};
  const { source = null, fill = '', outline = '', edge = 0, thickness = 0 } = settings;
  const change = (key: string, value: any) => update((next: any) => { next.numberEditor = { ...next.numberEditor, [key]: value }; });
  const valid = [fill, outline].every(color => !color || /^#[0-9a-f]{6}$/i.test(color));
  const { image, busy } = usePreview('font_recolor', { source, fill: fill || null, outline: outline || null, edge, thickness }, status, Boolean(source) && valid);
  const open = async () => {
    const path = await window.jersey.chooseFile('iff');
    if (!path) return;
    try {
      const stored = await window.jersey.storeAsset(projectPath, path, 'numbers', 'number_source');
      await window.jersey.engine('font_open', { path: stored });
      change('source', stored);
      status(`Loaded ${filename(path)}.`);
    } catch (error: any) { status(error.message); }
  };
  const loadManifest = async (path: string) => {
    const stored = await window.jersey.storeAsset(projectPath, path, 'numbers', 'number_source');
    change('source', stored);
  };
  const save = async () => {
    const destination = await window.jersey.saveFile('iff', `${parseName(source)}_recolor.iff`);
    if (!destination) return;
    try {
      await window.jersey.engine('font_save', { source, destination, fill: fill || null, outline: outline || null, edge, thickness });
      status(`Saved ${filename(destination)}.`);
    } catch (error: any) { status(error.message); }
  };
  return <div className="page">
    <PageHeader page="number" actions={<><button className="command" onClick={() => setBrowsing(true)}><Search/>Browse Game Numbers</button><button className="command" onClick={open}><FolderOpen/>Open Font IFF</button><button className="primary command" disabled={!source || !valid} onClick={save}><Save/>Save Font IFF As</button></>}/>
    {browsing && <FontBrowser onLoad={loadManifest} onClose={() => setBrowsing(false)} status={status}/>}
    <div className="editor-split"><div className="preview-panel"><div className="preview-toolbar">{busy ? 'Updating...' : source ? filename(source) : 'Number preview'}</div><div className="preview-stage">{image ? <img alt="Number recolor preview" src={image}/> : <div className="preview-loading"><Sparkles/>Open a font IFF</div>}</div></div>
      <div className="right-controls"><section className="tool-panel"><h2>Recolor</h2>
        <ColorControl label="Fill" value={fill} setValue={(value: string) => change('fill', value)}/>
        <ColorControl label="Outline" value={outline} setValue={(value: string) => change('outline', value)}/>
        {!valid && <p role="alert">Enter a six-digit hex color, such as #ffffff.</p>}
        <Range label="Edge protection" value={edge} min={0} max={100} onChange={(value: number) => change('edge', value)}/>
        <Range label="Outline thickness" value={thickness} min={0} max={20} onChange={(value: number) => change('thickness', value)}/>
      </section></div>
    </div>
  </div>;
}
