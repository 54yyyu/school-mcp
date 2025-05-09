# Generated by https://smithery.ai. See: https://smithery.ai/docs/config#dockerfile
FROM python:3.10-slim

WORKDIR /app

# Copy all files before installation so that the src directory and all modules are available
COPY . ./

RUN pip install --upgrade pip && \
    pip install --no-cache-dir setuptools && \
    pip install --no-cache-dir .

CMD ["python", "-m", "school_mcp"]
