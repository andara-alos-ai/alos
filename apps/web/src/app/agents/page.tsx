import { redirect } from "next/navigation";

export default function AgentsPage() {
  redirect("/governance?view=agents");
}
