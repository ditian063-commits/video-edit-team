# Optional DSH review

Use this path when the user already has a DSH bridge and authorizes it for the project or run. Discover the bridge and its tools in the current runtime, then verify its connection and the existing DSH workspace identity. Resolve the workspace and task routing from the user's configuration.

The lead coordinates all bridge requests. Typical handoffs include a source evidence and script review before the edit, a blueprint and color plan review before execution, or an independent review of the delivery evidence. The local specialist who owns an output makes any resulting revision.

1. Check the bridge's existing tasks and refresh unfinished states before submitting. Maintain one unfinished bridge task at a time, including tasks waiting for input or attention.
2. Send a narrowly scoped review with the run ID, stage, version, specific questions, accessible input paths, and an evidence summary. For rendered work, identify the actual project, timeline, and export. Share only materials authorized for this task. Confirm the remote workspace can read the supplied paths, or record the access gap.
3. Use `read_only` if the bridge supports task modes. When the user authorizes a written result, assign a separate output location. Keep Resolve state changes with `video_resolve` and integrate any proposed changes through the owner of the relevant artifact. Task mode describes the assignment and may not impose filesystem isolation.
4. Record the task ID, input version, and expected result in the run. Wait for the bridge's native completion state and retrieve the matching result before treating the review as complete. Keep old findings attached to their original input versions.
5. Route a request for user input or permission to the user through the bridge's supported workflow. If the bridge fails, record the failure and continue local work that can proceed independently. Report the status of the external review accurately. Visual and audio review claims require access to the corresponding output.

The local five-role workflow can proceed when no DSH connection is configured.
