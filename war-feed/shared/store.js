// A small rolling store: keeps the newest N items in memory, removes
// duplicates (same URL, or near-identical headline), and saves to a JSON
// file so a restart doesn't empty the page. Swap for a database later
// without changing the routes: they only call add(), list() and version.
import fs from 'node:fs';
import path from 'node:path';

const normTitle = (t) =>
  t.toLowerCase().replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim()
    .split(' ').filter((w) => w.length > 2).slice(0, 12).join(' ');

export class NewsStore {
  constructor({ file, maxItems = 2000, maxAgeHours = 72 }) {
    this.file = file;
    this.maxItems = maxItems;
    this.maxAgeMs = maxAgeHours * 3600e3;
    this.items = [];
    this.version = 0;
    this.lastRun = null;
    this.feedHealth = {};
    this.load();
  }

  load() {
    try {
      const data = JSON.parse(fs.readFileSync(this.file, 'utf8'));
      this.items = data.items ?? [];
      this.version = data.version ?? 0;
    } catch { /* first run */ }
  }

  save() {
    fs.mkdirSync(path.dirname(this.file), { recursive: true });
    const tmp = `${this.file}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify({ version: this.version, items: this.items }));
    fs.renameSync(tmp, this.file);
  }

  /** Adds new items, returns how many were new. */
  add(newItems) {
    const byId = new Set(this.items.map((i) => i.id));
    const byIdBefore = new Set(byId);
    const byTitle = new Map(this.items.map((i) => [normTitle(i.title), i]));
    let added = 0;
    for (const item of newItems) {
      if (byId.has(item.id)) continue;
      const key = normTitle(item.title);
      const dup = key && byTitle.get(key);
      if (dup) {
        // Same story from another outlet: record it as corroboration.
        dup.alsoReportedBy = [...new Set([...(dup.alsoReportedBy ?? []), item.outlet])].filter((o) => o !== dup.outlet);
        continue;
      }
      item.firstSeenAt = new Date().toISOString();
      this.items.push(item);
      byId.add(item.id);
      if (key) byTitle.set(key, item);
      added++;
    }
    const cutoff = Date.now() - this.maxAgeMs;
    this.items = this.items
      .filter((i) => Date.parse(i.publishedAt) >= cutoff)
      .sort((a, b) => Date.parse(b.publishedAt) - Date.parse(a.publishedAt))
      .slice(0, this.maxItems);
    added = this.items.filter((i) => !byIdBefore.has(i.id)).length; // new and still in range
    if (added) {
      this.version++;
      this.save();
    }
    return added;
  }

  /**
   * @param {{since?:string, limit?:number, filter?:(item)=>boolean}} opts
   */
  list({ since, limit = 100, filter } = {}) {
    let out = this.items;
    if (since) {
      const t = Date.parse(since);
      if (!Number.isNaN(t)) out = out.filter((i) => Date.parse(i.firstSeenAt ?? i.publishedAt) > t);
    }
    if (filter) out = out.filter(filter);
    return out.slice(0, Math.min(limit, 500));
  }
}
