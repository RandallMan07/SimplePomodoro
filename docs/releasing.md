# Publish SimplePomodoro 0.1.0

Run these steps in a regular terminal from the project directory. The editing
session could not initialize Git because its `.git` directory was mounted read-only.
The commands below use the exact tag `0.1.0`, without a `v` prefix.

## 1. Install tools and initialize Git

On Arch Linux:

```sh
sudo pacman -S --needed git github-cli base-devel desktop-file-utils python python-gobject python-cairo gtk4 libadwaita gstreamer gst-plugins-base gst-plugins-good
git init -b main
```

If Git does not already have your author identity, set it for this repository.
Replace these example values. You may use your GitHub-provided no-reply email:

```sh
git config user.name "Your Name"
git config user.email "YOUR_GITHUB_NOREPLY_EMAIL"
```

MIT has been selected and added to `LICENSE`. Its copyright attribution currently
uses `SimplePomodoro contributors`; replace that with your preferred author name
or pseudonym if desired before making the first commit.

## 2. Check what will be uploaded

```sh
git status --short --untracked-files=all
git check-ignore dist/ .aws/ .agents/ .codex/
```

The source, runtime assets, tests, packaging scripts, documentation, license, and
GitHub workflow belong in Git. Build output, Python caches, environments, local
credentials, and agent configuration are ignored. Ignore rules do not inspect file
contents: review any files containing personal paths or other information you do
not want to publish. They also do not remove files already tracked by Git.

## 3. Validate and build downloads

```sh
PYTHONPATH=src /usr/bin/python -m unittest discover -s tests -v
PYTHONPATH=src /usr/bin/python tests/gtk_smoke.py
python3 packaging/build.py
```

Run makepkg as your normal user. Exit 77 from the smoke check means no display was
available, so run that check from your desktop. Complete the manual checks in
`docs/verification.md`, including installing the package and launching it.

The build produces:

- `dist/simplepomodoro-0.1.0.tar.gz`
- `dist/simplepomodoro-0.1.0-1-any.pkg.tar.zst`
- `dist/SHA256SUMS`

Verify both checksums:

```sh
cd dist
sha256sum --check SHA256SUMS
cd ..
```

The source-only command is `python3 packaging/build.py --source-only`. It rewrites
`SHA256SUMS` to list only the source archive; run the full build again before
publishing both downloads. These are local snapshot builds: include all intended
changes in the commit below, then rebuild from that clean checkout for release.

## 4. Make the initial commit

```sh
git add .
git diff --cached --stat
git diff --cached
git commit -m "Add SimplePomodoro 0.1.0"
git status --short
```

The final status should be empty. Review the staged diff before committing.

## 5. Create the GitHub repository

Authenticate, then create and upload the repository:

```sh
gh auth login
gh repo create SimplePomodoro --public --source=. --remote=origin --push
```

This publishes the project publicly. Alternatively, create an **empty** repository
on GitHub (without an initial README, license, or gitignore), then run the commands
below instead of `gh repo create`, replacing `YOUR_USERNAME`:

```sh
git remote add origin https://github.com/YOUR_USERNAME/SimplePomodoro.git
git push -u origin main
```

Check the **Actions** tab and confirm the Checks workflow succeeds.

## 6. Tag the release

Ensure `git status --short` is empty, then make and push an annotated tag:

```sh
git tag -a 0.1.0 -m "SimplePomodoro 0.1.0"
git show 0.1.0 --stat
git push origin 0.1.0
```

The tag identifies the exact source commit. Do not move it after publication;
publish a new version for subsequent fixes.

## 7. Create a draft GitHub Release and attach downloads

Rebuild from the clean tagged checkout, then create a draft with explicit assets:

```sh
python3 packaging/build.py
gh release create 0.1.0 \
  dist/simplepomodoro-0.1.0.tar.gz \
  dist/simplepomodoro-0.1.0-1-any.pkg.tar.zst \
  dist/SHA256SUMS \
  --verify-tag \
  --title "SimplePomodoro 0.1.0" \
  --notes-file CHANGELOG.md \
  --draft
gh release view 0.1.0 --web
```

Review the draft and download names in GitHub, then click **Publish release**.
GitHub also supplies source ZIP and tar.gz links automatically for the tagged
repository. The named source asset above has the layout expected by the local
PKGBUILD. A tag alone does not create an installable package or a GitHub Release.

To use the website instead of the release CLI: open **Releases → Draft a new
release**, select the existing `0.1.0` tag, paste the changelog, and attach the
three files above before publishing.

## Later releases and AUR

Update `VERSION` in `packaging/build.py`, `pkgver`/`pkgrel` in `packaging/PKGBUILD`,
the changelog, and README examples before committing and tagging the next version.
Increment `pkgrel` for packaging-only revisions of the same upstream version.

The current PKGBUILD remains a local snapshot template. Before AUR submission,
add the public project URL, change `source` to the versioned release archive URL,
replace the checksum placeholder with the published archive's SHA-256, and
generate `.SRCINFO` with `makepkg --printsrcinfo > .SRCINFO`. Test that recipe in
a separate directory using only its public downloads. Keep AUR metadata in its
own AUR Git repository; upload the recipe and required supporting files there.

References: [GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases),
[GitHub CLI release creation](https://cli.github.com/manual/gh_release_create),
and [AUR submission guidelines](https://wiki.archlinux.org/title/AUR_submission_guidelines).
