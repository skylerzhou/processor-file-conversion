# processor-plot-prep

The stage that runs in front of [pennsieve-quick-plot](https://github.com/Pennsieve/pennsieve-quick-plot)
in the `plot-templates` workflow. It makes sure quick-plot gets a file it can read:

```
target-file ──▶ [ processor-plot-prep ] ──▶ [ quick-plot ] ──▶ figure-asset
                 MEF2 folder  → one NWB file
                 anything else → copied through unchanged
```

It converts only what it knows how to convert. Everything else passes through
untouched, and quick-plot says "no reader for `.xyz`" the way it already does.
There is no list of quick-plot's formats here to keep in sync.

**It is never a no-op.** Every run ends with data in `OUTPUT_DIR` or with exit
code 1 and a one-line reason. `OUTPUT_DIR` is the next stage's `INPUT_DIR`; an
earlier two-stage plot workflow died on a stage that did nothing and left the
next one an empty folder.

## Converters

| name | input | output | how |
|---|---|---|---|
| `mef2_to_nwb` | a folder of MEF 2.0 files, one `.mef` per channel | one `<folder>.nwb` | `mefstreamer.jar` (built from [Pennsieve/mef2streamer](https://github.com/Pennsieve/mef2streamer)) streams the samples; Python writes the NWB in chunks |

MEF 2.0 only. The jar reads the header and exits 1 on anything else. MEF3
(`.mefd` folder trees) is a different format and is not handled.

The code under `processor/converters/mef2/` is moved unchanged from
[processor-mef-timeseries](https://github.com/Pennsieve/processor-mef-timeseries),
tests included. This repo supersedes it: a MEF2 folder in, one NWB out, plus
the pass-through for everything else.

### Adding a converter

One module in `processor/converters/` with four things, plus one line in the
`CONVERTERS` list in `processor/converters/__init__.py`:

```python
NAME = "xyz_to_nwb"
INPUT_EXTENSIONS = (".xyz",)        # advisory, goes into schema/converters.json
OUTPUT_EXTENSION = ".nwb"           # something quick-plot already reads

def detect(input_dir: Path) -> Path | None:
    """The folder or file this converter would convert, or None."""

def convert(source: Path, output_dir: Path, config) -> Path:
    """Write exactly one file into output_dir and return it. Raise on failure.
    Keep scratch files out of output_dir, or delete them in a finally."""
```

Converters are asked in list order; the first `detect()` that answers wins.
Write to a format quick-plot already reads, so a new input format costs
quick-plot nothing. Then `make schemas` and vendor `schema/converters.json`
into pennsieve-mcp (below).

## Layout

```
processor/
  main.py             the gate: detect → convert, else pass through; exit codes
  config.py           env vars → Config
  handler.py          Lambda entry: event payload → env vars → main()
  schema.py           emits schema/converters.json (`make schemas`)
  converters/
    __init__.py       CONVERTERS registry + find_converter()
    mef2_to_nwb.py    the MEF2 converter (detect + convert)
    mef2/             mef_streamer.py, multi_channel_reader.py, nwb_writer.py
schema/converters.json   generated; pennsieve-mcp vendors a copy
tests/                   fake_streamer.py stands in for the jar; no Java needed
app.yml                  manifest app-deploy-service reads: runtime, parameters, input/output media types
entrypoint.sh            Lambda vs ECS detection (same as quick-plot)
Dockerfile               JRE + mef2streamer build + python 3.12 + pynwb
```

## Running

```sh
make test      # 42 tests, no Docker or Java needed
make run       # build the image (clones + builds mef2streamer) and run on data/input
make schemas   # regenerate schema/converters.json
```

Put a MEF2 session folder (or any file) under `data/input/`; the result lands in
`data/output/`. `CHANNELS="A1,B2" make run` converts a subset.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `INPUT_DIR` | `/data/input` | What the data-source staged |
| `OUTPUT_DIR` | `/data/output` | What the next stage will read |
| `CHANNELS` | all | Comma-separated channel names to convert (`MEF_CHANNELS` also accepted). The plot needs one or two channels; converting only those makes a 100-channel recording ~50× faster. A name that matches nothing fails the run. |
| `OUTPUT_FILENAME` | `<source folder>.nwb` | Force the converted file's name |
| `JAVA_CMD` | `/opt/java/openjdk/bin/java -jar /processor/mefstreamer.jar` | Command prefix for the streamer; the source folder is appended |

On Lambda the same values arrive in the event payload (`inputDir`, `outputDir`,
`channels`, `output_filename`) and `handler.py` copies them into the environment.

## Lambda + Fargate

The image runs either way; `entrypoint.sh` picks the mode from
`AWS_LAMBDA_RUNTIME_API`. Register the application with
`computeTypes: ["lambda", "standard"]`. pennsieve-mcp then sets
`executionTarget` per run from `schema/converters.json`: `lambda` when the
package will pass through (a copy, a few seconds), `standard` (Fargate) when a
converter will run (a big MEF2 recording needs more than Lambda's 15 minutes).

## Build arguments

| Argument | Default | Description |
|---|---|---|
| `MEF2STREAMER_REPO` | `skylerzhou/mef2streamer-fork` | GitHub `<owner>/<name>` to build the jar from. The default is the fork while this processor is under test (app-deploy-service passes no build args, so the default is what the platform builds). Switch it to `Pennsieve/mef2streamer` when integrating. |
| `MEF2STREAMER_REF` | `main` | Branch, tag or SHA in that repo. Pin it before a release: `MEF2STREAMER_REF=<sha> docker-compose build`. |

## Workflow definition

The node sits between the data-source and quick-plot. Its id is the repo name,
`processor-plot-prep`, so the workflow JSON, the `processorConfigs` /
`processorParams` keys and the logs all say the same thing:

```json
{ "id": "processor-plot-prep", "type": "processor",
  "sourceUrl": "https://github.com/skylerzhou/processor-plot-prep", "tag": "v0.0.1",
  "computeType": "lambda", "dependsOn": ["target-file"] },
{ "id": "quick-plot-processor", "type": "processor", "...": "...", "dependsOn": ["processor-plot-prep"] }
```

workflow-service only fills defaults for the `processorConfigs` entries a run
sends, so `plot_file` in pennsieve-mcp must add
`{ "nodeId": "processor-plot-prep", "version": "...", "executionTarget": "lambda" | "standard" }`
to every run.
