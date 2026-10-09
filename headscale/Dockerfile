FROM ghcr.io/juanfont/headscale:0.29.4 AS headscale

FROM alpine:3.22

RUN apk add --no-cache ca-certificates

COPY --from=headscale /ko-app/headscale /usr/local/bin/headscale
COPY render-config.yaml /etc/headscale/config.yaml

COPY bootstrap.sh /usr/local/bin/bootstrap-headscale

RUN chmod +x /usr/local/bin/bootstrap-headscale

ENTRYPOINT ["/bin/sh", "/usr/local/bin/bootstrap-headscale"]
