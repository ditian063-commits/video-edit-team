# Blueprint Schema

Use UTF-8 JSON with this minimum shape:

```json
{
  "schema_version": "1.0",
  "project": {
    "name": "Example",
    "fps": 30,
    "width": 1920,
    "height": 1080,
    "target_duration_seconds": 480
  },
  "tracks": {
    "video": ["V1"],
    "audio": ["A1", "A2"]
  },
  "clips": [
    {
      "id": "clip-001",
      "media_type": "video",
      "source_path": "/absolute/path/source.mp4",
      "source_in_seconds": 12.5,
      "source_out_seconds": 19.0,
      "timeline_in_seconds": 0.0,
      "timeline_out_seconds": 6.5,
      "video_track": 1,
      "audio_track": 1,
      "purpose": "Open on the central action",
      "source_group": "camera-a",
      "confidence": 0.9
    }
  ],
  "narration": [],
  "music": [],
  "captions": [],
  "notes": []
}
```

Rules:

- Use absolute source paths at build time.
- Keep `source_out_seconds` within probed duration.
- Require positive duration and matching source/timeline duration unless a
  speed change is declared.
- Declare still-image duration explicitly.
- Record music, LUT, retime, crop, stabilization, and audio processing as
  explicit authorized operations.
- When the plan targets Resolve, record the intended `timeline` alongside
  `project` and keep their known identities with the versioned blueprint.

## Color plan for the single-chat editing team

Legacy blueprints remain valid without `color_plan`, but they are assembly-only
plans and do not establish color readiness. The `video-edit-team` workflow adds
the object below. Keep the existing top-level blueprint shape; color plan
versioning is independent from the legacy `schema_version`.

```json
{
  "color_plan": {
    "version": "1.0",
    "metadata_manifest": {
      "path": "/absolute/project/work/runs/example/scan/media-manifest.json",
      "sha256": "<actual 64-character SHA-256 of this manifest file>"
    },
    "working_space": {"gamut": "DaVinci Wide Gamut", "gamma": "DaVinci Intermediate"},
    "output_space": {"gamut": "Rec.709", "gamma": "Gamma 2.4"},
    "clips": [
      {
        "clip_id": "clip-001",
        "scene_id": "interview-room",
        "reference_clip_id": "clip-001",
        "input": {
          "gamut": {
            "value": "S-Gamut3.Cine",
            "status": "confirmed",
            "evidence": [
              {"source": "verified associated camera sidecar", "field": "captureGamut", "value": "S-Gamut3.Cine"}
            ]
          },
          "gamma": {
            "value": "S-Log3",
            "status": "confirmed",
            "evidence": [
              {"source": "verified associated camera sidecar", "field": "captureGamma", "value": "S-Log3"}
            ]
          }
        },
        "existing_input_transforms": [],
        "action": "apply",
        "input_transform": {"method": "rcm"},
        "adjustments": ["exposure", "white_balance", "contrast", "saturation", "skin_tone", "shot_match"],
        "unresolved": []
      }
    ]
  }
}
```

This is a structural example, not a universal Sony profile or an instruction to
assume SDR output. Set the actual working/output targets in the approved brief.
Replace the manifest path, SHA-256, source evidence and clip IDs with this run's
values. Evidence entries always contain nonempty `source`, `field`, and `value`;
point `source` to the actual file, Resolve snapshot, or user confirmation record.
The validator checks the manifest hash and evidence structure, not whether a
photometric claim is true; the analyst and editor must reconcile the evidence.

### Per-clip decisions

- Cover every blueprint video/image clip exactly once by `clip_id`. Audio clips
  do not receive color entries. The IDs refer to timeline occurrences, so two
  uses of the same source may have different scene matching adjustments.
- `input.gamut` and `input.gamma` each carry `value`, `status`, and `evidence`.
  Allowed statuses are `confirmed`, `candidate`, `unknown`, and `conflicting`.
  Unconfirmed values do not authorize conversion. An unknown value can be `null`
  with empty evidence. Camera model and codec color tags alone do not prove the
  original capture profile; keep encoded tags separate from verified input.
- `scene_id` is required. Ready clips require a `reference_clip_id` with a color
  entry in the same scene; a reference may be the clip itself. A blocked clip may
  use `null` until a representative reference is available. A ready clip cannot
  depend on a blocked reference.
- `existing_input_transforms` records every effective input normalization,
  including project RCM, clip CST/LUT and already baked transforms. Inspect the
  actual Resolve state before filling it; an empty array is an affirmative
  declaration that no existing input normalization applies. Creative look
  adjustments are not input normalizations.
- `adjustments` is an array of intentions for the editor, not blind numeric
  controls. Match exposure, white balance and skin tone while preserving scene
  lighting. The runtime resolves supported API calls and verifies actual output.

Choose one action:

