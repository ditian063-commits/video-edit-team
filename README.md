# Video Edit Team

Run a DaVinci Resolve editing workflow from a single Codex conversation. The lead agent coordinates footage analysis, story and planning, editing and color matching, audio and captions, and independent delivery review. Work can start with a media inventory and end with an edit blueprint or a verified export, depending on the tools and permissions available.

The package includes the skill, five optional Codex role templates, a read-only media scanner, and an edit blueprint validator. The scanner can retain camera and color metadata with its evidence and uncertainty. The validator checks the declared color plan and delivery settings before a Resolve write.

## Install in a project

1. Clone or download this repository. Copy the complete `skills/video-edit-team` directory into your project's `.agents/skills/` directory. The entry point should be `.agents/skills/video-edit-team/SKILL.md`.
2. To install named Codex roles, copy the five `.toml` files from the installed skill's `assets/agent-roles/` into the project's `.codex/agents/`. Review any existing files with the same names before copying. The lead can use the bundled templates as task briefs when named roles are unavailable.
3. Open the project in Codex and invoke `$video-edit-team`. A GitHub skill installer can also install the `skills/video-edit-team` path into the project's skill directory.

The skill and role templates work as instructions. Running the media scanner requires Python 3.10 or newer and `ffprobe` on your `PATH`, or an explicit executable path. ExifTool can supply additional camera metadata when installed. The blueprint validator requires Python and reads local inputs. Resolve timeline creation, color work, and export require a working Resolve connection and supported operations. Configure your official Resolve MCP connection separately if you want to execute the plan in Resolve. The team can prepare a blueprint without that connection.

DSH is optional. If you already have an authorized DSH bridge, request its participation in the current run. The lead can ask it for an independent review and merge its findings into the conversation. [DSH handoff details](skills/video-edit-team/references/dsh.md)

## Start a run

> Use $video-edit-team to review the clips in `./footage` and plan a 90-second event recap. Keep meaningful location sound, match the cameras naturally, and show me the proposed timeline and delivery settings before the Resolve write.

> 使用 $video-edit-team，先分析 `./素材` 里的相机和可用片段，做一版 60 秒活动回顾的脚本与剪辑蓝图。确认后再剪辑、统一调色和导出预览。

For a narrower request, ask the lead to dispatch just the relevant role. `@素材`, `@脚本`, `@剪辑`, `@调色`, `@声音`, `@字幕`, and `@质检` are convenient names in the conversation. `@DSH` requests a review through a bridge you have configured.

The lead keeps versioned working files in a project-local run directory. Camera and input color findings record the metadata that supports them. Resolve work uses a single active editor, followed by an independent check of the actual saved timeline and export. [Workflow and handoffs](skills/video-edit-team/references/workflow.md)
