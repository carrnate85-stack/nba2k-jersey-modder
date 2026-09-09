import { existsSync, realpathSync } from 'node:fs';
import { dirname, isAbsolute, relative, resolve } from 'node:path';

function canonical(path: string): string {
  const absolute = resolve(path);
  if (existsSync(absolute)) return realpathSync(absolute);
  const parent = dirname(absolute);
  return parent === absolute ? absolute : resolve(canonical(parent), relative(parent, absolute));
}

export class FileAccess {
  private reads = new Set<string>();
  private writes = new Set<string>();
  private trees: { path: string; write: boolean }[] = [];
  grant(path: string, write = false): string {
    const value = canonical(path); this.reads.add(value.toLowerCase());
    if (write) this.writes.add(value.toLowerCase());
    return path;
  }
  grantTree(path: string, write = false): void { this.trees.push({ path: canonical(path), write }); }
  check(path: string, write = false): string {
    if (typeof path !== 'string' || !isAbsolute(path)) throw new Error('Choose a file using the file browser first.');
    const value = canonical(path);
    if ((write ? this.writes : this.reads).has(value.toLowerCase())) return path;
    if (this.trees.some(tree => {
      const rel = relative(tree.path, value);
      return (!write || tree.write) && !isAbsolute(rel) && rel !== '..' && !rel.startsWith(`..\\`) && !rel.startsWith('../');
    })) return path;
    throw new Error('This file is outside the current project. Choose it using the file browser first.');
  }
}
