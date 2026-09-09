import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Aperture, Archive, Blend, Box, ChevronDown, ChevronRight, CircleOff, Download, Copy, FileImage, FileText, FolderOpen, Grid3X3, Image as ImageIcon, Layers3, Palette, Pipette, Play, Plus, RefreshCw, Save, Scissors, Search, Settings2, Shirt, SlidersHorizontal, Sparkles, Upload, WandSparkles, X, } from 'lucide-react';
import type { AppInfo, JsonObject, ProjectSummary } from '../shared';
export type PageKey = 'generator' | 'logo' | 'trim' | 'paths' | 'number' | 'tweak' | 'texture' | 'iff' | 'rdat' | 'template';
export const PAGE_META: Record<PageKey, {
    label: string;
    icon: typeof Shirt;
    description: string;
}> = {
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
export const imageRows = [
    ['jersey_background_image', 'Background jersey image'],
    ['left_panel_image', 'Left side panel'], ['right_panel_image', 'Right side panel'],
    ['shorts_left_panel_image', 'Left shorts panel'], ['shorts_right_panel_image', 'Right shorts panel'],
    ['collar_trim_image', 'Collar trim'], ['left_arm_hole_trim_image', 'Left armhole trim'],
    ['right_arm_hole_trim_image', 'Right armhole trim'], ['waistband_image', 'Waistband image'],
] as const;
export const jerseyColors = [
    ['front_color', 'Front base'], ['back_color', 'Back base'], ['collar_background_color', 'Collar background'],
    ['left_panel_color', 'Left side panel'], ['right_panel_color', 'Right side panel'],
    ['collar_trim_color', 'Collar trim'], ['left_arm_hole_trim_color', 'Left armhole'], ['right_arm_hole_trim_color', 'Right armhole'],
] as const;
export const logoTypes = [
    ['Front Wordmark', 'front_wordmark'], ['Center Chest Logo', 'front_center_chest_logo'],
    ['Left Chest Logo', 'front_left_chest_logo'], ['Right Chest Logo', 'front_right_chest_logo'],
    ['Wrap Image', 'wrap_across_front_back_logo'], ['Back Neck Logo', 'back_neck_logo'],
    ['Back Center Logo', 'back_center_logo'], ['Belt Buckle Logo', 'shorts_belt_buckle_logo'],
] as const;
export const trimTypes = [
    ['Collar Trim', 'collar_trim_image'], ['Left Arm Hole Trim', 'left_arm_hole_trim_image'],
    ['Right Arm Hole Trim', 'right_arm_hole_trim_image'], ['Waistband', 'waistband_image'],
    ['Trim Path', 'trim_path_pattern'],
] as const;
export const shortsColors = [
    ['shorts_left_panel_color', 'Left shorts panel'], ['shorts_right_panel_color', 'Right shorts panel'],
    ['waistband_color', 'Waistband'],
] as const;
export function clone<T>(value: T): T { return structuredClone(value); }
export function filename(path?: string | null): string { return path ? path.replaceAll('\\', '/').split('/').pop() || path : 'None selected'; }
export function projectName(path?: string | null): string { return filename(path).replace('.nba2kproject.json', '').replace('.json', '') || 'Untitled project'; }
export function Nav({ active, item, onClick, compact }: {
    active: boolean;
    item: {
        label: string;
        icon: typeof Shirt;
    };
    onClick: () => void;
    compact?: boolean;
}) { const Icon = item.icon; return <button className={`nav-item ${active ? 'active' : ''} ${compact ? 'compact' : ''}`} onClick={onClick}><Icon /><span>{item.label}</span></button>; }
export function IconButton({ title, onClick, disabled, children }: any) { return <button className="icon-button" title={title} aria-label={title} disabled={disabled} onClick={onClick}>{children}</button>; }
export function PageHeader({ page, actions }: {
    page: PageKey;
    actions?: any;
}) { const meta = PAGE_META[page]; return <div className="page-header"><div><h1>{meta.label}</h1><p>{meta.description}</p></div>{actions && <div className="page-actions">{actions}</div>}</div>; }
export function Accordion({ title, children, open = false, summary }: any) { const [expanded, setExpanded] = useState(open); return <section className="accordion"><button className="accordion-head" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{expanded ? <ChevronDown /> : <ChevronRight />}<span>{title}</span>{summary && <small className="accordion-summary">{summary}</small>}</button>{expanded && <div className="accordion-body">{children}</div>}</section>; }
export function ColorRow({ label, value, onChange, allowNone }: any) { const active = value || '#ffffff'; return <div className="color-row"><span>{label}</span>{allowNone ? <button className={`none-color ${!value ? 'selected' : ''}`} title="No color" onClick={() => onChange('')}><CircleOff /></button> : <span className="none-color-spacer" aria-hidden="true"/>}<input className="hex" value={value || ''} placeholder="No color" onChange={(event) => onChange(event.target.value)}/><input type="color" value={active} onChange={(event) => onChange(event.target.value)}/></div>; }
export function AssetRow({ label, path, choose, clear }: any) { return <div className="asset-row"><div><strong>{label}</strong><small title={path}>{filename(path)}</small></div><IconButton title={`Choose ${label}`} onClick={choose}><Upload /></IconButton><IconButton title={`Clear ${label}`} disabled={!path} onClick={clear}><X /></IconButton></div>; }
export function Range({ label, value, min, max, onChange }: any) { return <label className="range"><span>{label}</span><input type="range" min={min} max={max} value={value} onChange={(event) => onChange(Number(event.target.value))}/><input type="number" min={min} max={max} value={value} onChange={(event) => onChange(Number(event.target.value))}/></label>; }
export function PathImage({ path }: {
    path: string;
}) { const [src, setSrc] = useState(''); useEffect(() => { let active = true; window.jersey.fileDataUrl(path).then((value) => active && setSrc(value)).catch(() => setSrc('')); return () => { active = false; }; }, [path]); return src ? <img src={src}/> : <div className="empty-preview">Loading preview...</div>; }
export function ColorControl({ label, value, setValue }: any) { return <div className="color-control"><div><strong>{label}</strong><label className="check"><input type="checkbox" checked={!value} onChange={(event) => setValue(event.target.checked ? '' : '#ffffff')}/>No change</label></div><div><input aria-label={`${label} hex color`} className="hex" value={value} placeholder="#ffffff" onChange={(event) => setValue(event.target.value)}/><input aria-label={`${label} color`} type="color" value={/^#[0-9a-f]{6}$/i.test(value) ? value : '#ffffff'} onChange={(event) => setValue(event.target.value)}/></div></div>; }
export function parseName(path: string) { const base = filename(path); return base.includes('.') ? base.slice(0, base.lastIndexOf('.')) : base; }
export function TweakSlider({ label, help, value, onChange }: any) {
    const [center] = useState(value);
    return <div className="tweak-row"><div><strong>{label}</strong><small>{help}</small></div><input aria-label={label} type="range" min={Math.min(center - 2, value)} max={Math.max(center + 2, value)} step="0.001" value={value} onChange={event => onChange(Number(event.target.value))}/><input aria-label={`${label} value`} type="number" step="0.001" value={value} onChange={event => { if (event.target.value !== '' && Number.isFinite(event.target.valueAsNumber)) onChange(event.target.valueAsNumber); }}/></div>;
}
export function extnameKind(path: string): string { return path.toLowerCase().endsWith('.iff') ? 'iff' : 'rdat'; }
