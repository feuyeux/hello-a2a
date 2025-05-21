# Hello A2A

## INSTALL

```sh
export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
uv pip install -e .
```

## RUN

> prompt:
> 在两个终端，依次执行 `uv run agents` 和 `uv run hosts`，启动过程如果遇到问题，先停下来解决问题。
> 执行过程如果遇到问题，立即解决。

```sh
lsof -i :10000 | grep LISTEN | awk '{print $2}' | xargs kill -9
c
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
