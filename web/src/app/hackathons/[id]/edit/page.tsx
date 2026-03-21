"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { hackathons as api } from "@/lib/api";
import type { Hackathon } from "@/lib/types";
import { HackathonForm } from "@/components/hackathon-form";

export default function EditHackathonPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [hackathon, setHackathon] = useState<Hackathon | null>(null);

  useEffect(() => {
    api.get(id).then(setHackathon);
  }, [id]);

  if (!hackathon) {
    return <p className="text-muted-foreground">Loading...</p>;
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">
          Edit {hackathon.name}
        </h1>
        <p className="text-muted-foreground">
          Update your hackathon configuration
        </p>
      </div>
      <HackathonForm
        initial={{ name: hackathon.name, config: hackathon.config }}
        submitLabel="Save Changes"
        onSubmit={async (data) => {
          await api.update(id, { name: data.name, config: data.config });
          router.push(`/hackathons/${id}`);
        }}
        onCancel={() => router.push(`/hackathons/${id}`)}
      />
    </div>
  );
}