| Action | Preconditions and behavior |
| --- | --- |
| `apply` | Both input fields confirmed with evidence; no existing input transform; exactly one `input_transform` method (`rcm`, `cst`, or `lut`) maps the declared input into `working_space`. For `lut`, supply an existing absolute `lut_path`. Never combine RCM and another input conversion. |
| `already_normalized` | Both input fields confirmed; `input_transform` is `null`; either the input already equals `working_space`, or exactly one existing transform has attributable evidence and `output_space` equal to `working_space`. Apply only shot matching, not a second input conversion. |
| `blocked` | `input_transform` is `null`; `unresolved` contains the reason. Preserve known state for review. Do not execute this clip's color work or report it as finished. Other ready clips may proceed. |

An existing normalization record has this shape:

```json
{
  "method": "rcm",
  "output_space": {"gamut": "DaVinci Wide Gamut", "gamma": "DaVinci Intermediate"},
  "evidence": [
    {"source": "resolve/state-v1.json", "field": "verified effective input conversion", "value": "RCM to working space"}
  ]
}
```

Allowed existing methods are `rcm`, `cst`, `lut`, and `baked`. If current state
contains competing input transforms, choose `blocked`, explain the conflict,
and inspect it before proposing a corrected version. Do not hide existing
transforms to make validation pass. Unresolved input issues always require a
blocked action; they cannot coexist with a ready action.

### Validation and completion

Use these commands from the skill directory (Windows uses `py -3`):

```powershell
py -3 scripts/validate_blueprint.py <blueprint.json> --require-color-plan
py -3 scripts/validate_blueprint.py <blueprint.json> --require-color-ready
```

The first checks structure, provenance, coverage and transform safety. It allows
a valid plan with explicit blocked clips, so inspect `color_plan.ready_clip_ids`
and `blocked_clip_ids` before dispatching partial work. The second also rejects
any blocked clip and implies `--require-color-plan`. Neither command executes
Resolve or establishes successful grading.

The JSON report distinguishes `plan_valid` (structural correctness),
`all_clips_ready`, `ready_clip_ids`, `blocked_clip_ids`, `blocked_reasons`, and
`invalid_clip_ids`. Invalid plans expose no ready IDs. A valid blocked plan may
still have `plan_valid: true` when the stricter readiness command fails; its
`errors` and nonzero exit code prohibit full execution. Reports identify this as
`verification: "plan_only_not_render_verification"`.

After writes, inspect Resolve settings and supported LUT/property readbacks,
then compare actual Resolve-rendered representative frames and adjacent cut
boundaries under one known display transform. Analysis JPEGs are not a grading
reference. Color completion requires successful actual rendering and inspection
of the delivered timeline version, with remaining mismatches reported by clip.

## Delivery specification

Before the team's export approval, `video_resolve` proposes the settings and
`video_story` stores them in the blueprint's top-level `delivery` object.
The main chat confirms this version; QC compares the actual output with it.
No universal resolution, frame rate, codec, SDR/HDR target or subtitle mode is
assumed. The following is only an example:

```json
{
  "delivery": {
    "output_path": "/absolute/project/work/runs/example/renders/preview-v1.mp4",
    "final_delivery_path": "/absolute/project/outputs/recap-v1.mp4",
    "container": "mp4",
    "video_codec": "h264",
    "audio_codec": "aac",
    "width": 1920,
    "height": 1080,
    "fps": 24,
    "range": {"start_seconds": 0, "end_seconds": 60},
    "color_space": {"gamut": "Rec.709", "gamma": "Gamma 2.4"},
    "subtitle_mode": "sidecar"
  }
}
```

- `output_path` must be an absolute new file path, distinct from all source
  files. A missing parent directory is allowed; validation does not create it.
  Rerenders use a new versioned path. Work renders remain under the run directory;
  only an accepted final file is copied to the user's delivery directory.
- If delivery involves a separate destination, record it once as the optional
  absolute `final_delivery_path`. Check that it is authorized and available
  before publishing the accepted export. Derive the confirmation and all
  handoffs from these fields.
- `container`, `video_codec`, and `audio_codec` are explicit nonempty strings.
  Use `none` for an intentionally silent video. The executor must verify that
  the running Resolve version supports the selected combination; this schema
  validator does not assert encoder availability.
- Dimensions are positive integers; `fps` is a finite positive number.
  Range values are seconds relative to the timeline start and satisfy
  `0 <= start_seconds < end_seconds`; translate with the actual timeline origin
  and verify against the intended edit at execution time.
- `color_space.gamut/gamma` must match `color_plan.output_space`. The executor
  derives supported output tags from this declared target and verifies them
  in the exported file. Matching declaration strings is not a visual test.
- `subtitle_mode` is `burn_in`, `sidecar`, or `none`. Sidecar subtitles remain
  tied to the same timeline/export version.

```powershell
py -3 scripts/validate_blueprint.py <blueprint.json> --require-color-ready --require-delivery
```

`delivery` stays optional for legacy assembly workflows; when present it is
always checked. `--require-delivery` makes it mandatory for team export
preflight. It must run before rendering, when the planned output does not yet
exist; post-render QC compares the actual file and tags with this specification
instead of rerunning a new-file preflight on an existing render.
The report is labelled `spec_only_not_render_verification` and validation never
creates a render job or reports a successful export.
