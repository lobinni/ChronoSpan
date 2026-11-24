#!/usr/bin/env node
/**
 * Read-only calls against a deployed ChronoSpan contract.
 *
 *   npm install genlayer-js
 *   node samples/query.mjs 0xYourContractAddress
 *
 * Reads are free: no wallet, no key, no gas. Everything a frontend needs
 * from the contract is one of these five calls.
 */
import { createClient } from "genlayer-js";
import { studionet } from "genlayer-js/chains";

// Default: the address recorded in deployments/chronospan.studionet.json.
const DEPLOYED = "0x499D1d2b5ee169b89Fa20aB426B754E8579EE2dd";
const address = process.argv[2] ?? DEPLOYED;
if (!/^0x[0-9a-fA-F]{40}$/.test(address)) {
  console.error("usage: node samples/query.mjs <contract-address>");
  process.exit(1);
}

const client = createClient({ chain: studionet });
const read = (functionName, args = []) =>
  client.readContract({ address, functionName, args, stateStatus: "accepted" });

const [tableId] = await read("list_tables");
console.log("table id      ", tableId);

const coverage = await read("coverage", [tableId]);
console.log("coverage      ", coverage.first_utc, "..", coverage.last_utc_exclusive);

const meta = await read("table_meta", [tableId]);
console.log("transitions   ", meta.transition_count, "expires", meta.expires_ntp);
console.log(
  "publishers    ",
  meta.sources.map((source) => new URL(source.url).host).join(", ")
);

const interval = await read("measure", [
  tableId,
  "2016-12-31T23:59:59Z",
  "2017-01-01T00:00:00Z",
]);
console.log(
  "2016 insertion",
  interval.elapsed_seconds,
  "SI seconds, offset changes",
  JSON.stringify(interval.offset_changes)
);

console.log(
  "advance +1s   ",
  await read("advance", [tableId, "2016-12-31T23:59:59Z", 1])
);
console.log(
  "rewind  -2s   ",
  await read("rewind", [tableId, "2017-01-01T00:00:00Z", 2])
);
console.log(
  "next leap     ",
  JSON.stringify(await read("next_transition", [tableId, "2016-06-01T00:00:00Z"]))
);

try {
  await read("get_table", ["0".repeat(64)]);
} catch (error) {
  console.log("unknown id    ", error.shortMessage ?? error.message);
}
