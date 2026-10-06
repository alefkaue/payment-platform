<!-- LOVABLE:BEGIN -->

> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.

<!-- LOVABLE:END -->

## Architecture rules

- All data access goes through `src/lib/api.ts` (mock-backed today, typed to mirror the real backend); screens never import `src/mocks` directly — keeps the backend swap a one-file change.
- Split math lives only in `src/lib/split.ts` (cbs/ibs rounded, liquido = remainder, PJ only) — single source of truth matching the backend.
- Authenticated screens live under the pathless `_app` layout (TanStack Router, not React Router) — the template's router is fixed.
