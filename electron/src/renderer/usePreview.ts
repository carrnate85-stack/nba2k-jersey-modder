import { useCallback, useEffect, useRef, useState } from 'react';
import type { JsonObject } from '../shared';
export function usePreview(method: string, params: JsonObject, status: (message: string) => void, enabled = true) {
  const [image, setImage] = useState('');
  const [busy, setBusy] = useState(false);
  const revision = useRef(0);
  const key = JSON.stringify(params);
  const refresh = useCallback(async () => {
    if (!enabled) return;
    const id = ++revision.current;
    setBusy(true);
    try {
      const result = await window.jersey.engine(method, JSON.parse(key));
      const url = await window.jersey.fileDataUrl(result.path || result.preview);
      if (revision.current === id) setImage(url);
    } catch (error: any) {
      if (revision.current === id && !error.message.includes('Preview superseded')) status(error.message);
    } finally { if (revision.current === id) setBusy(false); }
  }, [method, key, enabled, status]);
  useEffect(() => {
    revision.current++;
    const timer = setTimeout(refresh, 180);
    return () => { clearTimeout(timer); revision.current++; };
  }, [refresh]);
  return { image, busy, refresh };
}
