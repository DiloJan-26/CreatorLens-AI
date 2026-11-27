import { EngineeringGate } from "@/components/EngineeringAccess";
import { CostDashboard } from "@/components/CostDashboard";

export default function DashboardPage() {
  return <EngineeringGate title="LLM Observability" icon="chart"><CostDashboard /></EngineeringGate>;
}
