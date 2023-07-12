FROM debian:bullseye-slim

RUN apt-get update \
  && apt-get install -yq --no-install-recommends \
  curl \
  squid \
  gettext-base \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

COPY ./entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh \
  && mkdir -p /var/cache/squid \
  && mkdir -p /var/log/squid \
  && touch /run/squid.pid  \
  && chown -R nobody: /run/squid.pid /var/cache/squid /var/log/squid /var/spool/squid

RUN ln -sf /dev/stdout /var/log/squid/access.log

COPY ./squid.conf /etc/squid/squid.conf
RUN chown -R nobody: /etc/squid/

USER nobody

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
