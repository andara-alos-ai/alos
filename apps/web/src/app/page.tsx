import Link from "next/link";

const foundations = [
  "Requirement natural language dengan source dan workspace context",
  "Agent Blueprint dan Contract universal yang terversi",
  "Human review, release proposal, activation eksplisit, dan rollback",
  "Satu shared runtime dengan audit, observability, dan cost ledger",
];

export default function GenesisMvpHomePage() {
  return (
    <section className="spaceY6">
      <header className="pageHeader"><div><p className="eyebrow">ALOS · Internal Controlled Pilot</p><h1>Genesis MVP1</h1><p>Satu Agent Factory dan satu shared runtime untuk kebutuhan lintas Keuangan, Sales & Marketing, Property, HR, Legal, dan IT.</p></div></header>
      <section className="panel spaceY4">
        <div><p className="eyebrow">Alur wajib</p><h2>Requirement → evidence → contract → review → run</h2><p>Genesis hanya menghasilkan proposal. Aktivasi selalu memerlukan validasi, test, dan checkpoint manusia.</p></div>
        <div className="gridCols2">{foundations.map((foundation) => <p className="panel" key={foundation}>{foundation}</p>)}</div>
        <div className="workspaceActionGroup"><Link className="button primary" href="/genesis">Buat requirement agent</Link><Link className="button secondary" href="/agents">Lihat Agent Registry</Link></div>
      </section>
      <section className="panel"><p className="eyebrow">Validation set</p><h2>Tiga logical agent MVP1</h2><ul><li>Daily Brief Agent</li><li>Evidence Checker Agent</li><li>Permit/Overdue Monitor Agent</li></ul></section>
    </section>
  );
}
