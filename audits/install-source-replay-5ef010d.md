| case | input | expected unread | got | result |
|---|---|---|---|---|
| pip-r | `--cmd 'pip install -r req.txt'` | ['req.txt'] | ['req.txt'] | PASS |
| pip-r-joined | `--cmd 'pip install -rreq.txt'` | ['req.txt'] | ['req.txt'] | PASS |
| pip-requirement-eq | `--pip 'pip install requests --requirement=req.txt'` | ['req.txt'] | ['req.txt'] | PASS |
| pip-constraint | `--cmd 'pip install -c cons.txt requests'` | ['cons.txt'] | ['cons.txt'] | PASS |
| uv-editable | `--cmd 'uv pip install -e ./lib'` | ['./lib'] | ['./lib'] | FAIL (editable path told to run ghostcheck <file>) |
| conda-file-long | `--cmd 'conda install --file pk.txt'` | ['pk.txt'] | [] | FAIL (fail-open: source never reported) |
| conda-file-short #45 | `--cmd 'conda install -f pk.txt'` | ['pk.txt'] | [] | FAIL (fail-open: source never reported) |
| conda-channel-not-a-file #45 | `--cmd 'conda install -c conda-forge rdkit'` | [] | ['conda-forge'] | FAIL (false alarm or duplicate) |
| positional-covers-same-file | `req.txt --cmd 'pip install -r req.txt'` | [] | [] | PASS |
| include-already-read #45 | `top.txt --cmd 'pip install -r child.txt'` | [] | ['child.txt'] | FAIL (false alarm or duplicate) |
| cd-points-elsewhere #45 | `req.txt --cmd 'cd sub && pip install -r req.txt'` | ['req.txt'] | [] | FAIL (fail-open: source never reported) |
| uv-directory-points-elsewhere #45 | `req.txt --cmd 'uv --directory sub add -r req.txt'` | ['req.txt'] | [] | FAIL (fail-open: source never reported) |
| conda-list-never-masked #45 | `specs.txt --cmd 'conda install --file specs.txt'` | ['specs.txt'] | [] | FAIL (fail-open: source never reported) |
| repeated-source-once #45 | `--cmd 'pip install -r req.txt -r req.txt'` | ['req.txt'] | ['req.txt', 'req.txt'] | FAIL (false alarm or duplicate) |

5/14 pass, 9 fail (root: wt-5ef010d)
