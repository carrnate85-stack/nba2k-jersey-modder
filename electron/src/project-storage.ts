import { copyFileSync, existsSync, mkdirSync, readFileSync, renameSync, unlinkSync, openSync, writeSync, fsyncSync, closeSync } from 'node:fs';
import { dirname, isAbsolute, relative, resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import type { JsonObject } from './shared';

export function normalizeProject(payload: JsonObject, defaults: JsonObject): JsonObject {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) throw new Error('Project data must be an object.');
  if (Number(payload.projectVersion || 1) > defaults.projectVersion) throw new Error('This project requires a newer version of Jersey Modder.');
  const result = structuredClone(payload);
  const colors = result.generator?.colors;
  if (colors && typeof colors === 'object') {
    colors.shorts_left_panel_color ??= colors.left_panel_color ?? '';
    colors.shorts_right_panel_color ??= colors.right_panel_color ?? '';
  }
  const merge = (target: JsonObject, values: JsonObject) => {
    for (const [key, value] of Object.entries(values)) {
      if (target[key] === undefined || target[key] === null) target[key] = structuredClone(value);
      else if (value && typeof value === 'object' && !Array.isArray(value)) {
        if (typeof target[key] !== 'object' || Array.isArray(target[key])) throw new Error(`Invalid project field: ${key}`);
        merge(target[key], value);
      } else if (Array.isArray(value) && !Array.isArray(target[key])) throw new Error(`Invalid project list: ${key}`);
    }
  };
  merge(result, defaults);
  result.projectVersion = defaults.projectVersion;
  return result;
}

export function atomicWrite(path: string, text: string, backup = false): void {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.${randomUUID()}.tmp`;
  try {
    const fd = openSync(temporary, 'wx');
    try { writeSync(fd, text); fsyncSync(fd); } finally { closeSync(fd); }
    if (backup && existsSync(path)) copyFileSync(path, `${path}.bak`);
    renameSync(temporary, path);
  } finally { if (existsSync(temporary)) unlinkSync(temporary); }
}

export function readProject(path: string, defaults: JsonObject): JsonObject {
  return normalizeProject(mapPaths(JSON.parse(readFileSync(path, 'utf8')), value => /^(assets|references)[\\/]/.test(value) ? resolve(dirname(path), value) : value), defaults);
}

function mapPaths(value: any, transform: (value: string) => string): any {
  if (typeof value === 'string') return transform(value);
  if (Array.isArray(value)) return value.map(item => mapPaths(item, transform));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, mapPaths(item, transform)]));
  return value;
}

export function portableProject(project: JsonObject, path: string): JsonObject {
  return mapPaths(project, value => {
    if (!isAbsolute(value)) return value;
    const rel = relative(dirname(path), value);
    return /^(assets|references)[\\/]/.test(rel) ? rel.replaceAll('\\', '/') : value;
  });
}
