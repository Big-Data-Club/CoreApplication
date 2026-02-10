import { User } from "@/types";

export const users: User[] = [
  { id: "u1", name: "Nguyễn Văn A", code: "NV001", email: "a@example.com", team: "Research", type: "CLC", role: "Admin", score: 190, dateAdded: "2025-10-10", status: true },
  { id: "u2", name: "Trần Thị B", code: "TB002", email: "b@example.com", team: "Engineer", type: "DT", role: "Member", score: 120, dateAdded: "2025-10-11", status: true },
  { id: "u3", name: "Lê C",       code: "LC003", email: "c@example.com", team: "Event", type: "TN", role: "Member", score: 85,  dateAdded: "2025-09-30", status: true },
  { id: "u4", name: "Phạm D",     code: "PD004", email: "d@example.com", team: "Media", type: "CLC", role: "Moderator", score: 210, dateAdded: "2025-08-22", status: false },
  { id: "u5", name: "Hoàng E",    code: "HE005", email: "e@example.com", team: "Engineer", type: "DT", role: "Member", score: 134, dateAdded: "2025-07-12", status: true },
  { id: "u6", name: "Võ F",       code: "VF006", email: "f@example.com", team: "Research", type: "TN", role: "Member", score: 70,  dateAdded: "2025-05-01", status: true },
];