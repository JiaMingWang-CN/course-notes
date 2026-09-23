# Bundled HyperFrames skill sources

Source: https://github.com/heygen-com/hyperframes (skills/ directories). License: Apache License 2.0; full text in `LICENSE`. Original copyrights and attribution remain with the upstream authors. The `hyperframes` original entry file was compared byte-for-byte against the upstream `main` copy at integration time; `general-video` and `faceless-explainer` were fetched from upstream `main` for their required workflow scripts/references. The other ten directories were copied from the locally installed HyperFrames skill set.

The course-notes repository's own licensing statement is separate; this bundled subtree is distributed under Apache-2.0, including its notices/attributions. No user keys, downloaded course footage, project media, `.env` or generated outputs are included.

## Modifications from upstream (course-notes integration)

- `hyperframes/SKILL.md`: added local course-notes mapping and replaced the global workflow-install section with local bundled workflow entry.
- `hyperframes/references/skill-lifecycle.md` and `hyperframes/references/capability-menu.md`: removed global skill install/borrow instructions in the course-notes integration.
- `faceless-explainer/SKILL.md`: added local mapping, suppressed global skill updates, made `init` skip skill updates, and pointed MEDIA_DIR to the bundled sibling.
- `general-video/SKILL.md`: same local mapping and `init` changes; forbids borrowing unbundled workflows.
- `media-use/scripts/lib/media-fetch.mjs`: replaced the upstream compatibility re-export pointing outside the skill tree with the upstream canonical implementation from `packages/cli/src/media-use/lib/media-fetch.mjs`, so the bundled script has no missing local import.
- `faceless-explainer/scripts/{assemble-index,transitions,audio}.test.mjs`: used `fileURLToPath` for cross-platform spawned script paths in Windows tests; the audio test skips its equality assertion against the unbundled PR workflow.
- Repository-level `SKILL.md` and `references/COURSE_VIDEO.md` own course confirmation, teaching evidence, output routing and permissions. They are not upstream files.

All other bundled files are copied without intentional edits. Runtime dependencies (HyperFrames CLI, GSAP, Node.js, FFmpeg, browsers, optional provider services) are **not** bundled.

Integration checks: `python scripts/verify_bundled_skills.py` resolves all 12 entries, Markdown relative links and `.mjs` relative imports. The selected course workflow tests pass (21 passed, 1 skipped because the PR workflow is outside this bundle). The whole upstream test collection is **not** green when transplanted outside its original monorepo (136 passed, 23 failed, 1 skipped on this Windows host): failures include tests that assume unbundled workflow copies, upstream monorepo paths, unavailable symlink privilege, and npm/FFmpeg environment assumptions. No actual course composition or MP4 render has been verified; do not claim feature equivalence until a representative HTML + MP4 fixture passes end to end.
