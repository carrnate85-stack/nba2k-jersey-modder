import { useEffect, useState } from 'react';
import { RefreshCw, Save, Layers3 } from 'lucide-react';
import { PageHeader, Range, filename } from '../components';
import { usePreview } from '../usePreview';

export function TextureCreator({ project, status }: any) {
  const [kind, setKind] = useState('Color Texture');
  const [strength, setStrength] = useState(15);
  const [saving, setSaving] = useState(false);
  const regionAvailable = project.generator.garment === 'Jersey';
  const effectiveKind = !regionAvailable && kind === 'Region Texture' ? 'Color Texture' : kind;
  useEffect(() => { if (!regionAvailable && kind === 'Region Texture') setKind('Color Texture'); }, [regionAvailable, kind]);
  const { image, busy, refresh } = usePreview('render', { project, kind: effectiveKind, strength }, status);
  const save = async (format: 'png' | 'dds' | 'psd') => {
    const path = await window.jersey.saveFile(format, `${project.generator.garment.toLowerCase()}_${effectiveKind.toLowerCase().replace(' texture', '')}.${format}`);
    if (!path) return;
    setSaving(true);
    try {
      await window.jersey.engine('save_texture', { project, path, kind: effectiveKind, format: `.${format}`, strength });
      status(`Saved ${filename(path)}.`);
    } catch (error: any) { status(error.message); } finally { setSaving(false); }
  };
  return <div className="page">
    <PageHeader page="texture" actions={<button className="command" onClick={refresh}><RefreshCw/>Refresh Preview</button>}/>
    <div className="editor-split">
      <div className="preview-panel"><div className="preview-toolbar">{busy ? 'Updating...' : effectiveKind}</div><div className="preview-stage">{image ? <img alt="Texture export preview" src={image}/> : <div className="preview-loading">Preparing texture...</div>}</div></div>
      <div className="right-controls"><section className="tool-panel">
        <label className="field"><span>Texture type</span><select value={effectiveKind} onChange={event => setKind(event.target.value)}>
          <option>Color Texture</option><option disabled={!regionAvailable}>Region Texture</option><option>Normal Texture</option>
        </select></label>
        {effectiveKind === 'Normal Texture' && <Range label="Logo and trim strength" value={strength} min={0} max={100} onChange={setStrength}/>}
        <div className="export-stack">
          <button className="primary command" disabled={saving} onClick={() => save('png')}><Save/>Save PNG As</button>
          <button className="command" disabled={saving} onClick={() => save('dds')}><Save/>Save DDS BC1 As</button>
          <button className="command" disabled={saving || effectiveKind !== 'Color Texture'} onClick={() => save('psd')}><Layers3/>Layered PSD Export</button>
        </div>
      </section></div>
    </div>
  </div>;
}
