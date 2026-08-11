# Code Review Report — `webapp/src` + `desktop`

## 1. Scope

- **In scope**: `webapp/src` (api layer, store, hooks, all 15 page/panel components, 8 test files, vite config), `desktop/` (`main.js`, `preload.js`, `release.js`, `package.json`, packaging config).
- **Out of scope / excluded**: `node_modules`, `dist`, `package-lock.json`, `release/` artifacts.
- **Dependency interfaces read only to verify contracts**: `novel_editorial/web_api.py`, `config.py`, `services/{control,activity,misc,dashboard,meeting_session,knowledge,agents,ending,editorial}.py`, `tools/{daily_runs,flow_graph,mailroom,editorial_state,ai_taste_check,preflight,distill_lessons}.py`. No full-repo scan performed.

## 2. Baseline (targeted validation)

| Check | Command | Result |
|---|---|---|
| Desktop JS syntax | `node --check main.js / preload.js / release.js` | ✅ all OK |
| Webapp production build | `npm run build` (vite 5.4.21) | ✅ 984 modules, built in 2.45s (warning: charts chunk 527 kB > 500 kB) |
| Webapp tests | `npx vitest run` | ✅ 8 files / 20 tests passed |
| Encoding sanity | raw-byte inspection of `desktop/package.json` (UTF-8) | ✅ valid; console mojibake was display-only |
| Frontend ↔ backend contract spot-check | ~30 endpoint shapes (control, dashboard, meetings, knowledge, agents, actions, endings, flow, SSE, token guard) | ✅ all match (incl. `local_executions` id/workflow/status mapping and `update_action` empty-status fallback) |

No P0, no universal P1 failures found. **The slice is build-clean, test-clean, and contract-consistent.** The issues below are conditional/P2–P3.

## 3. Findings

### [P2] F1 — Packaged desktop app only relocates the DB; all other writable data paths stay in the install directory
`desktop/main.js:61-72` redirects only the SQLite DB to `userData/demo.db`, but the backend keeps every other writable file relative to `ROOT` (= `resources/novel-pipeline` in packaged mode): `alerts.log`, `hot_topics.json`, `n8n_tmp/` (weekly.lock), `exports/`, `demo_data/` (`novel_editorial/config.py:18-26`, used by `services/control.py::_weekly_worker` and `_alert`). In a per-machine NSIS install (Program Files) or any non-writable directory, hot-topic refresh, weekly-meeting locking, exports, and alert logging fail — and most failures are silent (broad `except` blocks plus `_alert()` writing to an unwritable log), so the UI reports “已启动/成功” while nothing is persisted. Default per-user NSIS installs (`%LOCALAPPDATA%\Programs`) are writable, so this only bites when the user picks “install for all users” or a custom read-only location.

### [P2] F2 — `release.js` re-publishes the same version forever; `electron-updater` never delivers an update
`desktop/package.json` pins `"version": "1.0.0"`; `desktop/release.js:6-8,50-78` derives tag/release from `pkg.version`, deletes and re-creates the same tag, and never bumps the version. `main.js::setupAutoUpdater` uses `electron-updater`, which only downloads releases with a **newer** semver than the installed app. Unless the version is manually bumped before every `npm run release`, every subsequent release ships a fresh installer that installed clients will never auto-update to — and the script gives no warning.

### [P2] F3 — `AgentsPage`: stale `moodDraft` leaks across agent switches and can overwrite the wrong agent’s mood
`webapp/src/components/AgentsPage.jsx:127-139`: `currentMood = moodDraft || moodOf?.mood || {...}`; `moodDraft` is never reset in `applyPick()` (lines 106-109) or in the `[selected]` effect, and `saveMood()` posts `currentMood` for the newly selected agent. Repro: edit any mood number for agent A (without saving) → click agent B → B’s panel shows A’s draft, and clicking 保存心情 writes A’s values to B. Since mood is later injected into LLM context (`tools/agent_context.py:76`, `tools/agent_meeting.py:133`), this can feed one agent’s state into another agent’s prompts.

