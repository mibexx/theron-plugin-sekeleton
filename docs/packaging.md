# Packaging, signing & installing

## The `.theronplugin` format

A ZIP archive with the plugin folder's content at its root (a single top-level folder is accepted, too):

```
my-plugin-0.1.0.theronplugin
├── plugin.toml
├── my_plugin/…
├── lib/…              (optional)
├── i18n/…             (optional)
└── SIGNATURE.json     (when signed)
```

Theron refuses packages with absolute paths, `..`, symbolic links or more than 200 MB unpacked. `.zip` files and plain
folders are accepted as well (`theron plugin install ./my-plugin`).

## What goes in: `.theronignore`

Every file of the folder goes into the package except caches (`__pycache__`, `*.pyc`), VCS and editor folders
(`.git`, `.venv`, `.idea` …), `.DS_Store` – and what `.theronignore` lists. One glob per line, `#` for comments:

```
tests/          a folder, at any depth
devkit/
scripts/
*.md            files by pattern (matched against the path and the file name)
docs/guide.pdf  a single file
```

`.theronignore` itself is never packed. The signature covers exactly the packed files.

## Packing

```bash
theron plugin pack FOLDER [--out FILE_OR_FOLDER] [--sign KEY]   # with Theron installed
python scripts/pack.py [--out FOLDER] [--sign KEY]               # this skeleton – no Theron needed
python scripts/pack.py --check                                   # list what would go in
```

Both write `<id>-<version>.theronplugin` in the same format, with the same files.

## Signing

Signing proves who built a plugin and that nothing changed since. Theron shows the result before installing:

| Status | Meaning | Install |
|---|---|---|
| ✔ verified | valid signature by a trusted key | allowed |
| signed, unknown key | valid signature, key not trusted – the fingerprint is shown | after confirming |
| not signed | no `SIGNATURE.json` | after confirming |
| ✖ invalid | a file was changed, added or removed after signing, or the signature doesn't match | refused |

Keys are Ed25519 key pairs:

```bash
theron plugin keygen ~/.theron-signing.key        # or: python scripts/pack.py --keygen ~/.theron-signing.key
```

This writes the private key (`.key`, readable only by you – keep it secret and out of the repository) and the public
key (`.pub`). Sign while packing with `--sign ~/.theron-signing.key`. Publish the public key (README, website) so users
can trust it:

```bash
theron plugin trust "<public key>" --name "Ada Lovelace"
```

Trusted keys are kept per Theron installation. Plugins signed with mibexx's key (Theron's maker) count as verified
everywhere.

### `SIGNATURE.json`

```json
{
 "format": 1,
 "key": "<Ed25519 public key, base64>",
 "files": {"plugin.toml": "<sha256 hex>", "my_plugin/__init__.py": "<sha256 hex>", "…": "…"},
 "signature": "<base64>"
}
```

The signature is made over the canonical JSON of `files` (keys sorted, separators `,` and `:` without spaces). Theron
recomputes the SHA-256 of every packed file and checks that the set of files matches exactly.

## Installing

| Where | How |
|---|---|
| Desktop app | Settings → Plugins → “Upload plugin …” → check name, signature and permissions → confirm |
| Console (also on a slave) | `theron plugin install FILE` – asks for unverified plugins; `--yes` for scripts |
| Headless Docker worker | files in `/data/plugin-packages/` (or `$THERON_PLUGIN_PACKAGES`) are installed/updated at every container start; or `docker exec <container> theron plugin install /data/FILE --yes` |
| Kubernetes | mount the package into `/data/plugin-packages/` (ConfigMap, init container or the data volume) |

Installing a plugin whose id is already installed **updates** it: the old folder is replaced (rolled back if copying
fails), settings, storage and `plugin-data/` stay. A newly installed plugin is switched on. Everything takes effect after
a restart of Theron.

## Managing

```bash
theron plugin list                       # installed plugins: version, on/off/error, signature
theron plugin info ID_OR_FILE            # manifest, permissions, settings, signature
theron plugin enable ID | disable ID
theron plugin remove ID [--purge]        # --purge also deletes settings, storage and plugin-data/
```

## Releasing a plugin

1. Raise `version` in `plugin.toml` (and `min_theron` if you use an API addition of a newer Theron).
2. Run the tests: `python -m pytest`.
3. Pack signed: `python scripts/pack.py --sign ~/.theron-signing.key`.
4. Publish the `.theronplugin` (e.g. as a GitHub release asset) together with your public key.
