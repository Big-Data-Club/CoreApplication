/* eslint-disable @typescript-eslint/no-explicit-any */
import { User } from "@/types";
import { v4 as uuidv4 } from "uuid";

/** Convert server user object to frontend User */
export function humanizeEnum(value?: string) {
  if (!value) return "";
  const lower = value.toLowerCase();
  if (lower.startsWith("role_")) {
    return value.replace(/^ROLE_?/i, "").toLowerCase().replace(/(^|\_)([a-z])/g, (_, __, c) => c.toUpperCase());
  }
  return value.toLowerCase().replace(/(^|\_)([a-z])/g, (_, __, c) => c.toUpperCase());
}

export function mapServerUserToClient(s: any): User {
  return {
    id: String(s.id ?? uuidv4()),
    name: s.name ?? s.fullName ?? "Unnamed",
    code: (s.code ?? s.email ?? `user-${s.id}`) as string,
    email: s.email ?? "",
    team: humanizeEnum(s.team) || "Research",
    type: (s.type ?? "CLC") as string,
    role: humanizeEnum(s.role) || "Member",
    score: Number(s.totalScore ?? s.score ?? 0),
    dateAdded: s.createdAt ?? s.updatedAt ?? new Date().toISOString(),
    status: typeof s.active === "boolean" ? s.active : Boolean(s.status ?? true),
  };
}
