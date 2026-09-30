FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir datasette==0.65.5
COPY . /app
RUN python scripts/fetch_locked_sources.py /tmp/ctw-source \
    && python scripts/build_snapshot.py build --ctw-root /tmp/ctw-source --output /app/ctw.sqlite \
    && rm -rf /tmp/ctw-source
EXPOSE 8080
CMD ["sh", "-c", "exec datasette serve -i /app/ctw.sqlite --metadata /app/datasette-metadata.json --plugins-dir /app/inspection_plugins --host 0.0.0.0 --port ${PORT:-8080}"]
