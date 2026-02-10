export function getCookie(name: string) {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
  return match ? decodeURIComponent(match[2]) : null;
}

export function mapFrontendRoleToBackend(role: string) {
  if (!role) return "ROLE_USER";
  const r = role.toLowerCase();
  if (r.includes("admin")) return "ROLE_ADMIN";
  if (r.includes("manager")) return "ROLE_MANAGER";
  return "ROLE_USER";
}

export function mapFrontendTeamToBackend(team: string) {
  if (!team) return "RESEARCH";
  return team.toUpperCase();
}

export function mapFrontendTypeToBackend(type: string) {
  if (!type) return "CLC";
  return type.toUpperCase();
}