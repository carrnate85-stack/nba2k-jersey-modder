import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Aperture, Archive, Blend, Box, ChevronDown, ChevronRight, CircleOff, Download, Copy, FileImage, FileText, FolderOpen, Grid3X3, Image as ImageIcon, Layers3, Palette, Pipette, Play, Plus, RefreshCw, Save, Scissors, Search, Settings2, Shirt, SlidersHorizontal, Sparkles, Upload, WandSparkles, X, } from 'lucide-react';
import type { AppInfo, JsonObject, ProjectSummary } from '../../shared';
import { PageKey, PAGE_META, imageRows, jerseyColors, logoTypes, trimTypes, shortsColors, clone, filename, projectName, Nav, IconButton, PageHeader, Accordion, ColorRow, AssetRow, Range, PathImage, ColorControl, parseName, TweakSlider, extnameKind } from '../components';
export function Creator({ kind, project, projectPath, update, status, setPage }: any) {
    const isLogo = kind === "logo";
    const typeOptions: readonly (readonly [
        string,
        string
    ])[] = isLogo
        ? logoTypes
        : trimTypes;
    const creatorState = project.creators?.[kind] || {};
    const reference = creatorState.reference || null;
    const items: any[] = Array.isArray(creatorState.items)
        ? creatorState.items
        : [];
    const selected: string | null = creatorState.selectedId || null;
    const [referenceUrl, setReferenceUrl] = useState("");
    const [sampleColor, setSampleColor] = useState("#ffffff");
    const [assetTarget, setAssetTarget] = useState<string>(typeOptions[0][1]);
    const saveCreator = (changes: Record<string, any>) => update((next: any) => {
        next.creators ??= {};
        next.creators[kind] ??= {};
        Object.assign(next.creators[kind], changes);
    });
    useEffect(() => {
        let active = true;
        if (!reference) {
            setReferenceUrl("");
            return () => {
                active = false;
            };
        }
        window.jersey
            .fileDataUrl(reference)
            .then((value) => {
            if (active)
                setReferenceUrl(value);
        })
            .catch(() => {
            if (active)
                setReferenceUrl("");
        });
        return () => {
            active = false;
        };
    }, [reference]);
    const chooseReference = async () => {
        const source = await window.jersey.chooseFile(isLogo ? "logo" : "trim");
        if (!source)
            return;
        const stored = await window.jersey.storeAsset(projectPath, source, "references", `${kind}_reference`);
        saveCreator({ reference: stored });
    };
    const persistSessionItems = async (staged: any[]) => Promise.all(staged.map(async (item) => {
        const stored = await window.jersey.storeAsset(projectPath, item.path, isLogo ? "logos" : "trims", item.typeLabel || kind);
        let storedSource: string | null = null;
        if (item.sourcePath) {
            try {
                storedSource = await window.jersey.storeAsset(projectPath, item.sourcePath, isLogo ? "logos" : "trims", `${item.typeLabel || kind}_source`);
            }
            catch {
                storedSource = null;
            }
        }
        return {
            ...item,
            path: stored,
            thumbnailPath: stored,
            sourcePath: storedSource,
        };
    }));
    const open = async (editItemId?: string) => {
        if (!reference) {
            await chooseReference();
            return;
        }
        try {
            const result = await window.jersey.openEditor(kind, {
                reference,
                items,
                selectedId: editItemId || selected,
                startInEditor: Boolean(editItemId),
            });
            const staged = await persistSessionItems(result.state?.items || []);
            saveCreator({
                items: staged,
                selectedId: result.state?.selectedId || staged.at(-1)?.id || null,
            });
        }
        catch (error: any) {
            status(error.message);
        }
    };
    const importImage = async () => {
        const source = await window.jersey.chooseFile(isLogo ? "logo" : "trim");
        if (!source)
            return;
        try {
            const option = typeOptions.find((entry) => entry[1] === assetTarget) || typeOptions[0];
            const stored = await window.jersey.storeAsset(projectPath, source, isLogo ? "logos" : "trims", `imported_${option[0]}`);
            const item = {
                id: `imported-${Date.now()}-${Math.random().toString(16).slice(2)}`,
                typeLabel: option[0],
                target: option[1],
                path: stored,
                thumbnailPath: stored,
                sourcePath: stored,
                imported: true,
                scale: 1,
            };
            saveCreator({ items: [...items, item], selectedId: item.id });
            status(`Imported ${filename(stored)} as ${option[0]}.`);
        }
        catch (error: any) {
            status(error.message);
        }
    };
    const send = async () => {
        if (!items.length)
            return;
        try {
            const storedItems = await Promise.all(items.map(async (item) => ({
                item,
                stored: await window.jersey.storeAsset(projectPath, item.path, isLogo ? "logos" : "trims", item.typeLabel || kind),
            })));
            update((next: any) => {
                for (const { item, stored } of storedItems) {
                    if (!isLogo) {
                        if (item.target === "trim_path_pattern") {
                            continue;
                        }
                        next.generator.images[item.target] = stored;
                        continue;
                    }
                    if (item.target === "front_wordmark") {
                        next.generator.images.front_wordmark_image = stored;
                        next.generator.frontWordmark.lockAspect = true;
                        continue;
                    }
                    const placement = {
                        path: stored,
                        targetName: item.target || "front_center_chest_logo",
                        offsetX: 0,
                        offsetY: 0,
                        scalePercent: 100,
                        scaleWidthPercent: 100,
                        scaleHeightPercent: 100,
                        lockAspect: true,
                        stretchX: item.target === "wrap_across_front_back_logo",
                    };
                    const existing = next.generator.logos.findIndex((logo: any) => logo.path === stored && logo.targetName === placement.targetName);
                    if (existing >= 0)
                        next.generator.logos[existing] = placement;
                    else
                        next.generator.logos.push(placement);
                }
            });
            const destinations = storedItems
                .map(({ item }) => item.typeLabel || (isLogo ? "Logo" : "Trim"))
                .join(", ");
            const hasTrimPath = !isLogo && storedItems.some(({ item }) => item.target === "trim_path_pattern");
            status(hasTrimPath
                ? `Staged ${destinations}. Choose a Trim Path source on the Trim Path Lab tab when you are ready.`
                : `Sent to Generator: ${destinations}. Open the Web Layer Editor to position them.`);
            if (!hasTrimPath)
                setPage("generator");
        }
        catch (error: any) {
            status(error.message);
        }
    };
    const exportToAi = async () => {
        if (!isLogo || !items.length)
            return;
        const folder = await window.jersey.chooseFolder();
        if (!folder)
            return;
        try {
            const result = await window.jersey.exportAiLogoPack(items, folder);
            status(`AI logo pack saved with ${result.count} reference(s).`);
        }
        catch (error: any) {
            status(error.message);
        }
    };
    const pickColor = async () => {
        try {
            const EyeDropper = (window as any).EyeDropper;
            if (!EyeDropper) {
                status("Use the color swatch to choose a color on this system.");
                return;
            }
            const result = await new EyeDropper().open();
            setSampleColor(String(result.sRGBHex || "#ffffff").toLowerCase());
        }
        catch {
            /* Canceling the eyedropper is not an error. */
        }
    };
    const copyColor = async () => {
        await window.jersey.copyText(sampleColor.toUpperCase());
        status(`Copied ${sampleColor.toUpperCase()} to the clipboard.`);
    };
    const changeAssetType = (target: string) => {
        setAssetTarget(target);
        const option = typeOptions.find((entry) => entry[1] === target);
        if (!selected || !option)
            return;
        saveCreator({
            items: items.map((item) => item.id === selected
                ? { ...item, target: option[1], typeLabel: option[0] }
                : item),
        });
    };
    const removeItem = (item: any) => {
        if (!window.confirm(`Remove ${item.typeLabel || kind} from the staged list?\n\nThe saved image will remain in this project's ${isLogo ? "logos" : "trims"} folder.`))
            return;
        const remaining = items.filter((candidate) => candidate.id !== item.id);
        let nextSelected = selected;
        if (selected === item.id) {
            const next = remaining.at(-1);
            nextSelected = next?.id || null;
            if (next?.target)
                setAssetTarget(next.target);
        }
        saveCreator({ items: remaining, selectedId: nextSelected });
        status(`Removed ${filename(item.path)} from the staged list.`);
    };
    const duplicateTrim = (item: any) => {
        if (isLogo)
            return;
        const duplicate = {
            ...item,
            id: `duplicate-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        };
        const index = items.findIndex((candidate) => candidate.id === item.id);
        const nextItems = [...items];
        nextItems.splice(index < 0 ? nextItems.length : index + 1, 0, duplicate);
        saveCreator({ items: nextItems, selectedId: duplicate.id });
        setAssetTarget(duplicate.target || typeOptions[0][1]);
        status(`Duplicated ${item.typeLabel || "trim"}. Choose another trim type or edit the copy.`);
    };
    const current = items.find((item) => item.id === selected);
    return (<div className="page creator-page">
      <PageHeader page={kind as PageKey} actions={<>
            <div className="header-reference-color">
              <strong>Reference color</strong>
              <button className="icon-button" title="Pick from image" onClick={pickColor}>
                <Pipette />
              </button>
              <input type="color" value={sampleColor} onChange={(event) => setSampleColor(event.target.value)}/>
              <input className="hex" value={sampleColor} onChange={(event) => setSampleColor(event.target.value)}/>
              <button className="icon-button" title="Copy hex color" onClick={copyColor}>
                <Copy />
              </button>
            </div>
            <button className="primary command large-editor" onClick={() => open()}>
              <WandSparkles />
              {reference
                ? `Open Web ${isLogo ? "Logo" : "Trim"} Editor`
                : "Choose Reference and Start"}
            </button>
          </>}/>
      <div className="creator-grid">
        <div className="creator-left">
          <div className="reference-panel">
            <div className="panel-title">
              <strong>Reference</strong>
              <div>
                <IconButton title="Upload reference" onClick={chooseReference}>
                  <Upload />
                </IconButton>
                <IconButton title={`Import finished ${kind}`} onClick={importImage}>
                  <Plus />
                </IconButton>
              </div>
            </div>
            <div className="reference-image">
              {referenceUrl ? (<img src={referenceUrl}/>) : (<div>
                  <ImageIcon />
                  <span>Upload a uniform reference photo</span>
                </div>)}
            </div>
            <small>{filename(reference)}</small>
          </div>
          <div className="selected-preview">
            <strong>Selected {isLogo ? "logo" : "trim"}</strong>
            {current ? (<>
                <PathImage path={current.path}/>
                <span>{current.typeLabel}</span>
              </>) : (<div className="empty-preview">Select a staged item</div>)}
          </div>
        </div>
        <div className="creator-right">
          <section className="tool-panel">
            <h2>Staged {isLogo ? "Logos" : "Trims"}</h2>
            <p>
              Use the web editor for selection, or reimport a finished image
              directly into the staged list.
            </p>
            <div className={`stage-actions ${isLogo ? "three" : ""}`}>
              <button className="command" onClick={() => open()}>
                <WandSparkles />
                Reopen Web Editor
              </button>
              <button className="primary command" disabled={!items.length} onClick={send}>
                <Layers3 />
                Send Staged to Generator
              </button>
              {isLogo && (<button className="command" disabled={!items.length} onClick={exportToAi}>
                  <Download />
                  Export to AI
                </button>)}
            </div>
            <div className="creator-import">
              <label className="field">
                <span>{isLogo ? "Logo" : "Trim"} type</span>
                <select value={assetTarget} onChange={(event) => changeAssetType(event.target.value)}>
                  {typeOptions.map(([label, target]) => (<option key={target} value={target}>
                      {label}
                    </option>))}
                </select>
              </label>
              <button className="command" onClick={importImage}>
                <Upload />
                Import Finished {isLogo ? "Logo" : "Trim"}
              </button>
            </div>
            <div className="staged-list">
              {items.length ? (items.map((item) => (<div className={`staged-item ${!isLogo ? "has-duplicate" : ""} ${item.id === selected ? "selected" : ""}`} key={item.id}>
                    <button className="staged-select" onClick={() => {
                saveCreator({ selectedId: item.id });
                setAssetTarget(item.target || typeOptions[0][1]);
            }} onDoubleClick={() => open(item.id)} title={`Double-click to edit ${item.typeLabel || kind}`}>
                      <FileImage />
                      <span>
                        <strong>{item.typeLabel}</strong>
                        <small>{filename(item.path)}</small>
                      </span>
                      <ChevronRight />
                    </button>
                    {!isLogo && (<button className="staged-duplicate" title={`Duplicate ${item.typeLabel || "trim"}`} onClick={() => duplicateTrim(item)}>
                        <Copy />
                      </button>)}
                    <button className="staged-edit" title={`Edit ${item.typeLabel || kind}`} onClick={() => open(item.id)}>
                      <SlidersHorizontal />
                      <span>Edit</span>
                    </button>
                    <button className="staged-remove" title={`Remove ${item.typeLabel || kind}`} onClick={() => removeItem(item)}>
                      <X />
                    </button>
                  </div>))) : (<div className="no-items">
                  Nothing staged yet. Select multiple{" "}
                  {isLogo
                ? "logos with the lasso or box tool"
                : "trim lines with the two-point selector"}{" "}
                  in the web editor, or import a finished image above.
                </div>)}
            </div>
          </section>
        </div>
      </div>
    </div>);
}
