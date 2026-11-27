import assert from "node:assert/strict";
import { test } from "node:test";
import { rankRows } from "../web/js/ext/advisors/model.js";

test("advisors rank comparable values and keep zero distinct from missing", () => {
  const rows = [
    { id: "a", value: null },
    { id: "b", value: -1 },
    { id: "c", value: 0 },
    { id: "d", value: 2 },
  ];
  assert.deepEqual(rankRows(rows).map((row) => row.id), ["d", "c", "b", "a"]);
  assert.deepEqual(rankRows(rows, "asc").map((row) => row.id), ["b", "c", "d", "a"]);
});
