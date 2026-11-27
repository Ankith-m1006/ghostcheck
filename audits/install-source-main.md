| case | input | expected unread | got | result |
|---|---|---|---|---|
| pip-r | `--cmd 'pip install -r req.txt'` | ['req.txt'] | ['req.txt'] | PASS |
| pip-r-joined | `--cmd 'pip install -rreq.txt'` | ['req.txt'] | ['req.txt'] | PASS |
| pip-requirement-eq | `--pip 'pip install requests --requirement=req.txt'` | ['req.txt'] | ['req.txt'] | PASS |
| pip-constraint | `--cmd 'pip install -c cons.txt requests'` | ['cons.txt'] | ['cons.txt'] | PASS |
| uv-editable | `--cmd 'uv pip install -e ./lib'` | ['./lib'] | ['./lib'] | PASS |
| conda-file-long | `--cmd 'conda install --file pk.txt'` | ['pk.txt'] | ['pk.txt'] | PASS |
| conda-file-short #45 | `--cmd 'conda install -f pk.txt'` | ['pk.txt'] | ['pk.txt'] | PASS |
| conda-channel-not-a-file #45 | `--cmd 'conda install -c conda-forge rdkit'` | [] | [] | PASS |
| positional-covers-same-file | `req.txt --cmd 'pip install -r req.txt'` | [] | [] | PASS |
| include-already-read #45 | `top.txt --cmd 'pip install -r child.txt'` | [] | [] | PASS |
| cd-points-elsewhere #45 | `req.txt --cmd 'cd sub && pip install -r req.txt'` | ['req.txt'] | ['req.txt'] | PASS |
| uv-directory-points-elsewhere #45 | `req.txt --cmd 'uv --directory sub add -r req.txt'` | ['req.txt'] | ['req.txt'] | PASS |
| conda-list-never-masked #45 | `specs.txt --cmd 'conda install --file specs.txt'` | ['specs.txt'] | ['specs.txt'] | PASS |
| repeated-source-once #45 | `--cmd 'pip install -r req.txt -r req.txt'` | ['req.txt'] | ['req.txt'] | PASS |

14/14 pass, 0 fail (root: ghostcheck)
