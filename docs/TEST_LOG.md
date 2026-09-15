# Test Log

Record command results here so experiment state remains recoverable.

## 2026-09-16 — Planning structure review

- Compared SHA-256 fingerprints before/after the documentation changes for all 22 existing Python, XML, TOML and YAML files: identical; no implementation or runtime configuration changes.
- Checked relative Markdown links across 15 root/config/project documents: no missing targets.
- Reviewed active-plan, historical-roadmap, and pending-choice labels for consistency with the Claude implementation handoff.
- These were documentation consistency checks only. No application tests, package installation, physics simulation, or learning experiment was run.

## 2026-09-15–16 — Planning review

- Read 19 Python files, XML, config, package metadata, and project documents.
- Parsed all Python sources with `ast.parse`, without importing dependencies or generating bytecode: 19 passed.
- Current shell inspection: arm64, macOS 26.6.2, Python 3.14.0. NumPy, MuJoCo, Gymnasium, PyTorch, Brian2, SB3 and pytest were absent from this interpreter.
- Memory query `sysctl -n hw.memsize` was denied; available RAM remains unknown.
- Analytic launch check: missing gravity correction causes 2.5428–4.4268 m displacement relative to target over 0.72–0.95 s, assuming free flight. Ground collision was not simulated.
- No local `.git` entry in the project folder. No Git initialization was performed.
- Initial documentation patch was rejected during patch validation; no files changed in that attempt. A revised documentation-only patch was then applied.
- No dependency installation, runtime physics test, external model execution, training, or dataset download was performed.

These checks establish source findings, not physics correctness or model performance.

## 2026-09-15

### Command

```bash
python3 -m compileall envs controllers encoders train analysis demos
```

### Result

Passed. All Python source files compiled successfully.

### Notes

The local shell did not provide `python`; `python3` was used instead.

## 2026-09-15

### Command

```bash
python3 -c "import tomllib; tomllib.load(open('pyproject.toml','rb')); print('pyproject ok')"
```

### Result

Passed. `pyproject.toml` parsed successfully.

## 2026-09-15

### Command

```bash
python3 -c "import xml.etree.ElementTree as ET; ET.parse('envs/assets/fly_batter.xml'); print('xml ok')"
```

### Result

Passed. The MuJoCo XML file is well-formed XML.

### Limitations

This only checks XML syntax. It does not validate MuJoCo semantics or runtime physics behavior.

## 2026-09-15

### Command

```bash
python3 -c "import sys; print(sys.version); import importlib.util; print('mujoco', importlib.util.find_spec('mujoco')); print('gymnasium', importlib.util.find_spec('gymnasium'))"
```

### Result

`mujoco` and `gymnasium` were not installed in the current environment.

### Next Runtime Test

After installing dependencies:

```bash
pip install -e ".[dev]"
python demos/record_episode.py --episodes 3 --render none
```
