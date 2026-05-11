import type { ReactNode } from "react";

export type MarkdownFile = {
  body: string;
  data: Record<string, unknown>;
  path: string;
};

export type WorkshopProgressItem = {
  checked: boolean;
  current: boolean;
  label: string;
  stepId: string;
};

export type WorkshopEvent = {
  agent: string;
  phase: string;
  summary: string;
  timestamp: string;
};

export type WorkshopState = {
  artifacts: string[];
  currentStep: string | null;
  events: WorkshopEvent[];
  path: string;
  progress: WorkshopProgressItem[];
  status: string | null;
};

export type ManifestGroup = {
  id: string;
  label: string;
  surface_ids: string[];
  transient?: boolean;
};

export type ManifestSurface = {
  audience?: string;
  diataxis?: string;
  id: string;
  path: string;
  renderer?: string;
  summary?: string;
  title: string;
  type: string;
};

export type MetricKpiGroup = {
  label: string;
  metrics: string[];
};

export type RenderableBody = ReactNode;
