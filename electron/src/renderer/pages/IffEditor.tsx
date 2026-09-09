import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Aperture, Archive, Blend, Box, ChevronDown, ChevronRight, CircleOff, Download, Copy, FileImage, FileText, FolderOpen, Grid3X3, Image as ImageIcon, Layers3, Palette, Pipette, Play, Plus, RefreshCw, Save, Scissors, Search, Settings2, Shirt, SlidersHorizontal, Sparkles, Upload, WandSparkles, X, } from 'lucide-react';
import type { AppInfo, JsonObject, ProjectSummary } from '../../shared';
import { PageKey, PAGE_META, imageRows, jerseyColors, logoTypes, trimTypes, shortsColors, clone, filename, projectName, Nav, IconButton, PageHeader, Accordion, ColorRow, AssetRow, Range, PathImage, ColorControl, parseName, TweakSlider, extnameKind } from '../components';
export function IffEditor({ status }: any) { const [source, setSource] = useState<string | null>(null); const [rows, setRows] = useState<any[]>([]); const open = async () => { const path = await window.jersey.chooseFile('iff'); if (!path)
    return; try {
    const result = await window.jersey.engine('iff_scan', { path });
    setSource(path);
    setRows(result.pairs);
    status(`Loaded ${filename(path)}: ${result.pairs.length} texture pair(s).`);
}
catch (error: any) {
    status(error.message);
} }; return <div className="page"><PageHeader page="iff" actions={<button className="primary command" onClick={open}><FolderOpen />Import IFF</button>}/><section className="tool-panel table-panel"><div className="source-line"><strong>{source ? filename(source) : 'No IFF loaded'}</strong><span>{rows.length} resource pair(s)</span></div><div className="data-table"><div className="table-head"><span>Texture</span><span>DDS</span><span>TXTR</span><span>Status</span></div>{rows.map((row, index) => <div className="table-row" key={`${row.key}-${index}`}><span>{row.key}</span><span>{row.dds?.name || ''}</span><span>{row.txtr?.name || ''}</span><span>{row.status}</span></div>)}</div></section></div>; }
