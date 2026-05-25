FROM alpine:3.20

RUN apk add --no-cache \
    bash \
    curl \
    iproute2 \
    iptables-legacy \
    openresolv \
    dumb-init \
    tinyproxy

RUN update-alternatives --install /sbin/iptables iptables /sbin/iptables-legacy 10

COPY tinyproxy.conf /etc/tinyproxy/tinyproxy.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/usr/bin/dumb-init", "/entrypoint.sh"]
