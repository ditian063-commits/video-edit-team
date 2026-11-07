# Editing workflow and handoffs

## Organize a run

Choose a writable project-local run folder, such as `work/runs/<run-id>/`. Keep the brief, media scan, script, blueprint, color plan, audio and caption artifacts, Resolve evidence, review, and renders together. Keep working copies and intermediate renders separate from the accepted delivery. Use a new versioned destination for rescans, revised plans, and new exports.

Each handoff records the run ID, input versions, output paths, and remaining unknowns. Resolve execution and QC records also identify the actual project, timeline, and export. Assign an owner to each output. The lead routes requested changes back to that owner.

## Scan and analyze

From the project directory, substitute your actual paths in the command below. Each `--input` accepts a media file or a directory. Repeat the flag for additional inputs. Choose a fresh scan output directory for a new version.

```sh
python .agents/skills/video-edit-team/scripts/scan_media.py --input "./footage" --output "./work/runs/event-recap/scan/v001"
```

The scan writes `media-manifest.json`, `media-manifest.sha256`, and `scan-summary.json`. Carry the summary's `metadata_manifest` reference into the blueprint. If the input set changes, update the referenced manifest and rerun validation. Sample and inspect the actual footage to identify shot ranges, dialogue, continuity, and technical issues. Keep any extraction or analysis failures visible in the inventory.

Use camera make, model, and identifiers only when supported by media tags, verified matching sidecars, or another attributable source. Keep conflicting values with their origins. A confirmed camera model does not identify the recording mode. Keep encoded color tags separate from verified input gamut and gamma, especially after a transcode. Request only the missing facts that materially affect a planned edit or transform.

## Prepare and validate the blueprint

The story role integrates a script, planned source ranges, timeline placement, color, audio, captions, and delivery choices. Use the source durations and intended frame rate and verify bounds at the intended frame precision. Identify pending inputs and transformations in the color plan. Include the authorized change scope and specific output destination in the execution handoff. [Blueprint schema](blueprint-schema.md)

```sh
python .agents/skills/video-edit-team/scripts/validate_blueprint.py "./work/runs/event-recap/blueprint/edit-v001.json" --require-color-plan --require-delivery
```

Add `--require-color-ready` when the authorized execution requires every visual clip to have a resolved color plan. The validator checks the declared plan and local inputs. Check actual application state and source boundaries before editing.

## Execute in Resolve

Discover the official Resolve MCP tools and check connection status, application version, target identity, and supported operations. Use documented calls and verify the result of every consequential write. One executor owns the live Resolve application state, including selection, playhead changes, timeline writes, grade changes, and rendering. If the change touches shared project color settings or media-pool attributes, use a new project or an independently verified copy. A copied timeline may still share those settings.

For each scene, select reference shots and normalize verified input profiles into a common working and viewing configuration. Check existing RCM, CST, LUTs, and other transforms before applying a new one. Match adjacent angles for natural continuity while respecting scene lighting. Sample the actual Resolve-processed output under the same display transform. Mark unsupported or uncertain transformations and record any affected clips. Assemble, mix, caption, and export only within the authorized plan.

## Verify the delivery

Wait for the assigned version to finish saving and rendering. Check that the project, timeline, render path, and version correspond. Inspect rendered cuts, transitions, audio sync and clarity, captions, framing, color continuity, resolution, frame rate, and playback. Review shot handles and track placement against the blueprint when they affect quality or accuracy. If read-only QC needs playback or another application state change, ask the editor to collect the evidence serially.

Track timeline assembly, color, sound and captions, render completion, and quality review as distinct outcomes. A visual or listening check requires the actual evidence. Where only a script, plan, or log was available, state what was reviewed and what remains pending. Send defect details with clip or timeline timecodes to the assigned owner and verify the affected sections of the revised export.
