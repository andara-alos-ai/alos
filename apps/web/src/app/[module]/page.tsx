import { ExecutiveDashboard } from "@/components/executive-dashboard";
import { dashboardModules, isDashboardModuleKey } from "@/lib/dashboard-modules";
import { notFound } from "next/navigation";

export function generateStaticParams() {
  return Object.keys(dashboardModules).map((module) => ({ module }));
}

export default async function DashboardModulePage({ params }: { params: Promise<{ module: string }> }) {
  const { module } = await params;
  if (!isDashboardModuleKey(module)) notFound();
  return <ExecutiveDashboard module={module} />;
}
