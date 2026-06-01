import type { ProjectCreateResponse } from "@/types/project";

type ProjectStatusCardProps = {
  project: ProjectCreateResponse | null;
  error: string | null;
};

export function ProjectStatusCard({
  project,
  error,
}: ProjectStatusCardProps) {
  if (!project && !error) {
    return null;
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      {project ? (
        <div>
          <p className="text-sm font-semibold text-emerald-700">
            Project created successfully
          </p>
          <dl className="mt-4 grid gap-3 text-sm">
            <div>
              <dt className="font-medium text-slate-500">Project ID</dt>
              <dd className="mt-1 break-all text-slate-950">
                {project.project_id}
              </dd>
            </div>
            <div>
              <dt className="font-medium text-slate-500">Status</dt>
              <dd className="mt-1 text-slate-950">{project.status}</dd>
            </div>
            <div>
              <dt className="font-medium text-slate-500">Message</dt>
              <dd className="mt-1 text-slate-950">{project.message}</dd>
            </div>
          </dl>
          <p className="mt-4 text-sm leading-6 text-slate-600">
            Next step: Day 02 extraction will pull transcripts, metadata,
            engagement signals, and prepare chunks for Qdrant.
          </p>
        </div>
      ) : null}

      {error ? (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
          {error}
        </div>
      ) : null}
    </section>
  );
}
