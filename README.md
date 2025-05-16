# Hello A2A

## INSTALL
```sh
export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
uv pip install -e .
```

## RUN

```sh
uv run agents
```

```sh
uv run hosts
```

## UT

```sh
python -m pytest agents/test_agent.py
```

## Project Structure

### Resources
The project uses YAML resources for configuration data:
- Periodic table data is stored in `agents/resources/periodic_table.yml`
- Resources are loaded using utilities in `agents/resources/loader.py`

### Data Management
To update the periodic table data:
- Modify the YAML file directly in `agents/resources/periodic_table.yml`
