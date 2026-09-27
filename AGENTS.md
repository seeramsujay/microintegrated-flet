# CLAUDE.md: Operational Instructions for Claude

For the comprehensive architectural guide, refer to [`AGENTS.md`](AGENTS.md).

## Quick Reference Commands

### Running Tests
* **Hardware Unit Tests**:
  ```bash
  PYTHONPATH=src /home/suzaykid/.local/bin/uv run --directory sdk/python/packages/flet pytest tests/test_hardware.py
  ```
* **CLI Flash Tests**:
  ```bash
  PYTHONPATH=src:../flet/src /home/suzaykid/.local/bin/uv run --directory sdk/python/packages/flet-cli pytest tests/test_flash_command.py
  ```
* **Full Unit Test Suite**:
  ```bash
  uv run --group test pytest sdk/python/packages/flet/tests
  ```

### Code Formatting
* **Format Python Files**:
  ```bash
  uv run --directory sdk/python/packages/flet ruff format <path_to_files>
  ```

### Diagnostics
* **Run μFlet Hardware Diagnostics**:
  ```bash
  PYTHONPATH=src:../flet/src uv run --directory sdk/python/packages/flet-cli python3 -m flet_cli.cli flash --doctor
  ```

## Key Conventions
1. **Composite Controls**: Use `with contextlib.suppress(RuntimeError): self.update()` to avoid unmounted page errors.
2. **Text Styling**: `TextSpan` requires `style=TextStyle(color=...)`.
3. **Dropdowns**: Use `on_select`, not `on_change`.
4. **Skills Location**: Dedicated skills live in `.agents/skills/`.
