import { readFileSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";

const source = readFileSync("src/homelabpilot/web.py", "utf8");
const match = source.match(/<script>([\\s\\S]*?)<\\/script>/);
if (!match) {
  throw new Error("Could not locate the embedded dashboard JavaScript in web.py");
}
const target = join(tmpdir(), "homelabpilot-dashboard.js");
writeFileSync(target, match[1], "utf8");
const checked = spawnSync(process.execPath, ["--check", target], { stdio: "inherit" });
if (checked.error) throw checked.error;
if (checked.status !== 0) process.exit(checked.status ?? 1);
process.stdout.write("Embedded dashboard JavaScript syntax: OK\\n");
