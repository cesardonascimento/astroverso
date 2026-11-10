ARG PYTHON_VERSION=3.13.18
FROM docker.io/library/python:${PYTHON_VERSION}-slim
ARG DISCORD_PY_VERSION=2.7.1
RUN pip install --no-cache-dir --disable-pip-version-check --root-user-action=ignore "discord.py==${DISCORD_PY_VERSION}"
COPY bot.py /app/bot.py
ENV PYTHONUNBUFFERED=1
CMD ["python", "-I", "/app/bot.py"]
