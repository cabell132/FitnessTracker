# Fitness Tracker

## Credentials and running commands

Install Python dependencies with `uv sync --locked --dev` and command tooling
with `npm ci`. Run commands from the repository root.

[.env.schema](.env.schema) defines configuration, defaults, and sensitivity.
Varlock loads existing `.env` values automatically. For a new checkout, create
a gitignored `.env.local` and supply the credentials you need. Shell environment
values override local files. Never commit credential values to the schema.

```bash
npm run env:check
npm run cli -- --help
```

Application commands require `EMAIL`, `TRUECOACH_PASSWORD`, `HEVY_API_KEY`,
`OPENAI_API_KEY`, and `DROPBOX_ACCESS_TOKEN`. Database-only and offline commands
do not require these credentials, so the schema leaves them optional and the
application validates them when needed. `DATABASE_URL` defaults to local SQLite;
set it explicitly for PostgreSQL. It is sensitive because it can contain a password.

Use these command wrappers for local credentials:

| Task | Command |
| --- | --- |
| Automatic sync, which writes to connected services | `npm start` |
| CLI command | `npm run cli -- <arguments>` |
| Database migration | `npm run db -- upgrade head` |
| Python script | `npm run env:run -- uv run python <script.py>` |
| PostgreSQL provisioning | `npm run env:run -- docker compose --env-file /dev/null -f docker-compose.postgres.yml up -d` |

Python reads the injected process environment and no longer loads `.env` itself.
Wrap older `uv run` examples with `npm run env:run --` when using local credentials.
Tests still run with `uv run poe test` and do not need real credentials.
CI can inject its secrets directly into the process environment.

Varlock loading does not encrypt existing files. To encrypt local secrets on
your device, run `npx --no-install varlock encrypt --file .env` yourself, or use
`.env.local` as the file argument if that is where you store them. Keep the
resulting file gitignored. See the [Varlock encryption guide](https://varlock.dev/guides/local-encryption/).

The rotating Hevy access and refresh tokens remain managed by the application's
gitignored `.hevy-web-auth.json` store. `HEVY_WEB_API_KEY` is a legacy fallback;
`HEVY_WEB_AUTH_PATH` can override the store location.

The command wrappers follow [Varlock's process injection approach](https://varlock.dev/integrations/other-languages/).

## VeSync scale data

The read-only VeSync client lives in `fitness_tracker.apis.vesync`. Supply
`VESYNC_EMAIL` and `VESYNC_PASSWORD` through Varlock before using it. The client
supports the V1 endpoint for older Wi-Fi scales and the V2 endpoint for Bluetooth
and Wi-Fi/Bluetooth scales, including EFS-A591S.
The automatic sync and the real Hevy result-apply command import primary-profile
scale readings. Other VeSync profiles are excluded. To reconcile all scale
history on its own, run:

```bash
npm run env:run -- uv run --locked python -m scripts.sync_vesync_scale
```

The command reports counts only; it does not print measurements.

```python
from fitness_tracker.apis.vesync import VeSyncClient

client = VeSyncClient.from_env()
scale = client.find_scale()
page = client.weight.get_weight_data_v2(scale)  # EFS-A591S, first 100 readings
# page = client.weight.get_weight_data(scale)  # Older Wi-Fi scale
for measurement in page.measurements:
    print(measurement.timestamp, measurement.weight_kg)
```

Run scripts that use the client with `npm run env:run -- uv run python <script.py>`.
For V2, request later pages with `get_weight_data_v2(scale, page=2)`.
