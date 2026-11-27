import { EngineeringGate } from "@/components/EngineeringAccess";
import { EvaluationDashboard } from "@/components/EvaluationDashboard";

export default function EvaluationsPage() {
  return <EngineeringGate title="RAG Evaluation" icon="shield"><EvaluationDashboard /></EngineeringGate>;
}
