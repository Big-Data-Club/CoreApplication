import { z } from "zod";
export const uuid = z.string().uuid();
export const role = z.enum(["viewer", "commenter", "editor", "manager"]);
export const title = z.string().trim().min(1).max(300);
export const createField = z
  .object({
    title: z.string().trim().min(1).max(120),
    description: z.string().trim().max(280).default(""),
    icon: z
      .enum([
        "book",
        "folder",
        "sigma",
        "atom",
        "flask",
        "brain",
        "code",
        "sprout",
        "globe",
        "pen",
        "briefcase",
        "sparkles",
      ])
      .default("book"),
    color: z
      .enum(["blue", "violet", "green", "amber", "rose", "slate"])
      .default("violet"),
    tags: z.array(z.string().trim().min(1).max(32)).max(6).default([]),
  })
  .strict();
export const patchField = createField
  .partial()
  .extend({ version: z.number().int().positive() })
  .strict();
export const safeUrl = z
  .string()
  .max(2000)
  .refine((value) => {
    if (/^\/(?!\/)[^\\]*$/.test(value)) return true;
    try {
      const url = new URL(value);
      return (
        ["https:", "http:"].includes(url.protocol) &&
        !url.username &&
        !url.password
      );
    } catch {
      return false;
    }
  }, "Liên kết không hợp lệ.");
export const source = z
  .object({
    type: z.enum(["course", "lab", "task", "url", "notebook", "studio"]),
    id: z.string().max(100).optional(),
    label: z.string().max(200),
    url: safeUrl.optional(),
  })
  .strict();
export const createPage = z
  .object({
    title: title.default("Trang không tiêu đề"),
    parent_id: uuid.nullable().default(null),
    field_id: uuid.nullable().optional(),
    kind: z.enum(["page", "database"]).default("page"),
    sources: z.array(source).max(30).default([]),
    template: z
      .enum(["blank", "meeting", "research", "lab", "learning"])
      .optional(),
    markdown: z.string().max(100000).optional(),
  })
  .strict();
export const patchPage = z
  .object({
    title: title.optional(),
    icon: z.string().max(32).optional(),
    cover: z
      .enum(["", "blue", "violet", "green", "amber", "rose", "slate"])
      .optional(),
    full_width: z.boolean().optional(),
    parent_id: uuid.nullable().optional(),
    field_id: uuid.nullable().optional(),
    sort_order: z.number().finite().min(-1e9).max(1e9).optional(),
    sources: z.array(source).max(30).optional(),
    version: z.number().int().positive(),
  })
  .strict();
const option = z
  .object({
    id: z.string().min(1).max(50),
    label: z.string().min(1).max(100),
    color: z
      .enum(["blue", "green", "amber", "rose", "violet", "slate"])
      .default("slate"),
  })
  .strict();
export const field = z
  .object({
    id: z.string().regex(/^[a-zA-Z0-9_-]{1,64}$/),
    name: z.string().trim().min(1).max(80),
    type: z.enum([
      "text",
      "number",
      "select",
      "status",
      "multi_select",
      "person",
      "date",
      "checkbox",
      "url",
      "relation",
      "formula",
      "rollup",
    ]),
    options: z.array(option).max(30).optional(),
    formula: z.string().max(1000).optional(),
    relation_page_id: uuid.optional(),
    relation_field_id: z.string().max(64).optional(),
    target_field_id: z.string().max(64).optional(),
    aggregate: z.enum(["count", "sum", "avg", "min", "max"]).optional(),
  })
  .strict();
export const fields = z
  .array(field)
  .max(40)
  .refine(
    (items) => new Set(items.map((item) => item.id)).size === items.length,
    "ID thuộc tính bị trùng.",
  );
export const view = z
  .object({
    name: z.string().trim().min(1).max(80),
    type: z.enum(["table", "board", "calendar", "list", "gallery", "timeline"]),
    personal: z.boolean().default(false),
    config: z
      .object({
        group_by: z.string().max(64).optional(),
        date_field: z.string().max(64).optional(),
        sort_by: z.string().max(64).optional(),
        sort_direction: z.enum(["asc", "desc"]).optional(),
        visible_fields: z.array(z.string().max(64)).max(40).optional(),
        filters: z
          .array(
            z
              .object({
                field: z.string().max(64),
                op: z.enum([
                  "eq",
                  "contains",
                  "empty",
                  "not_empty",
                  "gte",
                  "lte",
                ]),
                value: z
                  .union([z.string().max(500), z.number(), z.boolean()])
                  .optional(),
              })
              .strict(),
          )
          .max(20)
          .optional(),
      })
      .strict()
      .default({}),
  })
  .strict();
export const propertyPatch = z
  .object({
    title: title.optional(),
    values: z.record(z.unknown()).default({}),
    version: z.number().int().positive(),
  })
  .strict();
export const comment = z
  .object({
    body: z.string().trim().min(1).max(10000),
    block_id: z.string().max(100).nullable().default(null),
    parent_id: uuid.nullable().default(null),
    mentions: z
      .array(z.string().regex(/^[1-9][0-9]{0,18}$/))
      .max(20)
      .default([]),
  })
  .strict();
export function parse(schema, value) {
  return schema.parse(value);
}
export const defaultFields = [
  {
    id: "status",
    name: "Trạng thái",
    type: "status",
    options: [
      { id: "todo", label: "Chưa làm", color: "slate" },
      { id: "doing", label: "Đang làm", color: "blue" },
      { id: "done", label: "Hoàn thành", color: "green" },
    ],
  },
  { id: "assignee", name: "Người phụ trách", type: "person" },
  { id: "date", name: "Ngày", type: "date" },
  {
    id: "priority",
    name: "Ưu tiên",
    type: "select",
    options: [
      { id: "low", label: "Thấp", color: "slate" },
      { id: "normal", label: "Vừa", color: "blue" },
      { id: "high", label: "Cao", color: "rose" },
    ],
  },
];
