# Option-value audit: pnpm

40 probes, 40 pass, 0 fail.

| Command | Expected | Got | Result |
| --- | --- | --- | --- |
| `pnpm add -C sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm -C sentinelvalue add left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --dir sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --dir=sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm --dir sentinelvalue add left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --loglevel sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --loglevel=sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm --loglevel sentinelvalue add left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --registry sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --registry=sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm --registry sentinelvalue add left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --save-catalog-name sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --save-catalog-name=sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm --save-catalog-name sentinelvalue add left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --store-dir sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --store-dir=sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm --store-dir sentinelvalue add left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --virtual-store-dir sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --virtual-store-dir=sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm --virtual-store-dir sentinelvalue add left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --changed-files-ignore-pattern sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --changed-files-ignore-pattern=sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm --changed-files-ignore-pattern sentinelvalue add left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add -F sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm -F sentinelvalue add left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --filter sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --filter=sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm --filter sentinelvalue add left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --filter-prod sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --filter-prod=sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm --filter-prod sentinelvalue add left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --test-pattern sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --test-pattern=sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm --test-pattern sentinelvalue add left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --allow-build sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --allow-build=sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm --allow-build sentinelvalue add left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --global-dir sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm add --global-dir=sentinelvalue left-pad` | `left-pad` | `left-pad` | PASS |
| `pnpm --global-dir sentinelvalue add left-pad` | `left-pad` | `left-pad` | PASS |
