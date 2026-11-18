import json

import pytest

from ghostcheck.parsers import (NPM, PYPI, extract_from_answer, js_imports, normalize_pypi, parse_npm_command,
                                parse_package_json, parse_pip_command, parse_requirements, python_imports)
from ghostcheck.stdlib import is_node_builtin, is_python_stdlib


def names(deps):
    return [d.name for d in deps]


def test_requirements_txt_handles_specifiers_extras_markers_and_skips_options():
    text = """
# comment
requests[socks]>=2.31  # inline comment
Django==5.0 ; python_version >= "3.10"
-r other.txt
-e .
--index-url https://example.org/simple
numpy
./local/pkg
https://example.org/x-1.0.tar.gz
mypkg @ https://example.org/mypkg-1.0.whl
pandas~=2.2
"""
    deps = parse_requirements(text)
    assert names(deps) == ["requests", "Django", "numpy", "mypkg", "pandas"]
    assert all(d.ecosystem == PYPI for d in deps)
    assert deps[0].source == "requirements.txt:3"


def test_package_json_reads_all_sections_and_skips_local_links():
    pkg = {
        "dependencies": {"express": "^4.19.0", "@aws-sdk/client-s3": "3.500.0", "local": "file:../local"},
        "devDependencies": {"jest": "29", "ws-lib": "workspace:*"},
        "peerDependencies": {"react": ">=18"},
        "optionalDependencies": {"alias": "npm:real-pkg@^1.0.0"},
    }
    deps = parse_package_json(json.dumps(pkg))
    assert names(deps) == ["express", "@aws-sdk/client-s3", "jest", "real-pkg", "react"]
    assert all(d.ecosystem == NPM for d in deps)


def test_package_json_invalid_raises():
    with pytest.raises(ValueError):
        parse_package_json("{not json")


@pytest.mark.parametrize("cmd,expected", [
    ("pip install requests flask", ["requests", "flask"]),
    ("pip3 install -U 'fastapi[all]>=0.110' uvicorn==0.29", ["fastapi", "uvicorn"]),
    ("python -m pip install --upgrade pip", ["pip"]),
    ("pip install -r requirements.txt pdfplumber", ["pdfplumber"]),
    ("$ pip install opencv-python && python app.py", ["opencv-python"]),
    ("pip install --index-url https://x.org/simple private-pkg", ["private-pkg"]),
    ("conda install -c conda-forge rdkit", ["rdkit"]),
    ("pip install git+https://github.com/a/b.git", []),
    ("pip install requests requests", ["requests"]),
    ("uv add httpx 'pydantic>=2'", ["httpx", "pydantic"]),
    ("pipx install ruff", ["ruff"]),
    ("pip install flask && pip install requests; pip3 install rich", ["flask", "requests", "rich"]),
    # Qodo review on PR #1: quoted ';' is not a separator, installer options are not packages,
    # uv global options may come before 'add'
    ("""pip install 'requests;python_version < "3.11"' flask""", ["requests", "flask"]),
    ("uv add --group test pytest", ["pytest"]),
    ("pipx install --python python3.12 black", ["black"]),
    ("uv --project backend add requests", ["requests"]),
    ("uv --directory=api --offline add httpx", ["httpx"]),
    # Qodo re-review: a prose apostrophe before the command must not hide chained installs
    ("I'll install them: pip install flask && pip install requestz", ["flask", "requestz"]),
    ("Don't forget; pip install 'requests;python_version < \"3.11\"' rich && pip install httpx", ["requests", "rich", "httpx"]),
    ("uv pip install numpy", ["numpy"]),
])
def test_pip_commands(cmd, expected):
    assert names(parse_pip_command(cmd)) == expected


@pytest.mark.parametrize("cmd,expected", [
    ("npm install express jsonwebtoken", ["express", "jsonwebtoken"]),
    ("npm i -D jest @types/node@20", ["jest", "@types/node"]),
    ("yarn add lodash@^4.17.21", ["lodash"]),
    ("pnpm add @aws-sdk/client-s3 --save", ["@aws-sdk/client-s3"]),
    ("npm install ./local-folder user/repo", []),
    ("npm install --registry https://r.example.org pkg-a", ["pkg-a"]),
    # #21: a node: built-in must reach the rules (which say "nothing to install"), not vanish silently
    ("npm install node:fs lodash", ["node:fs", "lodash"]),
    # an alias installs the package after npm: (Qodo on #22), so that is the one to check
    ("npm install fs@npm:memfs util@npm:util@0.12.5", ["memfs", "util"]),
])
def test_npm_commands(cmd, expected):
    assert names(parse_npm_command(cmd)) == expected


