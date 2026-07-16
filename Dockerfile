# syntax=docker/dockerfile:1
# Nephos control-plane image: nephos-api + the tools it drives at runtime
# (pulumi CLI for the Automation API, kubectl for the Zitadel provisioner).

FROM python:3.12-slim AS build
WORKDIR /app
RUN pip install --no-cache-dir build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m build --wheel

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1
# curl/ca-certs/git for the pulumi install + plugin fetch; kubectl for zitadel.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates git \
 && rm -rf /var/lib/apt/lists/*
# pulumi CLI (Automation API shells out to it; resource plugins auto-install at runtime)
RUN curl -fsSL https://get.pulumi.com | sh \
 && ln -sf /root/.pulumi/bin/pulumi /usr/local/bin/pulumi
# kubectl (matches the image arch)
RUN curl -fsSL "https://dl.k8s.io/release/$(curl -fsSL https://dl.k8s.io/release/stable.txt)/bin/linux/$(dpkg --print-architecture)/kubectl" \
      -o /usr/local/bin/kubectl \
 && chmod +x /usr/local/bin/kubectl
COPY --from=build /app/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -f /tmp/*.whl
ENV PORT=8099
EXPOSE 8099
CMD ["nephos-api", "serve", "--host", "0.0.0.0", "--port", "8099"]
