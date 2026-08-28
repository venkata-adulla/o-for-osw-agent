# Only needed for hosts (like Render) that build an image from a Dockerfile
# rather than accepting a bare public image + a bind-mounted config file --
# docker-compose.yml still uses the public otel/opentelemetry-collector-contrib
# image directly with a mounted config, unchanged.
FROM otel/opentelemetry-collector-contrib:0.115.1
COPY collector-config.yaml /etc/otel/config.yaml
CMD ["--config=/etc/otel/config.yaml"]
