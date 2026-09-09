import { FolderOpen, Save } from 'lucide-react';
import { PageHeader, TweakSlider, filename, parseName } from '../components';
export function TweakEditor({ project, projectPath, update, status }: any) {
  const settings = project.tweakEditor || {};
  const { source = null, lock = false } = settings;
  const values = settings.values || { x: 0, y: 0, width: 0, height: 0 };
  const open = async () => {
    const path = await window.jersey.chooseFile('iff');
    if (!path) return;
    try {
      const result = await window.jersey.engine('tweak_open', { path });
      const stored = await window.jersey.storeAsset(projectPath, path, 'tweaks', 'tweak_source');
      update((next: any) => { next.tweakEditor = { source: stored, lock, values: { x: result.x.value, y: result.y.value, width: result.width.value, height: result.height.value } }; });
      status(`Loaded ${filename(path)}.`);
    } catch (error: any) { status(error.message); }
  };
  const change = (key: string, value: number) => {
    const changed = { ...values, [key]: value };
    if (lock && key === 'width' && values.width !== 0) changed.height = values.height * value / values.width;
    if (lock && key === 'height' && values.height !== 0) changed.width = values.width * value / values.height;
    update((next: any) => { next.tweakEditor = { source, lock, values: changed }; });
  };
  const save = async () => {
    const destination = await window.jersey.saveFile('iff', `${parseName(source)}_edited.iff`);
    if (!destination) return;
    try { await window.jersey.engine('tweak_save', { source, destination, ...values }); status(`Saved ${filename(destination)}.`); }
    catch (error: any) { status(error.message); }
  };
  return <div className="page"><PageHeader page="tweak" actions={<><button className="command" onClick={open}><FolderOpen/>Open Tweak IFF</button><button className="primary command" disabled={!source} onClick={save}><Save/>Save Tweak IFF As</button></>}/>
    <section className="tool-panel tweak-panel"><div className="tweak-heading"><div><h2>Front number placement</h2><p>{source ? filename(source) : 'Open a tweak IFF to edit its front number.'}</p></div><label className="check"><input type="checkbox" checked={lock} onChange={event=>update((next: any)=>{next.tweakEditor={source,values,lock:event.target.checked};})}/>Lock proportions</label></div>
      <TweakSlider key={`${source}:x`} label="X position" help="Left moves number left, right moves number right" value={values.x} onChange={(value: number)=>change('x',value)}/>
      <TweakSlider key={`${source}:y`} label="Y position" help="Left moves number down, right moves number up" value={values.y} onChange={(value: number)=>change('y',value)}/>
      <TweakSlider key={`${source}:width`} label="Width" help="Left makes narrower, right makes wider" value={values.width} onChange={(value: number)=>change('width',value)}/>
      <TweakSlider key={`${source}:height`} label="Height" help="Left makes shorter, right makes taller" value={values.height} onChange={(value: number)=>change('height',value)}/>
    </section>
  </div>;
}
