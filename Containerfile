FROM registry.access.redhat.com/ubi9/python-312

LABEL name="spypip" \
      summary="Python Packaging PR Analyzer" \
      description="Find and analyze packaging changes in GitHub pull requests" \
      version="1.0" \
      maintainer="Emilien Macchi <emacchi@redhat.com>"

WORKDIR /app

# Install git for patch application functionality
USER 0
RUN dnf install -y git && dnf clean all

COPY . .

RUN pip install --no-cache-dir -e .

RUN bash scripts/install-github-mcp-server.sh

USER 1001

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV PATH="$HOME/bin:$PATH"

ENTRYPOINT ["python", "-m", "spypip"]

CMD ["--help"]