# Incident Report

| Field | Value |
|---|---|
| Incident ID | `e7a3f1b2-8c4d-4a5e-9b6f-2c1d3e4f5a6b` |
| Unit | `postgresql/0` |
| Workload status | `blocked` |
| First seen | `2026-07-14T09:55:00+00:00` |
| Report generated | `2026-07-14T10:05:00+00:00` |

## Log files

- `/var/log/postgresql/postgresql-16-main.log` (high) — _Main PostgreSQL log_ ✓

```
2026-07-14 09:55:01 UTC [12345] LOG:  received SIGHUP, reloading configuration files
2026-07-14 09:55:01 UTC [12345] LOG:  parameter "max_connections" cannot be changed without restart
2026-07-14 09:56:00 UTC [12346] WARNING:  database "app" has no active replicas
2026-07-14 09:57:30 UTC [12347] ERROR:  out of disk space on primary
```

- `/var/log/postgresql/postgresql-16-main.log.1` (medium) — _Rotated PostgreSQL log (recent)_ ✓

```
2026-07-14 09:50:00 UTC [12340] LOG:  checkpoint starting: time
2026-07-14 09:52:00 UTC [12341] LOG:  checkpoint complete: wrote 42 buffers
```

- `/var/log/postgresql/pg_stat_statements.log` (low) — _Query statistics log_ ✗ (not_found)

## Processes

- **pgbouncer**: 1 running (expected 1-1) ✓
- **postgres**: 0 running (expected 1-4) ✗

## Systemd units

- `postgresql@16-main.service` → inactive ✗
- `postgresql-exporter.service` → active ✓

## Network ports

- `5432/tcp` → not_listening ✗
- `6432/tcp` → listening ✓

## Environment variables

- `PGDATA` = `/var/lib/postgresql/16/main` ✓
- `PGPORT` = `5432` ✓
- `POSTGRES_PASSWORD` — unset ✗

## Health commands

- `$ systemctl is-active postgresql@16-main.service` → exit 0 ✓
  ```
  active
  ```
- `$ pg_isready -h localhost -p 5432` → exit 1 ✗
  ```
  /tmp:5432 - no response
  ```

## Charm config

- `max_connections`: `100`
- `port`: `5432`

## Disk usage

```
Filesystem     Size  Used Avail Use% Mounted on
/dev/sda1       20G   19G  1.0G  95% /
```

## Memory

```
              total  used  free  shared  buff/cache  available
Mem:           7.7G  6.1G  0.3G   0.1G       1.3G       1.2G
Swap:          2.0G  0.5G  1.5G
```

## Recent unit logs

_Showing only lines matching `error` or `warning` (case-insensitive), with a context window around the last match._

_Logs are in chronological order._

```
2026-07-14 09:55:01 WARNING unit.postgresql/0.juju-log Cannot start: no replicas
2026-07-14 09:57:00 ERROR unit.postgresql/0.juju-log Hook start failed: disk full
2026-07-14 09:58:00 INFO juju.worker Running cleanup hooks
```
