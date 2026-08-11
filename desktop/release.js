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

// 1. build installer
run("npm run dist", { cwd: __dirname });

// 2. stage ascii-named assets (GitHub/electron-updater safe)
const files = fs.readdirSync(releaseDir);
const setup = files.find((f) => f.endsWith(".exe") && f.includes("Setup") && !f.includes("__uninstaller"));
const bmap = files.find((f) => f.endsWith(".exe.blockmap"));
if (!setup || !bmap) throw new Error("installer artifacts missing after build");
const asciiExe = `novel-pipeline-desktop-setup-${version}.exe`;
fs.copyFileSync(path.join(releaseDir, setup), path.join(releaseDir, asciiExe));
fs.copyFileSync(path.join(releaseDir, bmap), path.join(releaseDir, asciiExe + ".blockmap"));

// 3. tag & push
run(`git tag v${version}`, { cwd: root });
run(`git push origin v${version}`, { cwd: root });

// 4. create release (replace existing tag release if any)
const exists = gh(`release view v${version} --json tagName --jq .tagName`);
if (exists) {
  try {
    gh(`release delete v${version} --yes`);
  } catch {
    // release may not exist yet; create below
  }
}
gh(`release create v${version} --title "v${version}" --notes "Novel Pipeline Desktop v${version}"`);

// 5. upload assets (clobber so re-runs are idempotent)
gh(
  `release upload v${version} "${path.join(releaseDir, asciiExe)}" "${path.join(releaseDir, asciiExe + ".blockmap")}" "${path.join(releaseDir, "latest.yml")}" --clobber`,
);

console.log(`Released https://github.com/${owner}/${repo}/releases/tag/v${version}`);
