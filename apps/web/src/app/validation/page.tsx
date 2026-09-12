import { redirect } from "next/navigation";

export default function ValidationPage() {
  redirect("/governance?view=sources");
}
