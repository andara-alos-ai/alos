import Link from "next/link";
import { notFound } from "next/navigation";

import { workspaces } from "@/lib/catalog";

export default async function DivisionWorkspacePage({
  params,
}: {
  params: Promise<{ division: string }>;
}) {
  const { division } = await params;
  const workspace = workspaces.find((item) => item.id === division);
  if (!workspace) notFound();

  return (
    <>
      <header className="pageHeader"><div><p className="eyebrow">Workspace Divisi</p><h1>{workspace.name}</h1><p>{workspace.focus}. Business owner tetap berada pada divisi ini; platform IT bertindak sebagai technical custodian.</p></div><Link className="button secondary" href={workspace.operationalHref}>Buka operasional</Link></header>
      <div className="workspaceOverview">
        <section className="panel"><div className="panelHeader"><div><p className="eyebrow">Cakupan ALOS</p><h2>Kapabilitas operasional</h2></div></div><div className="capabilityGrid">{workspace.capabilities.map((capability, index) => <article key={capability}><span>{String(index + 1).padStart(2, "0")}</span><strong>{capability}</strong><small>Dijalankan melalui workflow deterministik dan audit trail ALOS.</small></article>)}</div></section>
        <aside className="panel"><div className="panelHeader"><div><p className="eyebrow">Digital workforce</p><h2>Core Agent & sumber</h2></div></div><div className="agentTiles">{workspace.agents.length ? workspace.agents.map((agent) => <div key={agent}><strong>{agent}</strong><span>Logical agent · Shared Runtime</span></div>) : <div><strong>Technical Custodian</strong><span>Runtime, registry, integrasi, security, observability, dan Genesis</span></div>}</div><div className="workspaceSources"><small>Baseline terkait</small><p>{workspace.sourceKeys.map((key) => `Lampiran ${key}`).join(" · ")}</p></div></aside>
      </div>
    </>
  );
}
