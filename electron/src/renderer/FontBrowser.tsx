import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import { FolderOpen, X } from 'lucide-react';
import { usePreview } from './usePreview';

export function FontBrowser({ onLoad, onClose, status }: { onLoad: (path: string) => Promise<void>; onClose: () => void; status: (message: string) => void }) {
  const [root, setRoot] = useState('');
  const [entries, setEntries] = useState<any[]>([]);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const deferred = useDeferredValue(query.toLowerCase());
  const filtered = useMemo(() => entries.filter(entry => `${entry.team} ${entry.uniform} ${entry.name}`.toLowerCase().includes(deferred)), [entries, deferred]);
  const [limit, setLimit] = useState(100);
  useEffect(() => setLimit(100), [deferred]);
  const previewStatus = (message: string) => setError(message);
  const { image } = usePreview('font_preview', { root, entry: selected }, setError, Boolean(root && selected));
  const choose = async () => {
    const folder = await window.jersey.chooseFolder();
    if (!folder) return;
    setBusy(true); setError('');
    try {
      const result = await window.jersey.engine('font_catalog', { root: folder });
      setRoot(folder); setEntries(result.entries); setSelected(null);
    } catch (error: any) { setError(error.message); } finally { setBusy(false); }
  };
  const load = async (entry = selected) => {
    if (!entry || busy) return;
    setBusy(true); setError('');
    try {
      const result = await window.jersey.engine('font_open_manifest', { root, entry });
      await onLoad(result.source);
      status(`Loaded ${entry.team} ${entry.uniform}.`);
      onClose();
    } catch (error: any) { setError(error.message); } finally { setBusy(false); }
  };
  return <div className="modal-shade"><section className="font-browser" role="dialog" aria-modal="true" aria-label="Game number catalog">
    <div className="panel-title"><h2>Game Numbers</h2><button className="icon-button" aria-label="Close catalog" disabled={busy} onClick={onClose}><X/></button></div>
    <div className="browser-actions"><button className="command" disabled={busy} onClick={choose}><FolderOpen/>Choose NBA 2K26 Folder</button><input aria-label="Search numbers" placeholder="Search team, season, or filename" value={query} onChange={event => setQuery(event.target.value)}/></div>
    <div className="font-browser-grid"><div className="font-results">{filtered.slice(0,limit).map(entry => <button key={entry.name} className={selected?.name === entry.name ? 'selected' : ''} onClick={() => setSelected(entry)} onDoubleClick={() => load(entry)}><strong>{entry.team || entry.name}</strong><span>{entry.uniform || entry.name}</span><small>{entry.cached ? 'Cached' : 'Preview on selection'}</small></button>)}{filtered.length > limit && <button onClick={() => setLimit(limit + 100)}>Show more</button>}</div><div className="image-workspace">{image ? <img alt="Selected number sheet" src={image}/> : <span>Select a number set</span>}</div></div>
    <div role="status">{error || (busy ? 'Loading...' : `${filtered.length} number sets`)}</div>
    <button className="primary command" disabled={!selected || busy} onClick={() => load()}>Load Selected Numbers</button>
  </section></div>;
}
