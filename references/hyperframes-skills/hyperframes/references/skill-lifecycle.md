# Skill lifecycle — course-notes bundled adaptation

The ten HyperFrames entry/domain skills plus `faceless-explainer` and `general-video` are already bundled under this repository's `references/hyperframes-skills/`. Their relative links and scripts must resolve inside the bundle. **Do not run `npx hyperframes skills`, `skills update`, `skills check`, or `npx skills add` in this course-notes workflow.** These commands change global skill installations and do not upgrade this bundled copy. The CLI itself remains a separate software dependency.

CLI `init` may attempt to update global Agent skills; disable that side effect using `HYPERFRAMES_SKIP_SKILLS=1` in the command environment (PowerShell: `$env:HYPERFRAMES_SKIP_SKILLS='1'`; bash: `HYPERFRAMES_SKIP_SKILLS=1 npx hyperframes init ...`). The `--skip-skills` flag is not reliable for this purpose. A CLI update is a separate dependency change, subject to the user's installation/overwrite permission and project lockfile verification; it does **not** rewrite the bundled skills.

For other workflow names mentioned in upstream references but absent from this bundle, ask the user whether to expand scope and package that workflow before use; do not fall back to home-installed skills or fetch instructions ad hoc.
