| case | input | expected unread | got | checked | exit | result |
|---|---|---|---|---|---|---|
| pip-r | `--cmd 'pip install -r req.txt'` | ['req.txt'] | ['req.txt'] | 0 | 3 | PASS |
| pip-r-joined | `--cmd 'pip install -rreq.txt'` | ['req.txt'] | ['req.txt'] | 0 | 3 | PASS |
| pip-requirement-eq | `--pip 'pip install requests --requirement=req.txt'` | ['req.txt'] | ['req.txt'] | 1 | 3 | PASS |
| pip-constraint | `--cmd 'pip install -c cons.txt requests'` | ['cons.txt'] | ['cons.txt'] | 1 | 3 | PASS |
| uv-editable | `--cmd 'uv pip install -e ./lib'` | ['./lib'] | ['./lib'] | 0 | 3 | PASS |
| conda-file-long | `--cmd 'conda install --file pk.txt'` | ['pk.txt'] | ['pk.txt'] | 1 | 3 | FAIL (checked 1 packages, expected 0) |
| conda-file-short #45 | `--cmd 'conda install -f pk.txt'` | ['pk.txt'] | [] | 0 | 0 | FAIL (fail-open: source never reported) |
| conda-channel-not-a-file #45 | `--cmd 'conda install -c conda-forge rdkit'` | [] | [] | 1 | 3 | PASS |
| positional-covers-same-file | `req.txt --cmd 'pip install -r req.txt'` | [] | [] | 1 | 3 | PASS |
| include-already-read #45 | `top.txt --cmd 'pip install -r child.txt'` | [] | [] | 1 | 3 | PASS |
| cd-points-elsewhere #45 | `req.txt --cmd 'cd sub && pip install -r req.txt'` | ['req.txt'] | ['req.txt'] | 1 | 3 | PASS |
| uv-directory-points-elsewhere #45 | `req.txt --cmd 'uv --directory sub add -r req.txt'` | ['req.txt'] | [] | 1 | 3 | FAIL (fail-open: source never reported) |
| conda-list-never-masked #45 | `specs.txt --cmd 'conda install --file specs.txt'` | ['specs.txt'] | [] | 1 | 3 | FAIL (fail-open: source never reported) |
| repeated-source-once #45 | `--cmd 'pip install -r req.txt -r req.txt'` | ['req.txt'] | ['req.txt'] | 0 | 3 | PASS |

10/14 pass, 4 fail (root: wt-ebd7a2b)
