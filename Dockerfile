# Sports Store - payment service.
#
# Layer order is deliberate: requirements.txt is copied and installed before
# the application source, so editing a .py file reuses the cached dependency
# layer instead of reinstalling every package on every build.

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user. Nothing here needs root, and a container that does
# not need it should not have it.
RUN useradd --create-home --uid 1000 appuser
USER appuser

# Metadata only - this does not publish the port. Every service listens on
# 8000 inside its own container; the gateway reaches them by service name,
# so there is no need for five different internal ports.
EXPOSE 8000

# Bind 0.0.0.0, never 127.0.0.1 - a loopback bind is unreachable from other
# containers on the compose network.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]