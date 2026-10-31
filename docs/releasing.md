# Release SimplePomodoro

Run release checks from a clean `main` checkout after the feature batch has been
accepted and integrated. Version `0.1.1` is the current release prepared by this
workflow. Do not move a published tag; use a new version for later changes.

## Validate and build

On Arch Linux, install the application and package build prerequisites:

```sh
sudo pacman -S --needed python python-gobject python-cairo gtk4 libadwaita gstreamer gst-plugins-base gst-plugins-good base-devel desktop-file-utils
env PYTHONPATH=src /usr/bin/python -m unittest discover -s tests -v
env PYTHONPATH=src /usr/bin/python tests/gtk_smoke.py
python3 packaging/build.py
```

The GTK smoke check needs a graphical session; exit 77 means no display was
available. The source builder runs the unit tests and desktop-entry validation
through `makepkg`. It writes the source archive, Arch package, and checksums to
ignored `dist/`. Verify them with:

```sh
(cd dist && sha256sum --check SHA256SUMS)
```

For a source-only build, use `python3 packaging/build.py --source-only`. That
rewrites `dist/SHA256SUMS` to cover only the source archive; rebuild normally
before attaching both release downloads.

## Commit and tag

Review the complete release diff and ensure the checkout is clean. Create an
annotated version tag on the verified release commit:

```sh
git status --short
git log -1 --oneline
git tag -a 0.1.1 -m "SimplePomodoro 0.1.1"
git show 0.1.1 --stat
```

Push `main` and the tag only when requested by the project owner:

```sh
git push origin main
git push origin 0.1.1
```

## Publish downloads

After pushing the tag, create a draft GitHub Release with the generated assets:

```sh
gh release create 0.1.1 \
  dist/simplepomodoro-0.1.1.tar.gz \
  dist/simplepomodoro-0.1.1-1-any.pkg.tar.zst \
  dist/SHA256SUMS \
  --verify-tag \
  --title "SimplePomodoro 0.1.1" \
  --notes-file CHANGELOG.md \
  --draft
```

Review the draft and download names in GitHub before publishing it. The release
archive is also the source expected by the local `packaging/PKGBUILD`; for AUR
submission, update its public source URL and checksum and generate `.SRCINFO`.
