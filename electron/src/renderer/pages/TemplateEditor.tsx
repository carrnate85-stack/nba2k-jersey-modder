import { useEffect, useState } from 'react';
import { Save, X } from 'lucide-react';
import { PageHeader, filename } from '../components';

export function TemplateEditor({ status }: any) {
  const [catalog, setCatalog] = useState<any>(null);
  const [garment, setGarment] = useState('Jersey');
  const [variant, setVariant] = useState('Retro U');
  const [map, setMap] = useState('Jersey color');
  const [data, setData] = useState<any>(null);
  const [preview, setPreview] = useState('');
  const [edit, setEdit] = useState<any>(null);
  const variants = Object.keys(catalog?.[garment] || {});
  const selectedVariant = variants.includes(variant) ? variant : variants[0];
  const maps = catalog?.[garment]?.[selectedVariant] || [];
  const selectedMap = maps.includes(map) ? map : maps[0];
  useEffect(() => { window.jersey.engine('template_catalog').then(setCatalog).catch(error => status(error.message)); }, [status]);
  useEffect(() => {
    if (!selectedVariant || !selectedMap) return;
    let active = true;
    setData(null); setEdit(null);
    window.jersey.engine('template_load', { garment, variant: selectedVariant, map: selectedMap }).then(async result => {
      const image = await window.jersey.fileDataUrl(result.image);
      if (active) { setData(result); setPreview(image); }
    }).catch(error => { if (active) status(error.message); });
    return () => { active = false; };
  }, [garment, selectedVariant, selectedMap, status]);
  const save = async () => {
    const path = await window.jersey.saveFile('json', filename(data.zonesPath));
    if (!path) return;
    try { await window.jersey.engine('template_save', { path, image: data.image, zones: data.zones }); status(`Saved ${data.zones.length} zones.`); }
    catch (error: any) { status(error.message); }
  };
  const apply = () => {
    const zone = edit.zone;
    if (!zone.name.trim() || !/^#[0-9a-f]{6}$/i.test(zone.color) || !['x','y','width','height'].every(key => Number.isInteger(zone[key])) || zone.width <= 0 || zone.height <= 0) { status('Enter a name, hex color, and valid coordinates. Width and height must be positive.'); return; }
    if (data.zones.some((other: any, index: number) => index !== edit.index && other.name === zone.name)) { status('Zone names must be unique.'); return; }
    setData({ ...data, zones: data.zones.map((other: any, index: number) => index === edit.index ? zone : other) });
    setEdit(null); status('Zone updated. Save the zone map to keep these changes.');
  };
  return <div className="page"><PageHeader page="template" actions={<button className="primary command" disabled={!data} onClick={save}><Save/>Save Zone Map As</button>}/>
    <div className="template-controls">
      <label className="field"><span>Garment</span><select value={garment} onChange={event=>setGarment(event.target.value)}><option>Jersey</option><option>Shorts</option></select></label>
      <label className="field"><span>Template</span><select value={selectedVariant || ''} onChange={event=>setVariant(event.target.value)}>{variants.map(item=><option key={item}>{item}</option>)}</select></label>
      <label className="field"><span>Map</span><select value={selectedMap || ''} onChange={event=>setMap(event.target.value)}>{maps.map((item: string)=><option key={item}>{item}</option>)}</select></label>
    </div>
    <div className="template-grid"><div className="image-workspace">{preview && <img alt="Master template" src={preview}/>}</div><div className="zone-list">{data?.zones.map((zone: any,index: number)=><button key={index} onClick={()=>setEdit({index,zone:{...zone}})}><span className="swatch" style={{background:zone.color}}/><span><strong>{zone.name}</strong><small>{zone.x}, {zone.y} / {zone.width} x {zone.height} · {zone.color}</small></span></button>)}</div></div>
    {edit && <div className="modal-shade"><section className="zone-dialog" role="dialog" aria-modal="true" aria-label="Edit zone"><div className="panel-title"><h2>Edit Zone</h2><button className="icon-button" aria-label="Cancel zone edit" onClick={()=>setEdit(null)}><X/></button></div>
      <label className="field"><span>Name</span><input value={edit.zone.name} onChange={event=>setEdit({...edit,zone:{...edit.zone,name:event.target.value}})}/></label>
      <div className="zone-fields">{['x','y','width','height'].map(key=><label className="field" key={key}><span>{key}</span><input type="number" value={edit.zone[key]} onChange={event=>setEdit({...edit,zone:{...edit.zone,[key]:event.target.value === '' ? '' : Number(event.target.value)}})}/></label>)}</div>
      <label className="field"><span>Hex color</span><input value={edit.zone.color} onChange={event=>setEdit({...edit,zone:{...edit.zone,color:event.target.value}})}/></label>
      <button className="primary command full" onClick={apply}>Apply Zone Edits</button>
    </section></div>}
  </div>;
}
