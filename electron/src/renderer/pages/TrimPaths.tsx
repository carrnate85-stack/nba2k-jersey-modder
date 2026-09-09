import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Aperture, Archive, Blend, Box, ChevronDown, ChevronRight, CircleOff, Download, Copy, FileImage, FileText, FolderOpen, Grid3X3, Image as ImageIcon, Layers3, Palette, Pipette, Play, Plus, RefreshCw, Save, Scissors, Search, Settings2, Shirt, SlidersHorizontal, Sparkles, Upload, WandSparkles, X, } from 'lucide-react';
import type { AppInfo, JsonObject, ProjectSummary } from '../../shared';
import { PageKey, PAGE_META, imageRows, jerseyColors, logoTypes, trimTypes, shortsColors, clone, filename, projectName, Nav, IconButton, PageHeader, Accordion, ColorRow, AssetRow, Range, PathImage, ColorControl, parseName, TweakSlider, extnameKind } from '../components';
export function TrimPaths({ project, projectPath, update, status }: any) {
    const stagedPatterns: any[] = (project.creators?.trim?.items || []).filter((item: any) => item.target === 'trim_path_pattern' && item.path);
    const pattern: string | null = project.generator.trimPathPattern || null;
    const selectPattern = (path: string) => {
        update((next: any) => { next.generator.trimPathPattern = path || null; });
        if (path)
            status(`Selected ${filename(path)} for the Trim Path Lab.`);
    };
    const choose = async (): Promise<string | null> => {
        const source = await window.jersey.chooseFile('trim');
        if (!source)
            return null;
        const stored = await window.jersey.storeAsset(projectPath, source, 'trims', 'trim_path_pattern');
        selectPattern(stored);
        status(`Loaded ${filename(stored)} as the Trim Path pattern.`);
        return stored;
    };
    const clear = () => update((next: any) => { next.generator.trimPathPattern = null; });
    const open = async () => {
        if (!pattern) {
            status('Select a staged Trim Path source before opening the web lab.');
            return;
        }
        try {
            const editorProject = clone(project);
            editorProject.generator.trimPathPattern = pattern;
            const result = await window.jersey.openEditor('paths', { project: editorProject, projectPath, pattern });
            if (result.project)
                update((next: any) => Object.assign(next, result.project));
        }
        catch (error: any) {
            status(error.message);
        }
    };
    const patternIsStaged = stagedPatterns.some((item) => item.path === pattern);
    return <div className="page"><PageHeader page="paths" actions={<button className="primary command large-editor" disabled={!pattern} onClick={open}><Blend />Open Web Trim Path Lab</button>}/><div className="two-column"><section className="tool-panel trim-source-panel"><h2>Trim source</h2><p>Choose one of the strips staged as Trim Path in Trim Creator, then open the web lab.</p><label className="field"><span>Staged Trim Paths</span><select value={pattern || ''} onChange={(event) => selectPattern(event.target.value)}><option value="">Select a staged trim...</option>{pattern && !patternIsStaged && <option value={pattern}>Imported: {filename(pattern)}</option>}{stagedPatterns.map((item, index) => <option key={item.id || `${item.path}-${index}`} value={item.path}>{index + 1}. {filename(item.path)}</option>)}</select></label><div className="trim-source-preview">{pattern ? <PathImage path={pattern}/> : <div className="empty-preview">No Trim Path source selected</div>}</div><AssetRow label="Import another trim pattern" path={pattern} choose={choose} clear={clear}/><p className="muted">The selected pattern bends continuously along straight segments, smooth curves, T junctions, and mirrored paths.</p></section><section className="tool-panel"><h2>Current project paths</h2><div className="stat-number">{project.generator.trimPathLayers.filter((item: any) => item.garment === project.generator.garment).length}</div><p>{project.generator.garment} trim path layer(s) on {project.generator.garment === 'Jersey' ? project.generator.jerseyCut : project.generator.shortsTemplate}.</p><button className="command full" disabled={!pattern} onClick={open}><Play />Open Selected Trim Path</button></section></div></div>;
}
