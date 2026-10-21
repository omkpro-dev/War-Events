// One collection run for GitHub Actions. Reads the previous output from ./out
// (the war-data branch), adds new stories + claims, writes fresh files back.
import fs from 'node:fs';
process.env.WAR_STORE_FILE ??= 'out/war_feed.json';
process.env.CLAIMS_FILE ??= 'out/war_claims.json';
const { collectWar, warStore } = await import('./war-news/collector.js');
const { listClaims } = await import('./war-news/claims.js');
const { buildControl } = await import('./war-news/verify.js');

const r = await collectWar();
console.log('collect', r.stats);
warStore.save();   // always write, so the file exists on the first run
fs.writeFileSync('out/war_control.json', JSON.stringify(buildControl(listClaims())));
fs.writeFileSync('out/war_health.json', JSON.stringify({ at: new Date().toISOString(), stats: r.stats, feeds: warStore.feedHealth }, null, 1));
console.log('done');
