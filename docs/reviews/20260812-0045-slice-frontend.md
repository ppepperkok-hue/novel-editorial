Review complete. Here is my report.

**Scope reviewed**: `webapp/src` (all components, api/hooks/stores, tests) and `desktop` (`main.js`, `preload.js`, `release.js`, `package.json`). Backend files read only to verify API contracts (`web_api.py`, `services/control.py`, `services/ending.py`, `services/misc.py`, `services/dashboard.py`, `services/activity.py`, `tools/daily_runs.py`, `tools/write_diaries.py`, `tools/mailroom.py`, `services/meeting_session.py`, `services/editorial.py`).

**Baseline (targeted, per slice constraints)**: `node --check` on all desktop JS files — pass (exit 0). `npm run build` (webapp) — pass, 984 modules, only a >500 kB chunk warning. `npm test` (vitest) — 7 files / 16 tests all pass. Encoding verified: all UTF-8 files are valid (console mojibake was a PowerShell GBK display artifact); no secrets or hardcoded absolute paths found in the slice.

```json
{
  "findings": [
    {
      "title": "[P1] release.js aborts before creating a release because `gh release view` throws when the release is missing",
      "body": "In `desktop/release.js`, line 49 `const exists = gh(\`release view v${version} ...\`)` calls `execSync`, which throws on the non-zero exit `gh` returns for a missing release. The try/catch at lines 51-55 wraps `release delete`, not `view`, so on the normal first-time release path the script dies at line 49 and `gh release create` (line 57) is never reached. Re-runs fail even earlier: line 45 `git tag v${version}` exits non-zero when the tag already exists, contradicting the `--clobber`/idempotent re-run comments. As written, the script can never complete a release (first run or re-run).",
      "confidence_score": 0.9,
      "priority": 1,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\desktop\\release.js",
        "line_range": {"start": 45, "end": 57}
      }
    },
    {
      "title": "[P2] AgentsPage passes `.md`-suffixed agent key to diary/state APIs, so diaries never load and moods never match",
      "body": "`agents_list()` returns `file` values like `\"planner.md\"` (glob of `*.md`), and `AgentsPage` uses `selected.file` directly for `getDiaries(selected.file)` (line 75) and `states.find((s) => s.agent === selected?.file)` (line 127), while `agent_diaries.agent` and `agent_states.agent` store the stem (`\"planner\"`, see `tools/write_diaries.py` AGENTS and `misc.update_state`). Result: the 记忆与日记 list always shows 暂无日记 and the 当前心情 panel always shows defaults instead of the weekly-inferred mood. `updateAgentState(selected.file, 0, currentMood)` (line 137) also writes a divergent `\"planner.md\"` row that the backend never reads. Line 78 correctly strips `.md` for memories, confirming the inconsistency.",
      "confidence_score": 0.85,
      "priority": 2,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\webapp\\src\\components\\AgentsPage.jsx",
        "line_range": {"start": 75, "end": 75}
      }
    },
    {
      "title": "[P2] WorksPage 新书创意 panel reads fields that /api/ending/status never returns",
      "body": "`WorksPage.jsx` lines 257-262 render `nextBook.premise || nextBook.abstract`, `JSON.parse(nextBook.tags || \"[]\")` and `nextBook.selling_point` from the `/api/ending/status` payload, but `ending_service.ending_status` (`novel_editorial/services/ending.py:11-15`) selects only `id, title, status, book_id, cover_prompt, target_chapters, finish_remaining, finish_note, updated_at`. For a planning/ready novel the panel therefore shows an empty premise, no tag chips and no selling point, leaving a mostly blank 新书创意 card. The columns exist in `novels` (dashboard `load_novels` selects them), so this is a frontend/backend contract mismatch, not a schema issue.",
      "confidence_score": 0.9,
      "priority": 2,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\webapp\\src\\components\\WorksPage.jsx",
        "line_range": {"start": 257, "end": 262}
      }
    },
    {
      "title": "[P3] DashboardPage '本次发布几章' modal and runNow are unreachable dead code",
      "body": "The modal is gated on `confirm === \"run\"` (line 590) but no code path ever calls `setConfirm(\"run\")` — the only setters are `setConfirm(\"pause-daily\")` and `setConfirm(null)` (verified by grep). Consequently `runNow` (lines 79-90) and the chapter-picker modal (lines 590-622) can never execute; the 编辑部开工 card uses `openWorkday(\"write\", ...)` instead. Dead code that should be removed or rewired.",
      "confidence_score": 0.95,
      "priority": 3,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\webapp\\src\\components\\DashboardPage.jsx",
        "line_range": {"start": 590, "end": 591}
      }
    },
    {
      "title": "[P3] desktop/main.js registers app:install-update IPC that preload.js never exposes",
      "body": "`ipcMain.handle(\"app:install-update\", ...)` is registered inside the `update-downloaded` event (lines 198-200), but `preload.js` exposes no `installUpdate` method, so the handler is unreachable from the renderer. Additionally, registering the handler inside the event would throw \"Attempted to register a second handler\" if `update-downloaded` ever fired twice in one session. Either expose the method in the preload or drop the handler.",
      "confidence_score": 0.8,
      "priority": 3,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\desktop\\main.js",
        "line_range": {"start": 198, "end": 200}
      }
    },
    {
      "title": "[P3] desktop/main.js spawns pythonw without an error handler, so a missing Python crashes the app instead of failing gracefully",
      "body": "`apiProc = spawn(PYTHONW, ...)` (lines 58-62) has `stdio: \"ignore\"` and no `apiProc.on(\"error\", ...)` listener. If `pythonw` is not on PATH (Python is only a documented prerequisite, not bundled), Node emits an unhandled `error` event (ENOENT) on the child process, crashing the Electron main process — bypassing the intended 20 s `apiReady` loop and the throw at line 67. In packaged mode `console.error` is invisible, so the user sees a silent exit. An `error` listener that rejects `ensureApi()` would route it to the existing quit path.",
      "confidence_score": 0.7,
      "priority": 3,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\desktop\\main.js",
        "line_range": {"start": 58, "end": 62}
      }
    },
    {
      "title": "[P3] No component tests for most pages; only 16 tests cover 12 routes",
      "body": "The Vitest suite (7 files, 16 tests) covers App shell/navigation, ChaptersPage, WorksPage and one DashboardPage helper. SettingsPage, AgentsPage, MeetingLive/MeetingsPage, CostPage, ReaderPage, FlowPage, ExecutionsPage and EditorialPage have zero component tests — notably the pages where the P2 findings above (diary/mood agent-key mismatch, 新书创意 contract mismatch) live, so neither regression was caught. Adding smoke tests for those pages would have surfaced both.",
      "confidence_score": 0.8,
      "priority": 3,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\webapp\\src\\__tests__\\app.test.jsx",
        "line_range": {"start": 1, "end": 1}
      }
    }
  ],
  "overall_correctness": "patch is incorrect",
  "overall_explanation": "Scope: webapp/src + desktop (baseline: webapp build OK, 16/16 vitest OK, node --check OK on all desktop JS). The release script can never complete a release (P1), and three user-facing features are degraded by contract mismatches: Agent diaries/moods never load or diverge on save, and the 新书创意 panel renders blank fields (P2). Remaining items are dead code and robustness gaps (P3). No P0 issues: no data loss, crashes in the normal runtime path, or security problems were found in the slice.",
  "overall_confidence_score": 0.8
}
```
