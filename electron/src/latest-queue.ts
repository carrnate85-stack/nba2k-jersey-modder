type Work<T> = { run: () => Promise<T>; resolve: (value: T) => void; reject: (error: Error) => void };

// One running request and one replaceable pending request per preview surface.
export class LatestQueue {
  private active = new Set<string>();
  private waiting = new Map<string, Work<any>>();
  submit<T>(key: string, run: () => Promise<T>): Promise<T> {
    return new Promise((resolve, reject) => {
      const work = { run, resolve, reject };
      if (this.active.has(key)) {
        this.waiting.get(key)?.reject(new Error('Preview superseded'));
        this.waiting.set(key, work);
      } else { this.active.add(key); void this.execute(key, work); }
    });
  }
  private async execute(key: string, work: Work<any>): Promise<void> {
    try { work.resolve(await work.run()); } catch (error) { work.reject(error as Error); }
    const next = this.waiting.get(key);
    this.waiting.delete(key);
    if (next) void this.execute(key, next); else this.active.delete(key);
  }
}
