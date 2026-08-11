/* One-command release: build installer, tag, upload to GitHub Releases. */
const { execSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const pkg = require("./package.json");
const version = pkg.version;
const repo = pkg.build.publish[0].repo;
const owner = pkg.build.publish[0].owner;
const root = path.resolve(__dirname, "..");
const releaseDir = path.join(__dirname, "release");

const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY || "";
const env = {
  ...process.env,
  ELECTRON_MIRROR: "https://npmmirror.com/mirrors/electron/",
  ELECTRON_BUILDER_BINARIES_MIRROR: "https://npmmirror.com/mirrors/electron-builder-binaries/",
  ...(proxy ? { HTTPS_PROXY: proxy, HTTP_PROXY: proxy } : {}),
};

function run(cmd, opts = {}) {
  console.log(">", cmd);
  execSync(cmd, { stdio: "inherit", env, ...opts });
}

function gh(args) {
  return execSync(`gh ${args}`, { encoding: "utf-8", env, cwd: root }).trim();
}

console.log(`Releasing v${version} (${owner}/${repo})`);

// 0. build webapp first so the installer bundles fresh frontend; a failed
// build throws here and aborts the release before any artifact is packaged.
run("npm run build", { cwd: path.join(root, "webapp") });

// 1. build installer
run("npm run dist", { cwd: __dirname });

// 2. upload the exact artifact names electron-builder recorded in latest.yml,
// so electron-updater's download path always exists on the release.
const latestYml = path.join(releaseDir, "latest.yml");
const latestYmlText = fs.readFileSync(latestYml, "utf8");
const pathMatch = latestYmlText.match(/^path:\s*(.+)\s*$/m);
if (!pathMatch) throw new Error(`latest.yml missing path: ${latestYml}`);
const exeName = pathMatch[1].trim();
const setup = path.join(releaseDir, exeName);
const bmap = setup + ".blockmap";
if (!fs.existsSync(setup) || !fs.existsSync(bmap)) throw new Error("installer artifacts missing after build");

// 3. tag & push (idempotent: skip when the tag already exists)
let tagExists = false;
try {
  execSync(`git rev-parse v${version}`, { cwd: root, stdio: "ignore" });
  tagExists = true;
} catch {
  tagExists = false;
}
if (!tagExists) {
  run(`git tag v${version}`, { cwd: root });
  run(`git push origin v${version}`, { cwd: root });
}

// 4. create release (replace existing tag release if any)
let exists = "";
try {
  exists = gh(`release view v${version} --json tagName --jq .tagName`);
} catch {
  // release does not exist yet; create below
  exists = "";
}
if (exists) {
  try {
    gh(`release delete v${version} --yes`);
  } catch {
    // release may not exist yet; create below
  }
}
gh(`release create v${version} --title "v${version}" --notes "Novel Editorial Desktop v${version}"`);

// 5. upload assets (clobber so re-runs are idempotent)
gh(`release upload v${version} "${setup}" "${bmap}" "${latestYml}" --clobber`);

console.log(`Released https://github.com/${owner}/${repo}/releases/tag/v${version}`);
