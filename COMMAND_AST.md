# Command AST

`requi` derives a command AST from the command catalog stored in `requi.db`. The catalog combines command names, compact usage strings, argument metadata, and aliases.

## Inspect commands

```sh
./requi.sh ast
./requi.sh ast add-term
./requi.sh ast --format json
./requi.sh ast read --format json
```

The default tree output is intended for humans. JSON is stable machine-readable output for tooling and UI layers. Pass a canonical command name or an alias to focus the output on one command.

## Generate parser code

```sh
./requi.sh ast read --format python
./requi.sh ast --format python > /tmp/requi_parser.py
```

Python output emits `argparse` parser-construction code derived from the AST. It does not generate command dispatch; dispatch remains project-specific in `tools/requi.py`.

## Update the source catalog

Edit `COMMANDS`, `COMMAND_ARGUMENTS`, or `COMMAND_ALIASES` in `tools/requi.py`, then rebuild the database before inspecting the AST:

```sh
./requi.sh build
./requi.sh ast
```

The generated site includes this page after `python3 tools/site.py`; `./requi.sh status` verifies whether `out/` is current.
