export type Team = "RESEARCH" | "ENGINEER" | "EVENT" | "MEDIA";
export type TypeTag = "CLC" | "DT" | "TN";
export type Role = "ROLE_ADMIN" | "ROLE_USER" | "ROLE_MANAGER" | (string & {});
export type ModalMode = "add" | "edit" | "view";

export type UserLogin = {
  id: number | string;
  name: string;
  email: string;
  role: Role | string;
};

export type User = {
  id: number | string;
  name: string;
  code: string;
  email: string;
  team: Team | string;
  type: TypeTag | string;
  role: Role | string;
  score?: number;
  totalScore?: number;
  dateAdded?: string;
  status?: boolean;
  active?: boolean;
  profilePicture?: string;
};
