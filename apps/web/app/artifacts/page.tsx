import { Suspense } from "react";
import { ArtifactsPage } from "@/components/artifacts/ArtifactsPage";

export default function Page() {
  return (
    <Suspense>
      <ArtifactsPage />
    </Suspense>
  );
}
