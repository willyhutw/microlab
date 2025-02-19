# aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws/$alias
# docker buildx build --platform linux/amd64,linux/arm64 -t public.ecr.aws/$alias/$repo:$tag -f Dockerfile . --push 

FROM fluent/fluentd:v1.18.0-debian-1.0

USER root

RUN apt update \
    && apt install -y curl build-essential autoconf automake libtool libgeoip-dev libmaxminddb-dev \
    && gem install fluent-plugin-rewrite-tag-filter --no-document --version 2.4.0 \
    && gem install fluent-plugin-record-modifier --no-document --version 2.2.0 \
    && gem install fluent-plugin-grok-parser --no-document --version 2.6.2 \
    && gem install fluent-plugin-geoip --no-document --version 1.3.2 \
    && curl -sSfL -o /opt/GeoLite2-City.mmdb https://github.com/P3TERX/GeoLite.mmdb/raw/download/GeoLite2-City.mmdb \
    && chmod 644 /opt/GeoLite2-City.mmdb \
    && gem sources --clear-all \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /tmp/* /var/tmp/* /usr/lib/ruby/gems/*/cache/*.gem

USER fluent
