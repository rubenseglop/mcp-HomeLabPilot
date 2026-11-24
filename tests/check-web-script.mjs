import { readFileSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";

const source = readFileSync("src/homelabpilot/web.py", "utf8");
const start = source.indexOf("<script>");
const end = source.indexOf("</script>", start + 8);
if (start < 0 || end < 0) {
  throw new Error("Could not locate the embedded dashboard JavaScript in web.py");
}
const target = join(tmpdir(), "homelabpilot-dashboard.js");
writeFileSync(target, source.slice(start + 8, end), "utf8");
const checked = spawnSync(process.execPath, ["--check", target], { stdio: "inherit" });
if (checked.error) throw checked.error;
if (checked.status !== 0) process.exit(checked.status ?? 1);
const navGroups = ["radarr", "sonarr", "lidarr", "scryer"];
for (const group of navGroups) {
  if (!source.includes(`data-nav-group="${group}"`) || !source.includes(`data-nav-toggle="${group}"`)) {
    throw new Error(`Missing expandable sidebar group: ${group}`);
  }
}
if (!source.includes("homelabpilot-sidebar-groups") || !source.includes("function setNavGroupOpen")) {
  throw new Error("Sidebar expanded-state persistence is missing");
}
if (!source.includes('data-view="downloads"')) {
  throw new Error("Direct Downloads navigation entry is missing");
}
process.stdout.write("Embedded dashboard JavaScript syntax: OK\n");
