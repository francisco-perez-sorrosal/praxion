import "server-only";

import matter from "gray-matter";
import YAML from "yaml";

import { readText } from "@/server/artifacts/files";
import type { MarkdownFile } from "@/server/types";

export async function readMarkdown(target: string): Promise<MarkdownFile | null> {
  const text = await readText(target);
  if (text === null) {
    return null;
  }

  const parsed = matter(text);
  return {
    body: parsed.content,
    data: parsed.data as Record<string, unknown>,
    path: target
  };
}

export async function readJson<T>(target: string): Promise<T | null> {
  const text = await readText(target);
  if (text === null) {
    return null;
  }

  try {
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}

export async function readYaml<T>(target: string): Promise<T | null> {
  const text = await readText(target);
  if (text === null) {
    return null;
  }

  try {
    return YAML.parse(text) as T;
  } catch {
    return null;
  }
}
