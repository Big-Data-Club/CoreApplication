export function mapFrontendRoleToBackend(role: string): string {
  if (!role) return "ROLE_USER";
  const r = role.toUpperCase();
  // If it's already a well-formatted backend role (from dynamic dropdown)
  if (r.startsWith("ROLE_") || r === r.replace(/[^A-Z_]/g, "")) return r;
  
  // Legacy text mapping for bulk upload CSV
  const lower = role.toLowerCase();
  if (lower.includes("admin")) return "ROLE_ADMIN";
  if (lower.includes("manager")) return "ROLE_MANAGER";
  return "ROLE_USER";
}

export function mapFrontendTeamToBackend(team: string): string {
  if (!team) return "RESEARCH";
  return team.toUpperCase();
}

export function mapFrontendTypeToBackend(type: string): string {
  if (!type) return "CLC";
  return type.toUpperCase();
}