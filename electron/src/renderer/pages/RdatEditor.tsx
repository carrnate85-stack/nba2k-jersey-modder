import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Aperture, Archive, Blend, Box, ChevronDown, ChevronRight, CircleOff, Download, Copy, FileImage, FileText, FolderOpen, Grid3X3, Image as ImageIcon, Layers3, Palette, Pipette, Play, Plus, RefreshCw, Save, Scissors, Search, Settings2, Shirt, SlidersHorizontal, Sparkles, Upload, WandSparkles, X, } from 'lucide-react';
import type { AppInfo, JsonObject, ProjectSummary } from '../../shared';
import { PageKey, PAGE_META, imageRows, jerseyColors, logoTypes, trimTypes, shortsColors, clone, filename, projectName, Nav, IconButton, PageHeader, Accordion, ColorRow, AssetRow, Range, PathImage, ColorControl, parseName, TweakSlider, extnameKind } from '../components';
export function RdatEditor({ status }: any) { const [source, setSource] = useState<string | null>(null); const [entry, setEntry] = useState<string | null>(null); const [encoding, setEncoding] = useState('utf-8'); const [text, setText] = useState(''); const open = async () => { const path = await window.jersey.chooseFile('rdat'); if (!path)
    return; try {
    const result = await window.jersey.engine('rdat_read', { path });
    setSource(path);
    setEntry(result.entry);
    setEncoding(result.encoding);
    setText(result.text);
    status(`Loaded ${result.entry || filename(path)} (${result.encoding}).`);
}
catch (error: any) {
    status(error.message);
} }; const save = async (as: boolean) => { if (!source)
    return; const destination = as ? await window.jersey.saveFile(extnameKind(source), filename(source)) : source; if (!destination)
    return; try {
    await window.jersey.engine('rdat_write', { source, destination, entry, encoding, text });
    setSource(destination);
    status(`Saved ${filename(destination)}.`);
}
catch (error: any) {
    status(error.message);
} }; return <div className="page"><PageHeader page="rdat" actions={<><button className="command" onClick={open}><FolderOpen />Open RDAT or IFF</button><button className="command" disabled={!source} onClick={() => save(false)}><Save />Save</button><button className="primary command" disabled={!source} onClick={() => save(true)}><Save />Save As</button></>}/><textarea className="text-editor" spellCheck={false} value={text} onChange={(event) => setText(event.target.value)} placeholder="Open an RDAT file or an IFF containing an RDAT entry."/></div>; }