def test_python_imports_drop_stdlib_relative_and_future():
    code = """
from __future__ import annotations
import os, sys
import json as j
import numpy as np, pandas
from sklearn.model_selection import train_test_split
from . import local
from .utils import helper
import xml.etree.ElementTree as ET
    import requests  # indented import inside a function
"""
    assert python_imports(code) == ["numpy", "pandas", "requests", "sklearn"]


def test_stdlib_lists():
    assert is_python_stdlib("asyncio") and is_python_stdlib("os.path") and is_python_stdlib("distutils")
    assert not is_python_stdlib("requests")
    assert is_node_builtin("fs") and is_node_builtin("fs/promises") and is_node_builtin("node:test")
    assert not is_node_builtin("test") and not is_node_builtin("express")


def test_js_imports_cover_require_import_dynamic_subpath_scoped_and_builtins():
    code = """
const express = require('express');
const fs = require("fs");
const { readFile } = require('node:fs/promises');
import pdf from "pdf-parse/lib/pdf-parse.js";
import { S3Client } from '@aws-sdk/client-s3';
import './styles.css';
import 'dotenv/config';
import helper from './helper.js';
import comp from '@/components/x';
const m = await import('chalk');
export * from 'zod';
"""
    assert js_imports(code) == ["express", "pdf-parse", "@aws-sdk/client-s3", "dotenv", "chalk", "zod"]


def test_answer_extraction_reads_code_blocks_and_install_lines_but_not_prose():
    answer = """Here is how to do it. First import the data and then use pip install with care.

```python
import pdfplumber
import cv2
from gstpro_validator import check
import os
```

Install the packages:

```bash
pip install pdfplumber opencv-python
```

Or run `pip install gstpro-validator` too.
"""
    ex = extract_from_answer(answer, "python")
    assert ex.python_imports == ["pdfplumber", "cv2", "gstpro_validator"]
    assert ex.pip_installs == ["pdfplumber", "opencv-python", "gstpro-validator"]
    assert ex.npm_installs == []


def test_answer_extraction_plain_pipx_line():
    # Qodo review on PR #1: an unfenced, non-inline pipx line must still be checked
    ex = extract_from_answer("Install the tool first:\npipx install ruff\nthen run it.", "python")
    assert ex.pip_installs == ["ruff"]


def test_answer_extraction_javascript():
    answer = "```javascript\nconst qr = require('upi-qr-magic');\nconst x = require('path');\n```\n\nnpm install upi-qr-magic qrcode\n"
    ex = extract_from_answer(answer, "javascript")
    assert ex.js_imports == ["upi-qr-magic"]
    assert ex.npm_installs == ["upi-qr-magic", "qrcode"]


def test_normalize_pypi():
    assert normalize_pypi("Python_Dateutil") == "python-dateutil"
    assert normalize_pypi("zope.interface") == "zope-interface"


# Issue #13: package runners download and run a package in one step.
@pytest.mark.parametrize("cmd,want", [
    ("npx some-ghost-cli --port 3000", ["some-ghost-cli"]),
    ("npx -y @scope/ghost-mcp@1.2.0 serve", ["@scope/ghost-mcp"]),
    ("npx --yes ghost-tool", ["ghost-tool"]),
    ("npx --package ghost-pkg ghost-bin", ["ghost-pkg"]),
    ("npx -p ghost-pkg ghost-bin", ["ghost-pkg"]),
    ("npm exec -- ghost-tool --flag", ["ghost-tool"]),
    ("npm exec ghost-tool", ["ghost-tool"]),
    ("bunx ghost-tool init", ["ghost-tool"]),
    ("pnpm dlx create-ghost-app my-app", ["create-ghost-app"]),
    ("yarn dlx ghost-tool@latest run", ["ghost-tool"]),
])
def test_npm_package_runners(cmd, want):
    assert [d.name for d in parse_npm_command(cmd)] == want


@pytest.mark.parametrize("cmd,want", [
    ("uvx ghost-cli --help", ["ghost-cli"]),
    ("uvx --from ghost-pkg ghost-cmd", ["ghost-pkg"]),
    ("uvx ghost-cli==1.2 run", ["ghost-cli"]),
    ("pipx run ghost-cli --version", ["ghost-cli"]),
    ("pipx run --spec ghost-pkg ghost-cmd", ["ghost-pkg"]),
])
def test_python_package_runners(cmd, want):
    assert [d.name for d in parse_pip_command(cmd)] == want


