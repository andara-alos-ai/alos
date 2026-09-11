import { Suspense } from "react";
import { GovernanceDashboard } from "@/components/governance-dashboard";

export default function GovernancePage() {
  return (
    <Suspense fallback={null}>
      <GovernanceDashboard />
    </Suspense>
  );
}
