import { DemoCTA } from "@/components/DemoCTA";
import { FeatureGrid } from "@/components/FeatureGrid";
import { LandingHero } from "@/components/LandingHero";
import { SupportedPlatforms } from "@/components/SupportedPlatforms";
import { WorkflowStrip } from "@/components/WorkflowStrip";

export default function Home() {
  return (
    <main id="home" className="min-h-screen bg-white text-slate-950 dark:bg-slate-950 dark:text-slate-50">
      <LandingHero />
      <FeatureGrid />
      <WorkflowStrip />
      <SupportedPlatforms />
      <DemoCTA />
    </main>
  );
}
