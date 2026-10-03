import type { Route } from "next";
import Link from "next/link";

import { SectionCard } from "@/components/chrome/section-card";

type Surface = { href: Route; summary: string; title: string };

/** Every surface, grouped as the sidebar groups them, with one sentence on what it holds. */
const SURFACES: Surface[] = [
  { href: "/sentinel", title: "Sentinel", summary: "Ecosystem audits graded A to F, with findings by severity." },
  { href: "/metrics", title: "Metrics", summary: "Code health trends and the agent readiness score." },
  { href: "/evals", title: "Evals", summary: "Quality-eval runs, failures by check, and the experiment leaderboard." },
  { href: "/workshops", title: "Workshops", summary: "In-flight pipelines with their steps, artifacts and recent activity." },
  { href: "/roadmap", title: "Roadmap", summary: "Where the project is heading, from the roadmap document." },
  { href: "/architecture", title: "Architecture", summary: "The design target and the code-verified component guide." },
  { href: "/adrs", title: "ADRs", summary: "Architecture decision records and how they supersede one another." },
  { href: "/documentation", title: "Documentation", summary: "Every documentation surface of the project, by purpose." }
];

export function ExploreGrid() {
  return (
    <SectionCard title={<h2 className="overview-card__title">Explore</h2>}>
      <ul className="overview-explore">
        {SURFACES.map((surface) => (
          <li key={surface.href}>
            <Link className="overview-explore__link" href={surface.href}>
              <span className="overview-explore__title">{surface.title}</span>
              <span className="overview-explore__summary">{surface.summary}</span>
            </Link>
          </li>
        ))}
      </ul>
    </SectionCard>
  );
}
