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
2. Inventory the inputs with `scripts/scan_media.py` and inspect the material needed for the edit. Keep camera identity, recording mode, and the Resolve input color interpretation separate. Attach evidence and mark unknown or conflicting information.
3. Prepare the script and integrated edit blueprint. Attach the corresponding manifest version and the color, audio, captions, and export plans. Use [the blueprint schema](references/blueprint-schema.md) and `scripts/validate_blueprint.py` before execution.
4. Present the write plan together, covering target project or timeline, key edit decisions, color, audio, captions, and export. Apply existing user authorization. If additional approval is necessary, request it for that combined plan and continue within the confirmed scope once given.
5. Use one active `video_resolve` executor for all Resolve state changes and render jobs. Check the connected tool's actual capabilities and recheck the destination before writing. If a connection or operation is unavailable, deliver the completed plan and report the blocked execution steps.
6. Run independent verification after the target version is saved and the render finishes. Check the actual timeline and exported media, return concrete defects to the relevant owner, and verify the revised output before delivery.

## Color and review

Identify each source's effective input color transform before applying a correction. Match representative shots in a shared viewing transform, comparing exposure, white balance, contrast, saturation, skin tones where relevant, and the transitions between angles. Preserve meaningful lighting differences. Leave unknown or conflicting inputs pending until supported by evidence. Check for existing color management or transforms so the input is normalized once.

Use DSH when the user has configured a compatible bridge and authorized its use for this project or run. The lead owns one bridge task at a time and incorporates its findings into the local review. [Optional DSH workflow](references/dsh.md)
