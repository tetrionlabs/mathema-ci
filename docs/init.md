# mathema-ci init

`mathema-ci init` writes a pull or merge request template and the CI
workflow that runs `mathema verify`, only where a file is missing. A file
already there is never overwritten, and each path is reported as
`written` or `kept, already there`.

```
mathema-ci init [--provider github|gitlab|both] [--dry-run]
```

| Provider | Files |
|---|---|
| GitHub | `.github/pull_request_template.md`, `.github/workflows/mathema-verify.yml` |
| GitLab | `.gitlab/merge_request_templates/Default.md`, `.gitlab-ci.mathema.yml` |

On GitLab, `init` never edits `.gitlab-ci.yml`: it prints the lines that
include the fragment, or says they are there already.

Without `--provider`, the provider is read from the project's files (a
`.github` directory; a `.gitlab-ci.yml` or `.gitlab` directory), then the
host of its `origin` remote. Signs of both, or of neither, are unclear:
`init` exits 2 and writes nothing. `--dry-run` says what would be written
and writes nothing.

The template has four sections: what changed, the claims added or
changed, the verdicts, and the accepted risks, in a table whose Expires
column is the author's own note, since `mathema accept` records no expiry
date. Both workflows carry an optional `mathema-ci gate` step after
verify.
