import type {
  ProjectCreateResponse,
  ProjectDetailResponse,
} from "@/types/project";

type ProjectStatusCardProps = {
  createdProject: ProjectCreateResponse | null;
  projectDetail: ProjectDetailResponse | null;
  progressMessage: string | null;
  error: string | null;
};

export function ProjectStatusCard({
  createdProject,
  projectDetail,
  progressMessage,
  error,
}: ProjectStatusCardProps) {
  if (!createdProject && !projectDetail && !progressMessage && !error) {
    return null;
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      {progressMessage ? (
        <p className="rounded-md border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800">
          {progressMessage}
        </p>
      ) : null}

      {createdProject ? (
        <div>
          <p className="text-sm font-semibold text-emerald-700">
            Project created successfully
          </p>
          <dl className="mt-4 grid gap-3 text-sm">
            <div>
              <dt className="font-medium text-slate-500">Project ID</dt>
              <dd className="mt-1 break-all text-slate-950">
                {createdProject.project_id}
              </dd>
            </div>
            <div>
              <dt className="font-medium text-slate-500">Status</dt>
              <dd className="mt-1 text-slate-950">
                {projectDetail?.status ?? createdProject.status}
              </dd>
            </div>
            <div>
              <dt className="font-medium text-slate-500">Message</dt>
              <dd className="mt-1 text-slate-950">{createdProject.message}</dd>
            </div>
          </dl>
          <p className="mt-4 text-sm leading-6 text-slate-600">
            Content extraction runs for both URLs. Missing public metrics
            remain unavailable instead of being estimated.
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
