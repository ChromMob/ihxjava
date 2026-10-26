# ihxjava

[![test](https://github.com/ChromMob/ihxjava/actions/workflows/test.yml/badge.svg)](https://github.com/ChromMob/ihxjava/actions/workflows/test.yml)

Use JetBrains' official IntelliJ language server for Java and Kotlin, the one behind the
[Java and Kotlin by IntelliJ IDEA](https://marketplace.visualstudio.com/items?itemName=JetBrains.intellij-server)
VS Code extension, from [Helix](https://helix-editor.com) or [Neovim](https://neovim.io).

This repository contains no JetBrains code. `ihxjava install` downloads the official
extension from [Open VSX](https://open-vsx.org/extension/JetBrains/intellij-server) on
your machine and reads which server build it pins. It then downloads that build from
`download.jetbrains.com` and checks both SHA-256 checksums. The server runs unmodified.
`ihxjava` handles only the parts that the VS Code client would otherwise do.

## Requirements

- Linux or macOS (x64 or arm64), and Python 3.10+ with no other dependencies
- Helix 25.01+ or Neovim 0.11+
- An **IntelliJ IDEA Ultimate** or **All Products Pack** subscription, or a trial. The
  server does not work without one, just like the VS Code extension.
- About 1.2 GB of disk space for the server, plus space for per-project indexes

## Install

```sh
git clone https://github.com/ChromMob/ihxjava ~/.local/share/ihxjava-src
ln -s ~/.local/share/ihxjava-src/ihxjava ~/.local/bin/ihxjava   # any directory on your PATH

ihxjava install          # download the official server
ihxjava setup            # read and accept the JetBrains User Agreement, pick region and data sharing
ihxjava license status   # then, if not licensed yet, one of:
ihxjava license login    #   sign in with a JetBrains Account (opens a browser; uses a pasted code over SSH)
ihxjava license activate <activation code | key file | license server URL>
ihxjava license trial
```

Run `ihxjava install` again at any time to update to whatever server the latest
extension release pins.

Then set up your editor.

### Helix

Add this to `~/.config/helix/languages.toml`. `ihxjava helix-config` prints the same text.

```toml
[language-server.intellij]
command = "ihxjava"
args = ["lsp"]
timeout = 120

[language-server.intellij.config]
# buildTool = "gradle"

[[language]]
name = "java"
language-servers = ["intellij"]

[[language]]
name = "kotlin"
language-servers = ["intellij"]
```

`hx --health java` should now list `intellij`.

### Neovim

The repository is also a Neovim plugin. With [lazy.nvim](https://github.com/folke/lazy.nvim):

```lua
{
  'ChromMob/ihxjava',
  opts = {
    -- Any vim.lsp.config() field, for example:
    -- init_options = { buildTool = 'gradle' },
  },
}
```

If you don't use a plugin manager, put the clone on the runtime path:

```lua
vim.opt.runtimepath:append(vim.fn.expand('~/.local/share/ihxjava-src'))
require('ihxjava').setup()
```

The plugin configures and enables a `vim.lsp` client named `intellij` for Java and
Kotlin buffers. The project root is the nearest directory with `settings.gradle(.kts)`,
`MODULE.bazel` or `WORKSPACE`, else the git root, else the nearest `pom.xml` or
`build.gradle(.kts)`. Turn off other Java language servers such as `jdtls` and
`nvim-jdtls` in the same buffers. `:checkhealth vim.lsp` shows the client.

### First start

Open a Maven, Gradle or Bazel project. The first import and indexing can take a few
minutes, and the editor shows the progress. Later starts reuse the index.

## Configuration

**Server options** are sent as `initializationOptions`. In Helix they go in
`[language-server.intellij.config]`, and in Neovim in `init_options`:

| key | meaning |
| --- | --- |
| `buildTool` | `"gradle"`, `"maven"`, `"bazel"` or `"jps"` to skip detection, or `""` to disable project import |
| `defaultSdk` | path of the JDK used for symbol resolution |
| `projects` | projects to import, each `{ type = "maven", path = "file:///abs/path/pom.xml" }`, with the same fields as the extension's `intellij.projects` setting |
| `disableRocksDBWriteAheadLog` | `true`/`false` |
| `lazyIntentions` | default `true`: fixes are computed only when you pick one |

The server rejects all of its initialization options if any one of them has the wrong
type. If an option seems to have no effect, check the server log (see below).

**Launcher settings** go in `~/.config/ihxjava/config.json`, which `ihxjava setup` writes:

```json
{
  "eulaAccepted": "<hash>",
  "region": "europe",
  "dataSharing": "none",
  "jvmArgs": ["-Xmx4g"]
}
```

`dataSharing` is `none` (the default), `anonymous` or `full`. Change it with
`ihxjava setup --reconfigure`.

## Troubleshooting

- `ihxjava doctor` shows the installation, settings, readiness and license status.
- `ihxjava logs [project-dir]` prints the path of a project's server log. This is the
  most useful place to look.
- The editor's own log (`:log-open` in Helix, `:LspLog` in Neovim) shows anything the
  server prints to stderr, apart from its routine start-up lines. Set
  `IHXJAVA_VERBOSE=1` to see everything, including the exact launch command.
- If the setup is incomplete, `initialize` fails with a message that says which
  `ihxjava` command to run.

## How it works

The editor starts `ihxjava lsp`. When the editor sends `initialize`, the bridge:

1. checks that the server is installed, the EULA is accepted and a region is chosen
2. starts the official `bin/intellij-server --stdio --eula <hash> --system-path <dir>` in
   the project root, keeping one index directory per project under
   `~/.cache/ihxjava/system/`
3. fills in the initialization options the server expects
4. turns `jar:` and `jrt:` locations into files. Go to definition on a JDK or
   library class returns a URI that neither editor can open, so the bridge asks the
   server to decompile it, the same way the VS Code extension does, and writes the
   result read-only under `~/.cache/ihxjava/decompiled/`. Requests about that file go
   to the server under the original URI, so navigation and hover keep working inside it.

Everything else passes through unchanged.

## Not supported

These VS Code extension features need VS Code UI or APIs and are not available here:
the debugger and test explorer, the build tool chooser and conflict dialogs, and
IntelliJ-specific protocol extensions (`intellij/*`). Code lenses and inlay hints
depend on what your editor supports.

## Other commands

```
ihxjava clean         delete indexes and decompiled classes (quit editors first)
ihxjava uninstall     remove the server (--all also removes caches and settings)
```

## Development

```sh
python3 -m unittest discover tests
```

The tests run the bridge against `tests/fake_server.py`, so they need neither the
JetBrains server nor a license. The Neovim test runs when `nvim` is on `PATH`, or
when `NVIM_BIN` points at a Neovim binary. CI runs it on Neovim 0.11.0 and the
latest stable release.

## Legal

This is an independent project. It is not affiliated with or endorsed by JetBrains.
"IntelliJ IDEA" and "JetBrains" are trademarks of JetBrains s.r.o.

`ihxjava` is MIT-licensed (see [LICENSE](LICENSE)). The IntelliJ server it downloads is
JetBrains software, and the [JetBrains User Agreement](https://www.jetbrains.com/legal/docs/toolbox/user/)
governs its use. `ihxjava setup` shows you that agreement to accept before the server
runs, and you need a valid JetBrains subscription or trial. This project only
automates downloading the server from JetBrains on your machine and talking to it over
the standard Language Server Protocol.
