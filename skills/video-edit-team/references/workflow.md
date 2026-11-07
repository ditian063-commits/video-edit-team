# Editing workflow and handoffs

## Organize a run

Choose a writable project-local run folder, such as `work/runs/<run-id>/`. Keep the brief, media scan, script, blueprint, color plan, audio and caption artifacts, Resolve evidence, review, and renders together. Keep working copies and intermediate renders separate from the accepted delivery. Use a new versioned destination for rescans, revised plans, and new exports.

Each handoff records the run ID, input versions, output paths, and remaining unknowns. Resolve execution and QC records also identify the actual project, timeline, and export. Assign an owner to each output. The lead routes requested changes back to that owner.

## Scan and analyze

From the project directory, substitute your actual paths in the command below. Each `--input` accepts a media file or a directory. Repeat the flag for additional inputs. Choose a fresh scan output directory for a new version.

```sh
python .agents/skills/video-edit-team/scripts/scan_media.py --input "./footage" --output "./work/runs/event-recap/scan/v001"
```

The scan writes `media-manifest.json`, `media-manifest.sha256`, and `scan-summary.json`. Carry the summary's `metadata_manifest` reference into the blueprint. If the input set changes, update the referenced manifest and rerun validation. Share a single inventory of stream presence and any audio probe results. If the brief calls for music only, deep measurements of each unused source track add little. The Resolve operator can identify the open project and its available music read-only while footage is sampled. Hand music identity to the sound role early so it can select an excerpt and timing while the story role shortlists clips.

Use representative frames for the initial shortlist, then inspect the exact source windows selected in the blueprint. Run `scripts/screen_selected_windows.py` on those video windows for black, near-white, and abrupt brightness candidates at source cadence. Review candidates in context and inspect risk-prone heads, tails, and internal transitions at frame level for focus or unwanted remnants. Keep viable replacement ranges. A candidate can be an intended lighting change, and a clean signal report does not establish visual quality. Keep decode failures and coverage gaps visible and resolve issues before assembly.

```sh
python .agents/skills/video-edit-team/scripts/screen_selected_windows.py "./work/runs/event-recap/blueprint/edit-v001.json"
```

Use camera make, model, and identifiers only when supported by media tags, verified matching sidecars, or another attributable source. Keep conflicting values with their origins. A confirmed camera model does not identify the recording mode. Keep encoded color tags separate from verified input gamut and gamma, especially after a transcode. Request only the missing facts that materially affect a planned edit or transform.

## Prepare and validate the blueprint

The story role integrates a script, planned source ranges, timeline placement, color, audio, captions, and delivery choices. Use the source durations and intended frame rate and verify bounds at the intended frame precision. Identify pending inputs and transformations in the color plan. Include the authorized change scope and specific output destination in the execution handoff. [Blueprint schema](blueprint-schema.md)

```sh
python .agents/skills/video-edit-team/scripts/validate_blueprint.py "./work/runs/event-recap/blueprint/edit-v001.json" --require-color-plan --require-delivery
```

Add `--require-color-ready` when the authorized execution requires every visual clip to have a resolved color plan. The validator checks the declared plan and local inputs. Check actual application state and source boundaries before editing.

Keep export names and the authorized delivery destination in `delivery`. Project and timeline identity, chosen music excerpt, subtitle and color decisions, and export settings should flow from this blueprint into the confirmation, execution, and bridge packets. Generate these with `scripts/make_handoff.py` using the applicable `--stage` value (`confirm`, `resolve`, `dsh-plan`, or `dsh-delivery`) and repeat `--evidence` for necessary supporting files. The packet includes the blueprint hash. Show a viewable storyboard with the one confirmation when approval is needed. Apply previous authorization to decisions already made. A materially changed scope requires an updated confirmation.

```sh
python .agents/skills/video-edit-team/scripts/make_handoff.py "./work/runs/event-recap/blueprint/edit-v001.json" --stage confirm --evidence "./work/runs/event-recap/storyboard.jpg"
```

Use the JSON packet to compose a short, readable confirmation. Supply the approval record to the `resolve` packet when needed. For `dsh-delivery`, include the actual exported file at the blueprint's `output_path` or `final_delivery_path` as evidence, along with the relevant QC and timeline records.

## Execute in Resolve

Discover the official Resolve MCP tools and check connection status, application version, target identity, and supported operations. Use documented calls and verify the result of every consequential write. One executor owns the live Resolve application state, including selection, playhead changes, timeline writes, grade changes, and rendering. If the change touches shared project color settings or media-pool attributes, use a new project or an independently verified copy. A copied timeline may still share those settings.

Reuse verified import, source-endpoint, and render parameter conventions for the connected version. Confirm a small placement probe and check source start plus duration against the actual readback before batch placement. Compare saved timeline and track state in equivalent application contexts.

For each scene, select reference shots and normalize verified input profiles into a common working and viewing configuration. Check existing RCM, CST, LUTs, and other transforms before applying a new one. Match adjacent angles for natural continuity while respecting scene lighting. Sample the actual Resolve-processed output under the same display transform. Mark unsupported or uncertain transformations and record any affected clips. Assemble, mix, caption, and export only within the authorized plan.

## Verify the delivery

Wait for the assigned version to finish saving and rendering. Check that the project, timeline, render path, and version correspond. Inspect rendered cuts, transitions, audio sync and clarity, captions, framing, color continuity, resolution, frame rate, and playback. Review shot handles and track placement against the blueprint when they affect quality or accuracy. If read-only QC needs playback or another application state change, ask the editor to collect the evidence serially.

Track timeline assembly, color, sound and captions, render completion, and quality review as distinct outcomes. Run technical checks on the finished file, including full decode and output dimensions, frame rate, frame count, and audio properties. Review audio with the rendered picture when playback is available, including the music cut-in, phrasing, timing, and fade-out. Record listening separately from loudness or peak measurements.

Send defects with clip IDs or timeline timecodes. For a bounded repair, preserve the previous version and compare the new blueprint and Resolve readback. Review the changed shots and their neighboring cuts on the actual new output. Carry forward earlier visual coverage only for verified unchanged edits and relevant render/color settings. Run whole-file technical checks again and bind acceptance to the final file's identity.
