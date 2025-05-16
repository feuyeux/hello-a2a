# Hello A2A

```sh
export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
uv pip install -e .
uv run agents
```

```sh
uv run hosts
```

UT

```sh
python -m pytest agents/test_agent.py
```
