// A bounded expression parser. Formulas never execute JavaScript or property access.
const precedence = {
  "||": 1,
  "&&": 2,
  "==": 3,
  "!=": 3,
  ">": 4,
  "<": 4,
  ">=": 4,
  "<=": 4,
  "+": 5,
  "-": 5,
  "*": 6,
  "/": 6,
  "%": 6,
  "^": 7,
};
const functions = {
  SUM: (...v) => numeric(v).reduce((a, b) => a + b, 0),
  AVG: (...v) => {
    const n = numeric(v);
    return n.length ? n.reduce((a, b) => a + b, 0) / n.length : 0;
  },
  MIN: (...v) => Math.min(...numeric(v)),
  MAX: (...v) => Math.max(...numeric(v)),
  COUNT: (...v) =>
    v.flat().filter((x) => x !== null && x !== undefined && x !== "").length,
  ABS: Math.abs,
  ROUND: (n, places = 0) => {
    if (!Number.isInteger(places) || Math.abs(places) > 10)
      throw Error("Số chữ số làm tròn không hợp lệ.");
    return Math.round(Number(n) * 10 ** places) / 10 ** places;
  },
  IF: (condition, yes, no) => (condition ? yes : no),
  EMPTY: (v) => v == null || v === "" || (Array.isArray(v) && !v.length),
  CONCAT: (...v) =>
    v
      .map((x) => String(x ?? ""))
      .join("")
      .slice(0, 5000),
  DAYS: (a, b) => {
    const x = Date.parse(String(a)),
      y = Date.parse(String(b));
    if (!Number.isFinite(x + y)) throw Error("Ngày không hợp lệ.");
    return Math.round((x - y) / 86400000);
  },
};
function numeric(values) {
  return values
    .flat()
    .filter((v) => v != null && v !== "")
    .map((v) => {
      const n = Number(v);
      if (!Number.isFinite(n)) throw Error("Cần giá trị số.");
      return n;
    });
}
function tokenize(source) {
  if (source.length > 1000) throw Error("Công thức quá dài.");
  const result = [];
  let offset = 0;
  const pattern =
    /\s*(?:([0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?)|\[([^\]\r\n]{1,80})\]|("(?:[^"\\]|\\["\\nrt])*")|([A-Za-z_][A-Za-z0-9_]*)|(>=|<=|==|!=|&&|\|\||[+*/%^(),!<>-]))/iy;
  while (offset < source.length) {
    if (!source.slice(offset).trim()) break;
    pattern.lastIndex = offset;
    const m = pattern.exec(source);
    if (!m) throw Error("Ký hiệu không được hỗ trợ.");
    result.push(
      m[1]
        ? { type: "value", value: Number(m[1]) }
        : m[2]
          ? { type: "ref", value: m[2] }
          : m[3]
            ? { type: "value", value: JSON.parse(m[3]) }
            : m[4]
              ? { type: "name", value: m[4] }
              : { type: m[5], value: m[5] },
    );
    offset = pattern.lastIndex;
    if (result.length > 300) throw Error("Công thức quá phức tạp.");
  }
  return result;
}
export function evaluateFormula(source, resolve) {
  const tokens = tokenize(source);
  let at = 0,
    depth = 0;
  function expression(min = 0) {
    if (++depth > 30) throw Error("Công thức lồng quá sâu.");
    let value;
    const token = tokens[at++];
    if (!token) throw Error("Thiếu giá trị.");
    if (token.type === "value") value = token.value;
    else if (token.type === "ref") value = resolve(token.value);
    else if (["+", "-", "!"].includes(token.type)) {
      const next = expression(8);
      value =
        token.type === "!"
          ? !next
          : token.type === "-"
            ? -Number(next)
            : Number(next);
    } else if (token.type === "(") {
      value = expression();
      if (tokens[at++]?.type !== ")") throw Error("Thiếu dấu đóng ngoặc.");
    } else if (token.type === "name") {
      const name = token.value.toUpperCase();
      if (["TRUE", "FALSE", "NULL"].includes(name))
        value = name === "NULL" ? null : name === "TRUE";
      else {
        const fn = functions[name];
        if (!Object.hasOwn(functions, name) || typeof fn !== "function")
          throw Error(`Hàm ${name} chưa được hỗ trợ.`);
        if (tokens[at++]?.type !== "(") throw Error("Thiếu dấu mở ngoặc.");
        const args = [];
        if (tokens[at]?.type !== ")") {
          for (;;) {
            args.push(expression());
            if (tokens[at]?.type !== ",") break;
            at++;
          }
        }
        if (tokens[at++]?.type !== ")") throw Error("Thiếu dấu đóng ngoặc.");
        value = fn(...args);
      }
    } else throw Error("Giá trị không hợp lệ.");
    while (tokens[at] && precedence[tokens[at].type] >= min) {
      const op = tokens[at++].type;
      const right = expression(precedence[op] + (op === "^" ? 0 : 1));
      switch (op) {
        case "+":
          value =
            typeof value === "string" || typeof right === "string"
              ? String(value ?? "") + String(right ?? "")
              : Number(value) + Number(right);
          break;
        case "-":
          value = Number(value) - Number(right);
          break;
        case "*":
          value = Number(value) * Number(right);
          break;
        case "/":
          if (Number(right) === 0) throw Error("Không thể chia cho 0.");
          value = Number(value) / Number(right);
          break;
        case "%":
          value = Number(value) % Number(right);
          break;
        case "^":
          if (Math.abs(Number(right)) > 100)
            throw Error("Số mũ vượt giới hạn.");
          value = Number(value) ** Number(right);
          break;
        case "==":
          value = value === right;
          break;
        case "!=":
          value = value !== right;
          break;
        case ">":
          value = value > right;
          break;
        case "<":
          value = value < right;
          break;
        case ">=":
          value = value >= right;
          break;
        case "<=":
          value = value <= right;
          break;
        case "&&":
          value = Boolean(value && right);
          break;
        case "||":
          value = Boolean(value || right);
          break;
      }
    }
    depth--;
    return value;
  }
  const result = expression();
  if (at !== tokens.length) throw Error("Công thức chưa hoàn chỉnh.");
  if (typeof result === "number" && !Number.isFinite(result))
    throw Error("Kết quả số không hợp lệ.");
  return typeof result === "string" ? result.slice(0, 5000) : result;
}