### [P3] F4 — Desktop API auto-restart budget is never reset
`desktop/main.js:100-110` increments `apiRestartCount` on every unexpected exit and never resets it, so after 3 crashes in one app session (e.g., transient port conflict at startup plus later hiccups over weeks of tray uptime) the backend is left permanently down with only a notification, even if later crashes are unrelated and recoverable.

### [P3] F5 — `panelToken()` doesn’t strip inline comments, unlike the backend
`desktop/main.js:193-198` returns `line.slice(eq+1).trim()` verbatim, while the backend parses `~/.n8n/.env` through `config.load_env()`/`_strip_inline_comment` (`novel_editorial/config.py:87-94`), which strips ` # ...` comments. If the env file contains `PANEL_TOKEN=xxx # comment`, the desktop sends `Authorization: Bearer xxx # comment` → backend `_guard` returns 403 → tray “立即更新/周会” reports 启动失败.

### [P3] F6 — No tests for several interactive components
`MeetingLive.jsx`, `MeetingsPage.jsx`, `FlowPage.jsx`, `CostPage.jsx`, `ReaderPage.jsx`, `EditorialPage.jsx`, `agent-panels.jsx`, `CommandPalette.jsx`, and `hooks.js` have no unit tests, although they carry the most logic (polling, SSE merge, session lifecycle, claim/task flows). The existing 8 test files cover only App/Dashboard/Works/Settings/Chapters/Audit/Editorial/Executions.

## 4. Impact table

