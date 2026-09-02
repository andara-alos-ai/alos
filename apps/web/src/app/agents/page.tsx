const validationAgents = [
  ["DAILY_BRIEF", "Daily Brief Agent", "Lintas enam divisi", "Planned"],
  ["EVIDENCE_CHECKER", "Evidence Checker Agent", "Lintas enam divisi", "Planned"],
  ["PERMIT_OVERDUE_MONITOR", "Permit/Overdue Monitor Agent", "Legal & Property", "Planned"],
];

export default function AgentsPage() {
  return (
    <section className="spaceY6">
      <header className="pageHeader"><div><p className="eyebrow">Shared Agent Runtime</p><h1>Agent Registry</h1><p>Registry menampilkan logical agent berversi; tidak ada service atau database per agent.</p></div></header>
      <div className="tablePanel"><table><thead><tr><th>Agent key</th><th>Nama</th><th>Scope</th><th>Status</th></tr></thead><tbody>{validationAgents.map(([key, name, scope, status]) => <tr key={key}><td><strong>{key}</strong></td><td>{name}</td><td>{scope}</td><td><span className="status">{status}</span></td></tr>)}</tbody></table></div>
    </section>
  );
}
