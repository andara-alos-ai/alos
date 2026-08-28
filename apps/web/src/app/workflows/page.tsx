import { workflows } from "@/lib/catalog";

export default function WorkflowsPage() {
  return (
    <>
      <header className="pageHeader"><div><p className="eyebrow">Deterministic Workflow Engine</p><h1>Workflow Awal</h1><p>Status, deadline, permission, dan approval routing tidak ditentukan oleh LLM.</p></div></header>
      <div className="workflowList">{workflows.map((workflow, index) => <article key={workflow.id}><span>{String(index + 1).padStart(2, "0")}</span><div><small>{workflow.id}</small><h2>{workflow.name}</h2><p>Business owner: {workflow.owner}</p></div><strong>STAGED</strong></article>)}</div>
    </>
  );
}
