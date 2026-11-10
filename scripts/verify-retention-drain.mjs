// Read-only completion gate for the exact backed-up queue, not all future input.
import fs from 'node:fs';
const [snapshot, queue, worker] = process.argv.slice(2);
if (!snapshot || !queue || !worker) throw new Error('snapshot_queue_worker_paths_required');
const ids=new Set(JSON.parse(fs.readFileSync(snapshot,'utf8')).items.map(r=>r.id));
for (;;) {
  const rows=JSON.parse(fs.readFileSync(queue,'utf8')).items;
  const state=JSON.parse(fs.readFileSync(worker,'utf8'));
  const remaining=rows.filter(r=>ids.has(r.id));
  const report={at:new Date().toISOString(),initial_items:ids.size,remaining_initial:remaining.length,
    completed_initial:ids.size-remaining.length,live_queue:rows.length,worker_status:state.status,
    completed_operations:state.completed_total,retries:state.retry_counts||{}};
  console.log(JSON.stringify(report));
  if (!remaining.length) break;
  if (['retry_limit_reached','worker_error','acknowledgement_conflict','intent_conflict'].includes(state.status)) process.exit(1);
  await new Promise(r=>setTimeout(r,30000));
}