def test_runners_inside_chains_and_prose():
    text = "I'll start the server: cd app && npx -y ghost-mcp-server; then uvx ghost-lint ."
    assert [d.name for d in parse_npm_command(text)] == ["ghost-mcp-server"]
    assert [d.name for d in parse_pip_command(text)] == ["ghost-lint"]



# Qodo review of #14: each case is the reviewer's own example.
@pytest.mark.parametrize("cmd,want", [
    ("npm exec --workspace app ghost-tool", ["ghost-tool"]),        # 1: option values are not the package
    ("npm exec foo --package=ghost-pkg", ["ghost-pkg"]),             # 2: npm exec reads --package anywhere before --
    ("npx serve -p 3000", ["serve"]),                                 #    ...but npx stops at the first positional
    ("(npx ghost-tool)", ["ghost-tool"]),                             # 5: closing ) is not part of the name
    ("I'll use npx to scaffold the app", []),                         # 4: prose mention, not a command
    ("Run it with: npx -y ghost-mcp", ["ghost-mcp"]),                 #    ...a command after a colon still counts
])
def test_npm_runner_review_cases(cmd, want):
    assert [d.name for d in parse_npm_command(cmd)] == want


@pytest.mark.parametrize("cmd,want", [
    ("pipx run --fetch-python missing ghost-tool", ["ghost-tool"]),   # 1
    ("uvx --with ghost-plugin ruff", ["ghost-plugin", "ruff"]),       # 3: --with installs extra packages
    ("uvx --with a-plugin,b-plugin ruff", ["a-plugin", "b-plugin", "ruff"]),
    ("uvx -p 3.12 ghost-cli", ["ghost-cli"]),                         #    uvx -p is --python, not a package
])
def test_python_runner_review_cases(cmd, want):
    assert [d.name for d in parse_pip_command(cmd)] == want


def test_bare_runner_line_in_answer_is_checked():
    # 6: an unfenced command line in an agent answer.
    assert extract_from_answer("Start it:\nnpx -y ghost-mcp\n", "javascript").npm_installs == ["ghost-mcp"]


# #25: pnpm's -w is --workspace-root (no value); npm's -w is --workspace <name>
@pytest.mark.parametrize("cmd,expected", [
    ("pnpm add -w expres", ["expres"]),
    ("pnpm add --workspace-root expres", ["expres"]),
    ("pnpm add expres -w", ["expres"]),
    ("npm install -w web expres", ["expres"]),
    ("npm install --workspace web expres", ["expres"]),
    ("pnpm add -F web expres", ["expres"]),
    ("pnpm add --filter web expres", ["expres"]),
    ("pnpm add -w expres && npm install -w web lodahs", ["expres", "lodahs"]),
    ("npm install -w web pnpm", ["pnpm"]),
    ("npm install -w web pnpm lodash", ["pnpm", "lodash"]),
    ("sudo pnpm add -w expres", ["expres"]),
])
def test_workspace_flags_per_package_manager(cmd, expected):
    assert [d.name for d in parse_npm_command(cmd)] == expected


# #29: pnpm add --workspace only links a local workspace package; it never fetches from npm
@pytest.mark.parametrize("cmd,expected", [
    ("pnpm add --workspace @acme/shared", []),
    ("pnpm add @acme/shared --workspace", []),
    ("pnpm add --workspace @acme/shared && pnpm add lodahs", ["lodahs"]),
    ("pnpm add lodash", ["lodash"]),
    ("pnpm add -w lodash", ["lodash"]),
    ("pnpm add --workspace-root lodash", ["lodash"]),
    ("npm install -w web lodash", ["lodash"]),
    ("npm install --workspace web lodash", ["lodash"]),
])
def test_pnpm_workspace_only_packages_are_not_checked_on_npm(cmd, expected):
    assert [d.name for d in parse_npm_command(cmd)] == expected


# #30: the workspace: protocol links a local package; it is never fetched from npm
@pytest.mark.parametrize("cmd,expected", [
    ("pnpm add @acme/shared@workspace:*", []),
    ("yarn add @acme/shared@workspace:^", []),
    ("pnpm add shared-utils@workspace:~ lodahs", ["lodahs"]),
    ("pnpm add lodash@^4", ["lodash"]),
    ("npm install @types/node@20", ["@types/node"]),
])
def test_workspace_protocol_packages_are_not_checked_on_npm(cmd, expected):
    assert [d.name for d in parse_npm_command(cmd)] == expected


