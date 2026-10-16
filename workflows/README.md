# workflows/

Workflow definitions for testing this processor on the platform. Registration
is API-only in workflow-service (POST the JSON to `/definitions`); runs are
started with `POST /runs`. pennsieve-mcp is just one caller of `POST /runs`, so
none of this needs MCP.

| File | Purpose |
|---|---|
| `plot-prep-test.json` | This stage alone: data-source → `processor-plot-prep` → `Pennsieve Dataset` target. The output file (an NWB, or the pass-through copy) comes back as a package in the dataset. |
| `plot-prep-quick-plot-test.json` | This stage in front of quick-plot: data-source → `processor-plot-prep` (Fargate) → `quick-plot-processor` (Lambda, from the `pennsieve-quick-plot-test` fork) → viewer asset. Run it on a CSV: the CSV passes through and quick-plot draws it, so a PNG at the end proves the folder hand-off and `standard → lambda` in one run with today's quick-plot. |

The production workflow (`processor-plot-prep` → `quick-plot-processor` → viewer asset)
lives in `pennsieve-quick-plot/workflows/plot-templates.json`, because that is
where the other nodes are pinned.

## Testing the stage on its own

```sh
export TOKEN="<session-token>"
export BASE="https://api2.pennsieve.net/compute/workflows"   # dev

# 0. Once: register the application (app-deploy-service) and tag a release.
#    app.yml declares computeTypes [standard, lambda]; the first test runs
#    on standard (the workflow node's default).

# 1. Register the test workflow
curl -X POST "$BASE/definitions" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d @workflows/plot-prep-test.json
# -> note the returned workflow UUID

# 2a. MEF2: a folder of .mef files, convert two channels
curl -X POST "$BASE/runs" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{
  "workflowInstanceConfiguration": {
    "workflowId": "<workflow-uuid>",
    "computeNodeId": "<compute-node-uuid>",
    "processorConfigs": [
      {"nodeId": "processor-plot-prep", "version": "v0.0.1", "executionTarget": "standard"}
    ]
  },
  "datasetId": "<dataset with write permission>",
  "dataSources": { "target-file": { "packageIds": ["<mef folder or mef file package id>"] } },
  "dataTargets": { "prep-output": { "params": { "UPLOAD_BUCKET": "<bucket>" } } },
  "processorParams": { "processor-plot-prep": { "CHANNELS": "EEG AD 01-Ref,EEG PT 01-Ref" } }
}'

# 2b. Pass-through: point target-file at a CSV or EDF package; omit processorParams.

# 3. Watch it
curl -H "Authorization: Bearer $TOKEN" "$BASE/runs/<run-uuid>"
curl -H "Authorization: Bearer $TOKEN" "$BASE/runs/<run-uuid>/logs"
```

What to check after each run:

- MEF2 run: exactly one `<folder>.nwb` package appears in the dataset; open it
  (pynwb or h5py) and confirm the channel names and sample count. Note the run
  duration from `GET /runs/{id}` — that is the number the Lambda/Fargate decision
  needs.
- Pass-through run: the input file comes back byte-identical.
- A folder with no `.mef` and nothing else staged: run status FAILED, log line
  `plot-prep failed: No input file was staged for this run.`

Known platform quirks (from pennsieve-quick-plot/workflows/README.md): the user
POSTing the run needs write permission on `datasetId`, and data-target
`defaultParams` are ignored at run time — pass `dataTargets.<nodeId>.params`
in the run body as above.

## Testing the stage in front of quick-plot (CSV, no quick-plot change)

Prerequisites: `skylerzhou/pennsieve-quick-plot-test` synced to upstream main and
tagged (`v0.0.5` at the time of writing; change the JSON if you tag again), registered
as an application with `computeTypes: ["lambda"]`; the dev compute node has the
`quick-plot-stack` EFS layer populated (it does if `plot-templates` runs there).

```sh
curl -X POST "$BASE/definitions" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d @workflows/plot-prep-quick-plot-test.json

curl -X POST "$BASE/runs" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{
  "workflowInstanceConfiguration": {
    "workflowId": "<workflow-uuid>",
    "computeNodeId": "<compute-node-uuid>",
    "processorConfigs": [
      {"nodeId": "processor-plot-prep",  "version": "v0.0.1", "executionTarget": "standard"},
      {"nodeId": "quick-plot-processor", "version": "v0.0.5", "executionTarget": "lambda"}
    ]
  },
  "datasetId": "<dataset with write permission>",
  "dataSources": { "target-file": { "packageIds": ["<csv package id>"] } },
  "dataTargets": { "figure-asset": { "params": { "ASSET_TYPE": "PNG", "ASSET_NAME": "plot-prep-test" } } },
  "processorParams": { "quick-plot-processor": { "template": "csv_column_distributions" } },
  "layers": ["quick-plot-stack"]
}'
```

Both `processorConfigs` entries are required: workflow-service fills defaults
only for the entries you send, it does not invent one for a node you leave out.

What to check: run status SUCCEEDED; a PNG viewer asset on the CSV package; in
the quick-plot logs, `Target file:` names the CSV under the plot-prep stage's
output folder (that is the hand-off working); and the run's total duration minus
quick-plot's ~5 s is what the Fargate stage costs on a pass-through.

A MEF2 recording cannot go through this workflow yet: quick-plot has no NWB
reader until `nwb_to_signal.py` lands in the fork. Use `plot-prep-test.json`
for MEF2 until then.

## Open question for the data-source

On Pennsieve a MEF2 recording is one `.mef` file per channel, all in one folder.
Two ways to point a run at it, and the gate handles both:

- **The folder's package id.** If the provisioner stages the folder's children
  flat into `INPUT_DIR`, `detect()` finds them there; one level down also works.
  `CHANNELS` picks the one or two the plot needs.
- **The channel files' package ids** (one or two `packageIds`). Then
  `INPUT_DIR` holds exactly those files and `CHANNELS` is unnecessary. The
  output is then named after the staging folder, so pass
  `processorParams.processor-plot-prep.OUTPUT_FILENAME` to name it after the recording.

Which of the two the provisioner supports for a collection id is still to be
checked (compute-node-aws-provisioner-v2).
