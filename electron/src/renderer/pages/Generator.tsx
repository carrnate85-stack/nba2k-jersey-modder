import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Aperture, Archive, Blend, Box, ChevronDown, ChevronRight, CircleOff, Download, Copy, FileImage, FileText, FolderOpen, Grid3X3, Image as ImageIcon, Layers3, Palette, Pipette, Play, Plus, RefreshCw, Save, Scissors, Search, Settings2, Shirt, SlidersHorizontal, Sparkles, Upload, WandSparkles, X, } from 'lucide-react';
import type { AppInfo, JsonObject, ProjectSummary } from '../../shared';
import { usePreview } from '../usePreview';
import { PageKey, PAGE_META, imageRows, jerseyColors, logoTypes, trimTypes, shortsColors, clone, filename, projectName, Nav, IconButton, PageHeader, Accordion, ColorRow, AssetRow, Range, PathImage, ColorControl, parseName, TweakSlider, extnameKind } from '../components';
export function Generator({ project, projectPath, update, setPage, status }: any) {
    const { image: preview, busy: rendering, refresh: render } = usePreview('render', { project, kind: 'preview' }, status);
    const openEditor = async () => { try {
        const result = await window.jersey.openEditor('layer', { project, projectPath });
        if (result.project)
            update((next: any) => Object.assign(next, result.project));
    }
    catch (error: any) {
        status(error.message);
    } };
    const colors = project.generator.garment === 'Shorts' ? shortsColors : jerseyColors;
    const visibleImages: (readonly [
        string,
        string
    ])[] = imageRows.filter(([key]) => project.generator.garment === 'Jersey' ? !key.startsWith('shorts_') && key !== 'waistband_image' : key.startsWith('shorts_') || key === 'waistband_image');
    if (project.generator.garment === 'Jersey')
        visibleImages.splice(1, 0, ['wrap_across_front_back_logo', 'Wrap image']);
    const visibleLogoTypes = logoTypes.filter(([, target]) => project.generator.garment === 'Shorts' ? target === 'shorts_belt_buckle_logo' : target !== 'shorts_belt_buckle_logo' && target !== 'wrap_across_front_back_logo');
    const setColor = (key: string, value: string) => update((next: any) => { next.generator.colors[key] = value; });
    const chooseImage = async (key: string, label: string) => { const source = await window.jersey.chooseFile('image'); if (!source)
        return; const stored = await window.jersey.storeAsset(projectPath, source, key.includes('trim') || key.includes('waistband') ? 'trims' : 'logos', label); update((next: any) => { next.generator.images[key] = stored; }); };
    const chooseLogo = async (target: string, label: string) => { const source = await window.jersey.chooseFile('logo'); if (!source)
        return; const stored = await window.jersey.storeAsset(projectPath, source, 'logos', label); update((next: any) => { if (target === 'front_wordmark') {
        next.generator.images.front_wordmark_image = stored;
        next.generator.frontWordmark.lockAspect = true;
        return;
    } const placement = { path: stored, targetName: target, offsetX: 0, offsetY: 0, scalePercent: 100, scaleWidthPercent: 100, scaleHeightPercent: 100, lockAspect: true, stretchX: target === 'wrap_across_front_back_logo' }; const existing = next.generator.logos.findIndex((logo: any) => logo.targetName === target); if (existing >= 0)
        next.generator.logos[existing] = placement;
    else
        next.generator.logos.push(placement); }); };
    const logoPath = (target: string) => target === 'front_wordmark' ? project.generator.images.front_wordmark_image : project.generator.logos.find((logo: any) => logo.targetName === target)?.path || null;
    const clearLogo = (target: string) => update((next: any) => { if (target === 'front_wordmark')
        next.generator.images.front_wordmark_image = null;
    else
        next.generator.logos = next.generator.logos.filter((logo: any) => logo.targetName !== target); });
    return <div className="page generator-page"><PageHeader page="generator" actions={<button className="primary command wide-editor" onClick={openEditor}><Layers3 />Open Web Layer Editor</button>}/><div className="generator-grid"><div className="control-rail"><Accordion title="Preview Aids" open summary="Preview only"><label className="check"><input type="checkbox" checked={project.generator.uvOverlay.enabled} onChange={(event) => update((next: any) => { next.generator.uvOverlay.enabled = event.target.checked; })}/>Show UV overlay</label>{project.generator.uvOverlay.enabled && <><label className="field"><span>UV line color</span><select value={project.generator.uvOverlay.color === 'white' ? 'white' : 'black'} onChange={(event) => update((next: any) => { next.generator.uvOverlay.color = event.target.value; })}><option value="black">Black</option><option value="white">White</option></select></label><Range label="UV opacity" value={project.generator.uvOverlay.opacity} min={0} max={100} onChange={(value: number) => update((next: any) => { next.generator.uvOverlay.opacity = value; })}/></>}<button className="primary command full" onClick={render}><RefreshCw />Generate Preview</button></Accordion><Accordion title="Colors" summary={<span className="color-summary">{colors.map(([key]) => <i key={key} style={{background: project.generator.colors[key] || "transparent"}}/>)}</span>}>{colors.map(([key, label]: any) => <ColorRow key={key} label={label} value={project.generator.colors[key] || ''} onChange={(value: string) => setColor(key, value)} allowNone={key.includes('panel')}/>)}</Accordion><Accordion title="Base Images" summary={`${visibleImages.filter(([key]) => key === "wrap_across_front_back_logo" ? logoPath(key) : project.generator.images[key]).length} loaded`}>{visibleImages.map(([key, label]) => key === 'wrap_across_front_back_logo' ? <AssetRow key={key} label={label} path={logoPath(key)} choose={() => chooseLogo(key, label)} clear={() => clearLogo(key)}/> : <AssetRow key={key} label={label} path={project.generator.images[key]} choose={() => chooseImage(key, label)} clear={() => update((next: any) => { next.generator.images[key] = null; })}/>)}</Accordion><Accordion title="Logos" summary={`${visibleLogoTypes.filter(([, target]) => logoPath(target)).length} loaded`}>{visibleLogoTypes.map(([label, target]) => <AssetRow key={target} label={label} path={logoPath(target)} choose={() => chooseLogo(target, label)} clear={() => clearLogo(target)}/>)}</Accordion><Accordion title="Trim Paths"><p className="muted">{project.generator.trimPathLayers.filter((item: any) => item.garment === project.generator.garment).length} path layer(s) for this garment.</p><button className="command full" onClick={() => setPage('paths')}><Blend />Open Trim Path Lab</button></Accordion><Accordion title="Preview Number"><label className="check"><input type="checkbox" checked={project.generator.numberPreview.enabled && project.generator.garment === 'Jersey'} disabled={project.generator.garment === 'Shorts'} onChange={(event) => update((next: any) => { next.generator.numberPreview.enabled = event.target.checked; })}/>Show in previews only</label><label className="field"><span>Number</span><input maxLength={4} value={project.generator.numberPreview.text} onChange={(event) => update((next: any) => { next.generator.numberPreview.text = event.target.value; })}/></label></Accordion></div><div className="preview-panel"><div className="preview-toolbar"><span>{rendering ? 'Updating preview...' : `${project.generator.garment} / ${project.generator.garment === 'Jersey' ? project.generator.jerseyCut : project.generator.shortsTemplate}`}</span><button onClick={render} title="Refresh preview"><RefreshCw /></button></div><div className="preview-stage">{preview ? <img src={preview}/> : <div className="preview-loading"><RefreshCw />Preparing preview...</div>}</div></div></div></div>;
}
