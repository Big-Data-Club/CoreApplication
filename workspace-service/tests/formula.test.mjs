import test from "node:test";
import assert from "node:assert/strict";
import { evaluateFormula } from "../src/formula.mjs";
test("formulas use typed fields, arithmetic precedence and bounded functions", () => {
  const values = { hours: 3, rate: 12, status: "done", empty: null };
  const resolve = (id) => values[id] ?? null;
  assert.equal(
    evaluateFormula("[hours]*[rate]+ROUND(1.235,2)", resolve),
    37.24,
  );
  assert.equal(
    evaluateFormula('IF([status]=="done", SUM(1,2,3), 0)', resolve),
    6,
  );
  assert.equal(evaluateFormula("2^3^2", resolve), 512);
  assert.equal(evaluateFormula('CONCAT("A", [status])', resolve), "Adone");
  assert.equal(evaluateFormula('DAYS("2026-11-05","2026-11-01")', resolve), 4);
});
test("formula input cannot execute code or escape the expression grammar", () => {
  for (const expression of [
    "globalThis.process.exit()",
    'constructor("return process")()',
    "SUM.constructor(1)",
    "__proto__(1)",
    "1/0",
    "2^100000",
    "(1+2",
    "1;2",
    "Math.random()",
  ])
    assert.throws(() => evaluateFormula(expression, () => null), expression);
  assert.throws(() =>
    evaluateFormula("(".repeat(50) + "1" + ")".repeat(50), () => null),
  );
});
