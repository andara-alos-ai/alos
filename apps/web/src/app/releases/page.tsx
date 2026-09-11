import { redirect } from "next/navigation";

export default function ReleasesPage() {
  redirect("/governance?view=agents&sub=releases");
}