| ID | File(s) | Condition to trigger | Impact | Priority |
|---|---|---|---|---|
| F1 | desktop/main.js, config.py, package.json | per-machine / read-only install dir | hot-topics, weekly lock, exports, alerts silently fail; UI reports success | P2 |
| F2 | desktop/release.js, package.json, main.js | version not manually bumped | auto-update channel permanently stale | P2 |
| F3 | webapp/src/components/AgentsPage.jsx | edit mood → switch agent → save | wrong agent’s mood persisted & injected into prompts | P2 |
| F4 | desktop/main.js | 3 API crashes in one session | auto-restart permanently disabled | P3 |
| F5 | desktop/main.js, config.py | inline `#` comment on PANEL_TOKEN line | tray triggers rejected with 403 | P3 |
| F6 | webapp/src/components/* | n/a | regression risk; no coverage for session/SSE/flow logic | P3 |

## 5. Conclusion

Honest verdict: **no blocking defects**. The slice builds, all 20 frontend tests pass, desktop scripts pass syntax checks, and every frontend/desktop call verified against the backend contract matches (including the trickier ones: `update_action` empty-status fallback, `local_executions` shape mapping, SSE framing, CSRF/token guard, `/api/control` actions). All findings are P2/P3, conditional on specific deployment modes or user interaction sequences; the two most worth fixing before the next release are F1 (packaged-install writable paths) and F3 (stale mood draft), and F2 is a process trap that will silently disable auto-updates the first time `release.js` is run without a version bump.

---

```json
{
  "findings": [
    {
      "title": "Move all writable data paths to userData in packaged desktop mode",
      "body": "desktop/main.js:61-72 (`userDbPath`) relocates only the SQLite DB to `userData/demo.db`, but the backend keeps `alerts.log`, `hot_topics.json`, `n8n_tmp/` (weekly.lock), `exports/`, and `demo_data/` relative to ROOT (= `resources/novel-pipeline` in the packaged app) per novel_editorial/config.py:18-26, used by services/control.py `_weekly_worker`/`_alert` and `apply_schedule`. In a per-machine NSIS install (Program Files) or any read-only directory these writes fail and are swallowed by broad `except` blocks, so hot-topic refresh, weekly-meeting locking, exports, and alert logging silently break while the UI reports success. Default per-user installs (%LOCALAPPDATA%\\Programs) are writable, so the bug only manifests for per-machine/read-only install locations.",
      "confidence_score": 0.7,
      "priority": 2,
      "code_location": {
        "absolute_file_path": "E:/code/novel-editorial/desktop/main.js",
        "line_range": {"start": 61, "end": 72}
      }
    },
    {
      "title": "release.js must bump/verify the version or auto-update will never fire",
      "body": "desktop/package.json pins version 1.0.0 and desktop/release.js:6-8,50-78 derives the tag and GitHub release from `pkg.version`, deleting and re-creating the same tag on every run without ever bumping the version. main.js `setupAutoUpdater` uses electron-updater, which only downloads releases newer than the installed app's version. Unless the version is manually bumped before each `npm run release`, installed clients never receive updates while the script happily publishes fresh installers.",
      "confidence_score": 0.75,
      "priority": 2,
      "code_location": {
        "absolute_file_path": "E:/code/novel-editorial/desktop/release.js",
        "line_range": {"start": 6, "end": 8}
      }
    },
    {
      "title": "Reset moodDraft when switching agents to avoid cross-agent mood writes",
      "body": "webapp/src/components/AgentsPage.jsx:127-139 computes `currentMood = moodDraft || moodOf?.mood || {...}` but `moodDraft` is never cleared in `applyPick()` (lines 106-109) or the `[selected]` effect, and `saveMood()` posts `currentMood` for the newly selected agent. Repro: edit a mood number for agent A (don't save), click agent B, then 保存心情 — A's draft is written to B. Since mood is injected into LLM context (tools/agent_context.py:76, tools/agent_meeting.py:133), the wrong agent's state can end up in another agent's prompts.",
      "confidence_score": 0.9,
      "priority": 2,
      "code_location": {
        "absolute_file_path": "E:/code/novel-editorial/webapp/src/components/AgentsPage.jsx",
        "line_range": {"start": 127, "end": 139}
      }
    },
    {
      "title": "Reset the API auto-restart budget after a healthy period",
      "body": "desktop/main.js:100-110 increments `apiRestartCount` on every unexpected exit and never resets it, so after 3 crashes in one app session (e.g., a transient port conflict at startup plus two later hiccups over long tray uptime) the backend stays down for the rest of the session with only a notification, even when later crashes are transient and restarts would succeed.",
      "confidence_score": 0.9,
      "priority": 3,
      "code_location": {
        "absolute_file_path": "E:/code/novel-editorial/desktop/main.js",
        "line_range": {"start": 100, "end": 110}
      }
    },
    {
      "title": "Strip inline comments in desktop panelToken() to match backend parsing",
      "body": "desktop/main.js:193-198 returns `line.slice(eq+1).trim()` verbatim, while the backend reads PANEL_TOKEN via config.load_env()/`_strip_inline_comment` (novel_editorial/config.py:87-94), which strips trailing ` # ...` comments. If `~/.n8n/.env` contains `PANEL_TOKEN=xxx # comment`, the desktop sends `Bearer xxx # comment` and the backend `_guard` rejects the POST with 403, so tray triggers report 启动失败.",
      "confidence_score": 0.6,
      "priority": 3,
      "code_location": {
        "absolute_file_path": "E:/code/novel-editorial/desktop/main.js",
        "line_range": {"start": 188, "end": 203}
      }
    },
    {
      "title": "Add tests for meeting/flow/cost/editorial/command-palette components",
      "body": "No unit tests exist for MeetingLive.jsx, MeetingsPage.jsx, FlowPage.jsx, CostPage.jsx, ReaderPage.jsx, EditorialPage.jsx, agent-panels.jsx, CommandPalette.jsx, or hooks.js, even though they contain the most logic (2.5s session polling, SSE merge, claim/task flows, meeting lifecycle). The current 20 tests cover only App, Dashboard, Works, Settings, Chapters, Audit, Editorial, and Executions.",
      "confidence_score": 0.8,
      "priority": 3,
      "code_location": {
        "absolute_file_path": "E:/code/novel-editorial/webapp/src/components/MeetingLive.jsx",
        "line_range": {"start": 1, "end": 1}
      }
    }
  ],
  "overall_correctness": "patch is correct",
  "overall_explanation": "Scope: webapp/src and desktop only; baseline: vite build succeeds, all 20 vitest tests pass, node --check passes on desktop scripts, and every frontend/desktop call verified against the backend contract matches. No P0/P1 blocking issues were found; the five code findings are conditional P2/P3 (per-machine install paths, release version pinning, stale mood draft, restart budget, token comment parsing) and the sixth is a test-coverage gap.",
  "overall_confidence_score": 0.75
}
```
