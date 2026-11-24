#!/usr/bin/env node
/**
 * Live verification of a deployed ChronoSpan instance.
 *
 *   npm install genlayer-js
 *   node samples/verify_deployment.mjs                        # address from deployments/
 *   node samples/verify_deployment.mjs 0xYourContractAddress  # or any instance
 *
 * Reads only: no wallet, no key, no gas. Exits 0 when every check passes,
 * 1 on the first failure. See docs/DEPLOYMENT.md for the expected table.
 */
import { readFileSync } from "node:fs";
import { createClient } from "genlayer-js";
import { studionet } from "genlayer-js/chains";

const RECORD = new URL("../deployments/chronospan.studionet.json", import.meta.url);

function addressFromRecord() {
  try {
    return JSON.parse(readFileSync(RECORD, "utf8")).address;
  } catch {
    return null;
  }
}

const address = process.argv[2] ?? addressFromRecord();
if (!address) {
  console.error("usage: node samples/verify_deployment.mjs <contract-address>");
  process.exit(1);
}

const client = createClient({ chain: studionet });
const read = (functionName, args = []) =>
  client.readContract({ address, functionName, args, stateStatus: "accepted" });

/** Dict returns arrive either as an object or as canonical JSON text. */
const asObject = (value) =>
  typeof value === "string" ? JSON.parse(value) : value;

let failures = 0;
function check(label, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (!ok) failures += 1;
  console.log(`${ok ? "PASS" : "FAIL"}  ${label}`);
  if (!ok) {
    console.log(`      expected ${JSON.stringify(expected)}`);
    console.log(`      actual   ${JSON.stringify(actual)}`);
  }
}

console.log(`ChronoSpan @ ${address}\n`);

const tables = await read("list_tables");
check("list_tables returns at least one id", tables.length >= 1, true);
check(
  "every table id is a 64-hex digest",
  tables.every((id) => /^[0-9a-f]{64}$/.test(id)),
  true
);

const tableId = tables[0];
const meta = asObject(await read("table_meta", [tableId]));
check("table_meta.schema", meta.schema, "chronospan/v1");
check("table_meta.transition_count", meta.transition_count, 28);
check(
  "table_meta carries both publishers",
  meta.sources.map((source) => new URL(source.url).host).sort(),
  ["hpiers.obspm.fr", "tf.nist.gov"]
);

const coverage = asObject(await read("coverage", [tableId]));
check("coverage.first_utc", coverage.first_utc, "1972-01-01T00:00:00Z");
check(
  "coverage.last_utc_exclusive is after first_utc",
  coverage.last_utc_exclusive > coverage.first_utc,
  true
);

const interval = asObject(
  await read("measure", [
    tableId,
    "2016-12-31T23:59:59Z",
    "2017-01-01T00:00:00Z",
  ])
);
check("2016 insertion is two SI seconds", interval.elapsed_seconds, 2);
check(
  "offset change inside the interval",
  interval.offset_changes,
  [[3692217600, 37]]
);
check("measure echoes the table id", interval.table_id, tableId);

check(
  "advance +1s reaches the inserted label",
  await read("advance", [tableId, "2016-12-31T23:59:59Z", 1]),
  "2016-12-31T23:59:60Z"
);
check(
  "rewind -2s returns to the last ordinary second",
  await read("rewind", [tableId, "2017-01-01T00:00:00Z", 2]),
  "2016-12-31T23:59:59Z"
);

const upcoming = asObject(
  await read("next_transition", [tableId, "2016-06-01T00:00:00Z"])
);
check("next transition inserts 23:59:60Z", upcoming.inserted_utc, "2016-12-31T23:59:60Z");
check("next transition is 2017-01-01", upcoming.effective_utc, "2017-01-01T00:00:00Z");

async function expectRevert(label, message, call) {
  try {
    await call();
    console.log(`FAIL  ${label}`);
    console.log("      expected a revert, the call succeeded");
    failures += 1;
  } catch (error) {
    const text = String(error?.shortMessage ?? error?.message ?? error);
    const ok = text.toLowerCase().includes(message);
    console.log(`${ok ? "PASS" : "FAIL"}  ${label}`);
    if (!ok) {
      console.log(`      expected revert containing "${message}"`);
      console.log(`      actual   ${text}`);
      failures += 1;
    }
  }
}

await expectRevert("unknown table id reverts", "unknown table id", () =>
  read("get_table", ["0".repeat(64)])
);
await expectRevert("label before coverage reverts", "outside schedule coverage", () =>
  read("measure", [tableId, "1971-12-31T23:59:59Z", "1972-01-01T00:00:00Z"])
);
await expectRevert("false leap label reverts", "does not exist", () =>
  read("advance", [tableId, "2016-12-30T23:59:60Z", 1])
);
await expectRevert("reversed interval reverts", "end label precedes start", () =>
  read("measure", [tableId, "2017-01-01T00:00:00Z", "2016-12-31T23:59:59Z"])
);

console.log(
  failures === 0
    ? "\nAll live checks passed."
    : `\n${failures} check(s) failed.`
);
process.exit(failures === 0 ? 0 : 1);
