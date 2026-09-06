# Fix setup-uv action reference

Status: resolved
Type: task

The publish-image run failed during job setup because `astral-sh/setup-uv@v10`
does not resolve. Use the published `v10.0.1` tag.

Run: https://github.com/SarthakMishra/spotify-playlist-sorter/actions/runs/34047246969

## Validation

GitHub confirms `refs/tags/v10.0.1` resolves to
`20cfd1bf945f4377ade1205e4dbc17946fc9a30d`.

`task check` passed, including 44 tests and the frontend production build.
`git diff --check` passed.

## Answer

Changed `.github/workflows/publish-image.yml` to use `astral-sh/setup-uv@v10.0.1`.
The fix is local; GitHub Actions has not been rerun.
