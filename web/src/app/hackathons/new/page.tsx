"use client";

import { useRouter } from "next/navigation";
import { hackathons as api } from "@/lib/api";
import { HackathonForm } from "@/components/hackathon-form";

export default function NewHackathonPage() {
  const router = useRouter();

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">New Hackathon</h1>
        <p className="text-muted-foreground">
          Configure your hackathon review pipeline
        </p>
      </div>
      <HackathonForm
        submitLabel="Create Hackathon"
        onSubmit={async (data) => {
          const h = await api.create(data.name, data.config);
          router.push(`/hackathons/${h.id}`);
        }}
        onCancel={() => router.push("/")}
      />
    </div>
  );
}
