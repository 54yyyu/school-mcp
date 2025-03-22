"""Setup script for the School MCP package."""

from setuptools import setup, find_packages

setup(
    name="school-mcp",
    version="0.1.0",
    description="MCP server for academic tools",
    author="Your Name",
    author_email="your.email@example.com",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    include_package_data=True,
    python_requires=">=3.8",
    install_requires=[
        "mcp>=1.2.0",
        "canvasapi",
        "gradescope-api",
        "pandas",
        "pytz",
        "httpx",
        "tqdm",
        "python-dotenv",
    ],
    entry_points={
        "console_scripts": [
            "school-mcp=school_mcp.__main__:main",
        ],
    },
)
