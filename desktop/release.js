/* One-command release: bump version, build installer, tag, upload to GitHub Releases. */
const { execSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const pkgPath = path.join(__dirname, "package.json");
const pkg = require(pkgPath);
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

function parseVersion(version) {
  const m = /^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$/.exec(version);
  if (!m) throw new Error(`cannot parse semver version: ${version}`);
  return [Number(m[1]), Number(m[2]), Number(m[3])];
}

function compareVersions(a, b) {
  const pa = parseVersion(a);
  const pb = parseVersion(b);
  for (let i = 0; i < 3; i += 1) {
    if (pa[i] !== pb[i]) return pa[i] - pb[i];
  }
  return 0;
}

function bumpVersion(version, level) {
  const [major, minor, patch] = parseVersion(version);
  if (level === "major") return `${major + 1}.0.0`;
  if (level === "minor") return `${major}.${minor + 1}.0`;
  return `${major}.${minor}.${patch + 1}`;
}

function writePackageVersion(version) {
  const pkgText = fs
    .readFileSync(pkgPath, "utf8")
    .replace(/"version":\s*"[^"]+"/, `"version": "${version}"`);
  fs.writeFileSync(pkgPath, pkgText);
  console.log(`Bumped package version to v${version}`);
}

const args = process.argv.slice(2);
const explicitArg = args.find((a) => a.startsWith("--version="));
const explicitVersion = explicitArg ? explicitArg.slice("--version=".length) : "";
const level = args.includes("--major") ? "major" : args.includes("--minor") ? "minor" : "patch";
const noBump = args.includes("--no-bump");

let version;
if (explicitVersion) {
  parseVersion(explicitVersion);
  version = explicitVersion;
  if (version !== pkg.version) writePackageVersion(version);
} else if (noBump) {
  version = pkg.version;
} else {
  version = bumpVersion(pkg.version, level);
  if (version === pkg.version) throw new Error(`cannot bump version ${pkg.version}`);
  writePackageVersion(version);
}

console.log(`Releasing v${version} (${owner}/${repo})`);

// 0. refuse stale versions: electron-updater only upgrades clients when the
// release version is strictly newer than the currently published latest.
let latestRemote = "";
try {
  latestRemote = gh(`release view latest --json tagName --jq .tagName`).replace(/^v/, "");
} catch (err) {
  throw new Error(
    `cannot check the latest GitHub release before publishing: ` +
      `${(err && err.stderr) || (err && err.message) || err}`,
  );
}
if (latestRemote && compareVersions(version, latestRemote) <= 0) {
  throw new Error(
    `refusing to release stale version v${version}: remote latest is v${latestRemote}; ` +
      "bump the version (default patch, or --minor/--major)",
  );
}

// 1. build webapp first so the installer bundles fresh frontend; a failed
// build throws here and aborts the release before any artifact is packaged.
run("npm run build", { cwd: path.join(root, "webapp") });

// 2. build installer
run("npm run dist", { cwd: __dirname });

// 3. upload the exact artifact names electron-builder recorded in latest.yml,
// so electron-updater's download path always exists on the release.
const latestYml = path.join(releaseDir, "latest.yml");
const latestYmlText = fs.readFileSync(latestYml, "utf8");
const pathMatch = latestYmlText.match(/^path:\s*(.+)\s*$/m);
if (!pathMatch) throw new Error(`latest.yml missing path: ${latestYml}`);
const versionMatch = latestYmlText.match(/^version:\s*(.+)\s*$/m);
if (!versionMatch) throw new Error(`latest.yml missing version: ${latestYml}`);
const builtVersion = versionMatch[1].trim();
if (builtVersion !== version) {
  throw new Error(`latest.yml version ${builtVersion} does not match package version ${version}`);
}
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