# #31: pnpm options before the subcommand must not hide the install (fail-open)
@pytest.mark.parametrize("cmd,expected", [
    ("pnpm --filter web add lodahs", ["lodahs"]),
    ("pnpm -F web add lodahs", ["lodahs"]),
    ("pnpm -C ./app add lodahs", ["lodahs"]),
    ("pnpm --dir=./app add lodahs", ["lodahs"]),
    ("pnpm -r add lodahs", ["lodahs"]),
    ("pnpm add lodahs", ["lodahs"]),
    ("pnpm --filter web add --workspace @acme/shared", []),
    ("pnpm --filter web run build", []),
])
def test_pnpm_options_before_subcommand_are_still_checked(cmd, expected):
    assert [d.name for d in parse_npm_command(cmd)] == expected


# #31 review r1: shell quoting in option values, a selector named like a subcommand, long input
@pytest.mark.parametrize("cmd,expected", [
    ('pnpm --dir "./my app" add lodahs', ["lodahs"]),
    (r"pnpm -C ./my\ app add lodahs", ["lodahs"]),
    ("pnpm --filter add install lodahs", ["lodahs"]),
    ("pnpm --reporter silent add lodahs", ["lodahs"]),
])
def test_pnpm_option_values_are_read_as_shell_tokens(cmd, expected):
    assert [d.name for d in parse_npm_command(cmd)] == expected


def test_long_pnpm_text_without_a_subcommand_is_fast():
    import time
    text = " ".join(["pnpm -x"] * 5000)
    t = time.perf_counter()
    assert parse_npm_command(text) == []
    assert time.perf_counter() - t < 1.0


# #31 PR review: --workspace and value-taking options placed before the subcommand
@pytest.mark.parametrize("cmd,expected", [
    ("pnpm --workspace add @acme/shared", []),
    ("pnpm --registry https://registry.example add lodahs", ["lodahs"]),
    ("pnpm --prefix ./app add lodahs", ["lodahs"]),
])
def test_pnpm_options_before_subcommand_keep_their_meaning(cmd, expected):
    assert [d.name for d in parse_npm_command(cmd)] == expected


# #34: npm, yarn and bun options before the subcommand must not hide the install (fail-open)
@pytest.mark.parametrize("cmd,expected", [
    ("npm --prefix ./app install lodahs", ["lodahs"]),
    ("npm -w web install lodahs", ["lodahs"]),
    ("yarn --cwd app add lodahs", ["lodahs"]),
    ("bun --cwd app add lodahs", ["lodahs"]),
    ("npm install lodahs", ["lodahs"]),
    ("npm install -w web lodahs", ["lodahs"]),
    ("yarn add lodahs", ["lodahs"]),
    ("yarn global add lodahs", ["lodahs"]),
    ("npm --prefix ./app run build", []),
])
def test_npm_yarn_bun_options_before_subcommand_are_still_checked(cmd, expected):
    assert [d.name for d in parse_npm_command(cmd)] == expected


# #34: a manager word that is not an install must not hide a later install in the same line
@pytest.mark.parametrize("cmd,expected", [
    ("use npm or yarn add lodahs", ["lodahs"]),
    ("Run `npm --prefix app install lodahs`", ["lodahs"]),
])
def test_later_install_after_a_non_install_manager_word(cmd, expected):
    assert [d.name for d in parse_npm_command(cmd)] == expected


def test_long_npm_text_without_a_subcommand_is_fast():
    import time
    text = " ".join(["npm -x yarn -y"] * 3000)
    t = time.perf_counter()
    assert parse_npm_command(text) == []
    assert time.perf_counter() - t < 1.0


# #34 review: a manager word inside a quoted or escaped option value is not a new command
@pytest.mark.parametrize("cmd,expected", [
    ('pnpm -C "./npm project" add lodahs', ["lodahs"]),
    ('pnpm -C "my npm stuff" add lodahs', ["lodahs"]),
    ("npm --prefix 'a yarn b' install lodahs", ["lodahs"]),
    (r"yarn --cwd my\ bun\ app add lodahs", ["lodahs"]),
])
def test_manager_word_inside_quotes_is_not_a_command(cmd, expected):
    assert [d.name for d in parse_npm_command(cmd)] == expected


# #34 PR review r2: escaped quotes, more value options, a manager word as an option value, many quotes
@pytest.mark.parametrize("cmd,expected", [
    ('npm --prefix "a \\"npm x\\"" install lodahs', ["lodahs"]),
    ("npm --omit dev install lodahs", ["lodahs"]),
    ("yarn --mutex network add lodahs", ["lodahs"]),
    ("npm -w yarn install lodahs", ["lodahs"]),
])
def test_install_found_through_tricky_option_values(cmd, expected):
    assert [d.name for d in parse_npm_command(cmd)] == expected


