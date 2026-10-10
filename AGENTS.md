# AGENTS.md (Codex and any other non-Claude agent)

Read [CLAUDE.md](CLAUDE.md) first. It is the shared project context for every agent in this repo, and its hard rules apply to you too. Task prompts are in [PROMPTS.md](PROMPTS.md). The plan and folder ownership are in [BUILD_PLAN.md](BUILD_PLAN.md), section 8.

- **When the user says "continue":** follow the "continue" protocol at the top of [PROGRESS.md](PROGRESS.md). Your owner name there is `Codex`. After finishing any prompt, even one pasted by hand, update its row in PROGRESS.md (status, notes, facts, log), then commit and push.
- Edit only the folders your track owns (BUILD_PLAN.md section 8). If you need a change anywhere else, especially `detector/golden.py`, `detector/config.py` or `docs/contracts.md`, stop and describe the change instead of making it.
- Every message, file and register format comes from `docs/contracts.md`. Don't invent field names.
- Before every push: `git pull --rebase`, run the tests for your folders, and commit with the prompt ID in the message (e.g. `P8: line buffers + tile accumulators`).
- Some prompts mention "the claude-api skill". You don't have it, so use exactly the facts written in the prompt (model ID, parameters) and don't substitute values from memory.
