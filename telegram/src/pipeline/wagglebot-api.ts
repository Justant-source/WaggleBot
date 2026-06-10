/**
 * WaggleBot 백엔드 REST API 클라이언트.
 * Spring Boot :8080 과 통신.
 */
import { config } from "../config.js";
import { logger } from "../utils/logger.js";

const BASE = config.backend.url;

export interface PostSummary {
  id: number;
  title: string;
  siteCode: string;
  status: string;
  engagementScore: number;
  createdAt: string;
}

export interface PipelineStatus {
  COLLECTED: number;
  EDITING: number;
  APPROVED: number;
  PROCESSING: number;
  PREVIEW_RENDERED: number;
  RENDERED: number;
  UPLOADED: number;
  FAILED: number;
  DECLINED: number;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export async function getPipelineStatus(): Promise<PipelineStatus> {
  return apiFetch<PipelineStatus>("/api/analytics/funnel");
}

export async function getCollectedPosts(limit = 10): Promise<PostSummary[]> {
  const resp = await apiFetch<{ posts: PostSummary[] }>(`/api/inbox?page=0&size=${limit}`);
  return resp.posts ?? [];
}

export async function approvePost(postId: number): Promise<void> {
  await apiFetch(`/api/inbox/${postId}/approve`, { method: "POST" });
}

export async function rejectPost(postId: number): Promise<void> {
  await apiFetch(`/api/inbox/${postId}/decline`, { method: "POST" });
}

export async function triggerCrawl(): Promise<{ jobId: number }> {
  return apiFetch("/api/inbox/crawl", { method: "POST" });
}