def test_many_quoted_values_and_manager_words_are_fast():
    import time
    text = " ".join(["'x' npm -x"] * 3000)
    t = time.perf_counter()
    assert parse_npm_command(text) == []
    assert time.perf_counter() - t < 1.0


def test_each_inline_command_in_a_line_is_checked():
    assert [d.name for d in parse_npm_command("Run `npm i expres` then `yarn add lodahs`")] == ["expres", "lodahs"]


# Ticket #26: values of pip options are not packages; packages after them are still checked.
_PIP_VALUE_OPTIONS_26 = [
    "--upgrade-strategy eager", "--progress-bar off", "--log pip.log", "--proxy http://proxy:3128",
    "--retries 3", "--timeout 9", "--exists-action w", "--no-binary :all:", "--only-binary :all:",
    "--config-settings key=val", "-C key=val", "--report report.json", "--cert ca.pem",
    "--client-cert client.pem", "--use-feature truststore", "--python 3.12",
    # found by the Qodo review of the change (same class of bug)
    "--keyring-provider subprocess", "--root-user-action ignore", "--install-option warn",
    "--global-option disabled",
]


@pytest.mark.parametrize("opt", _PIP_VALUE_OPTIONS_26)
def test_pip_option_values_are_not_packages(opt):
    names = [d.name for d in parse_pip_command(f"pip install {opt} reqests")]
    assert names == ["reqests"], (opt, names)


@pytest.mark.parametrize("cmd", ["conda install -C reqests", "mamba install -C reqests"])
def test_conda_cache_switch_does_not_hide_the_package(cmd):
    # conda/mamba -C (--use-index-cache) takes no value, unlike pip's -C/--config-settings
    assert [d.name for d in parse_pip_command(cmd)] == ["reqests"]


@pytest.mark.parametrize("cmd, expected", [
    ("npm i --loglevel warn react", ["react"]),
    ("npm install --omit dev express", ["express"]),
    ("npm install --omit=dev express", ["express"]),
    ("npm install --include optional sharp", ["sharp"]),
    ("npm install --install-strategy nested axios", ["axios"]),
    ("npm i --before 2024-01-01 debug", ["debug"]),
    ("npm install --cache /tmp/c lodash", ["lodash"]),
    ("npm install --userconfig ./.npmrc left-pad", ["left-pad"]),
    ("npm install --otp 123456 left-pad", ["left-pad"]),
    ("npm install --audit-level high left-pad", ["left-pad"]),
    ("yarn add --network-timeout 100000 chalk", ["chalk"]),
    ("yarn add --cwd app chalk", ["chalk"]),
    ("yarn add --mutex network chalk", ["chalk"]),
    ("yarn add --modules-folder vendor chalk", ["chalk"]),
    ("pnpm add --reporter silent zod", ["zod"]),
    ("pnpm add --dir web zod", ["zod"]),
    ("pnpm add -C web zod", ["zod"]),
    ("bun add --cwd app zod", ["zod"]),
    ("bun add --backend copyfile zod", ["zod"]),
    ("bun add --cache-dir .cache zod", ["zod"]),
])
def test_package_manager_option_values_are_not_packages(cmd, expected):
    assert [d.name for d in parse_npm_command(cmd)] == expected


@pytest.mark.parametrize("cmd, expected", [
    ("npm install --save-dev typescript", ["typescript"]),
    ("npm i -D vitest", ["vitest"]),
    ("pnpm add -w zod", ["zod"]),
    ("yarn add --frozen-lockfile chalk", ["chalk"]),
    ("bun add -d zod", ["zod"]),
])
def test_boolean_flags_never_swallow_the_package(cmd, expected):
    assert [d.name for d in parse_npm_command(cmd)] == expected


@pytest.mark.parametrize("cmd, expected", [
    # the same value-taking options placed before the install subcommand (Qodo review on #38)
    ("npm --otp 123456 install zod", ["zod"]),
    ("npm --audit-level high i zod", ["zod"]),
    ("bun --cache-dir .cache add zod", ["zod"]),
    ("bun --backend copyfile add zod", ["zod"]),
    # and in runner commands (npx / npm exec / pnpm dlx / yarn dlx)
    ("npx --loglevel warn create-react-app", ["create-react-app"]),
    ("pnpm dlx --reporter silent create-vite", ["create-vite"]),
    ("npm exec --loglevel warn -- cowsay", ["cowsay"]),
    ("yarn dlx --cwd app create-vite", ["create-vite"]),
])
def test_option_values_before_the_subcommand_and_in_runners(cmd, expected):
    assert [d.name for d in parse_npm_command(cmd)] == expected
