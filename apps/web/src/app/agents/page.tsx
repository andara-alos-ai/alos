import { sharedAgents, workspaces } from "@/lib/catalog";

export default function AgentsPage() {
  const agents = [
    ...sharedAgents.map((id) => ({ id, owner: "Shared Enterprise" })),
    ...workspaces.flatMap((workspace) => workspace.agents.map((id) => ({ id, owner: workspace.name }))),
  ];
  return (
    <>
      <header className="pageHeader"><div><p className="eyebrow">Shared Agent Runtime</p><h1>Agent Registry</h1><p>18 logical agent, satu runtime, dan business owner tetap pada divisi terkait.</p></div></header>
      <div className="tablePanel">
        <table><thead><tr><th>Agent ID</th><th>Pemilik bisnis</th><th>Versi</th><th>Status</th></tr></thead>
          <tbody>{agents.map((agent) => <tr key={agent.id}><td><strong>{agent.id}</strong></td><td>{agent.owner}</td><td>0.1.0</td><td><span className="status">STAGED</span></td></tr>)}</tbody>
        </table>
      </div>
    </>
  );
}
