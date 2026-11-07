---
name: video-edit-team
description: Coordinate a five-role video editing team from one conversation, including media and camera analysis, story and shot planning, DaVinci Resolve editing and cross-camera color matching, audio and captions, and independent delivery review. Use for video editing plans or end-to-end editing tasks involving user-provided media.
---

# Video Edit Team

Act as the lead and return a single user-facing result. Use [the workflow reference](references/workflow.md) to create a run, dispatch specialists, and transfer evidence between stages. Use the user's requested language, format, delivery location, and editing scope.

## Roles

| Role | Responsibility |
| --- | --- |
| `video_footage` | Media inventory, usable ranges, camera evidence, input color evidence |
| `video_story` | Script, pacing, source-backed shot choices, integrated blueprint |
| `video_resolve` | Color plan, Resolve writes, timeline and export evidence |
| `video_audio_captions` | Dialogue, sound, caption timing, and assigned audio assets |
| `video_qc` | Independent timeline and rendered output verification |

Dispatch only roles needed by the current request. Parallelize independent work and keep up to three specialists active at once. A specialist returns results to the lead. The lead handles any further dispatch. Use the named role when the runtime supports it. Otherwise use its bundled template under `assets/agent-roles/` as a task brief, or perform the roles in sequence if subagents are unavailable. Give each role its inputs, version, output path, authorized operations, and acceptance criteria.

## Run the edit

1. Gather missing information that affects the result, such as media locations, duration, framing, story purpose, language, and delivery format. Establish the versioned run directory and preserve original media.
2. Scan the inputs once per version and share the resulting evidence, including the audio inventory. In parallel, have `video_resolve` identify the current project, timeline, and project music read-only when relevant. Shortlist useful ranges while the sound role analyzes the chosen music. Keep camera identity, recording mode, and input color interpretation separate.
3. Build one integrated blueprint. Shortlist first, then use `scripts/screen_selected_windows.py` and a visual review on the actual selected source windows before assembly. Use [the blueprint schema](references/blueprint-schema.md) and `scripts/validate_blueprint.py` for plan validation. The blueprint owns project and timeline identity, audio, color, captions, and delivery settings.
4. Generate the confirmation summary, Resolve handoff, and applicable DSH packets from the same blueprint with `scripts/make_handoff.py`. Show the storyboard where the user can view it and confirm the combined write scope once when needed. Continue within that scope after approval.
5. Use one active `video_resolve` executor for all Resolve state changes and render jobs. Reuse operations validated against the connected version, verify actual writes and destination, and keep the execution evidence. If a connection or operation is unavailable, deliver the completed plan and report the pending steps.
6. Verify the actual saved timeline and finished export independently. After a bounded repair, verify changed clips and adjacent cuts against the new export and carry forward documented visual coverage only when the corresponding timeline settings and unchanged edits match. Recheck the whole new file's technical integrity. Record actual listening or its status separately from numeric audio measurements.

## Color and review

Identify each source's effective input color transform before applying a correction. Match representative shots in a shared viewing transform, comparing exposure, white balance, contrast, saturation, skin tones where relevant, and the transitions between angles. Preserve meaningful lighting differences. Leave unknown or conflicting inputs pending until supported by evidence. Check for existing color management or transforms so the input is normalized once.

Use DSH when the user has configured a compatible bridge and authorized its use for this project or run. The lead owns one bridge task at a time and incorporates its findings into the local review. [Optional DSH workflow](references/dsh.md)
