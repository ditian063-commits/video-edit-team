# Optional DSH review

Use this path when the user already has a DSH bridge and authorizes it for the project or run. Discover the bridge and its tools in the current runtime, then verify its connection and the existing DSH workspace identity. Resolve the workspace and task routing from the user's configuration.

The lead coordinates all bridge requests. Use the plan review to check authorization, version consistency, and unresolved shot, audio, or color risks. Use the delivery review to check the exact saved timeline and finished render, repair scope, and unresolved issues. The local validator checks structure and local QC checks the actual output. Send their evidence instead of asking the bridge to repeat the entire scan or QC procedure. The specialist who owns an output makes any resulting revision.

1. Check the bridge's existing tasks and refresh unfinished states before submitting. Maintain one unfinished bridge task at a time, including tasks waiting for input or attention.
2. Generate the `dsh-plan` or `dsh-delivery` packet with `scripts/make_handoff.py` from the corresponding blueprint. Add the run ID, stage-specific question, and authorized evidence that the bridge can read. For delivery include the exact finished render and the current QC and timeline evidence. Share compact references and hashes instead of duplicating the reports.
3. Use `read_only` if the bridge supports task modes. When the user authorizes a written result, assign a separate output location. Keep Resolve state changes with `video_resolve` and integrate any proposed changes through the owner of the relevant artifact. Task mode describes the assignment and may not impose filesystem isolation.
4. Record the task ID, input version, and expected result in the run. While the plan review runs, prepare the storyboard or perform independent preflight work. During delivery review, prepare and verify the staging copy where authorized. Check native completion and retrieve the matching result before treating the review as complete. Keep old findings attached to their original input versions.
5. Route a request for user input or permission to the user through the bridge's supported workflow. If the bridge fails, record the failure and continue local work that can proceed independently. Report the status of the external review accurately. Visual and audio review claims require access to the corresponding output.

The local team can proceed when no DSH connection is configured.
