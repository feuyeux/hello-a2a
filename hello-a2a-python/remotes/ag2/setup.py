from setuptools import find_packages, setup


setup(
    name="a2a-samples-mcp",
    version="0.1.0",
    description="MCP agent using A2A and AG2",
    packages=find_packages(),
    python_requires=">=3.12",
    install_requires=[
        "ag2>=0.8.6",
        "ag2[mcp, openai]>=0.8.6",
        "google-genai>=1.10.0",
        "a2a-samples",
        "autogen>=0.2.19",
        "python-dotenv>=1.0.0",
        "litellm>=1.16.9",
        "pydantic",
    ],
)
