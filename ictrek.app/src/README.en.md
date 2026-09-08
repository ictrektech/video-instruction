# Video Instruction

Video scene detection (scene-detect) and video structuring (structure) dual-service app for other VOS platform apps.

## Capabilities

- **scene-detect (default host port 48910)**: ffprobe metadata → PySceneDetect scene boundaries, returns `scenes[]`
- **structure (default host port 48911)**: per-scene frame grids → staging → tar artifact pull delivery; optional VLM scene descriptions (describe)
- **Integration guide page**: navigation "Video Instruction → Integration Guide", a same-origin iframe with the full HTTP API reference

## Integration Notes

1. **Base URLs** (direct, recommended): `http://<host>:48910` / `http://<host>:48911`
2. **Gateway URLs**: `http://${VOS_HOST_GW_IP}:${VOS_API_GW_PORT_INTERNAL}/api/com.ictrek.video-structure/{scene|structure}`
3. **Always pass `video_path` as an `http(s)://` URL** reachable from the service containers (use `172.17.0.1` on the same host, never `localhost`). Local-path mode requires identical mounts across containers and is not recommended.
4. Async jobs: submit → poll `GET .../jobs/{id}` until `succeeded` → download artifact → `DELETE` to release staging.
5. Business errors return HTTP 200 — **judge success by the response body `code` only**.

See the in-app "Integration Guide" page for the full API contract.

## Deployment Topology

One app with two containers (scene-detection + structure) sharing the `data/` volume (jobs/queue SQLite) and `staging/` volume (artifacts). **Both containers must be scheduled on the same host.**

## Configuration

Collected at install time via `configs.yml`, keeping only the essentials: the two host ports (default 48910/48911) and the default LLM config for describe (base URL / key / model name). Everything else uses built-in server defaults.
