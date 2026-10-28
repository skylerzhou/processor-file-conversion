# Build JRE
FROM eclipse-temurin:17.0.10_7-jre-jammy AS jre

# Builder stage: clone and build mef2streamer (produces the jar)
FROM maven:3.9.4-eclipse-temurin-17 AS builder
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /build

# The commit of Pennsieve/mef2streamer the jar is built from. Pinned, so a
# change upstream cannot alter this image unnoticed; move the pin on purpose
# to pick up a newer streamer. (app-deploy-service passes no build args, so
# this default is what the platform builds.)
ARG MEF2STREAMER_REF=0e7304775811e5e8b44cc0e71479563f7b272cc0

# Bust the cache when the ref moves: ADD re-fetches this URL on every build and
# invalidates the layer only when the commit it names actually changes.
ADD https://api.github.com/repos/Pennsieve/mef2streamer/commits/${MEF2STREAMER_REF} /build/mef2streamer-ref.json

# Resolve the ref to a commit before checkout so a SHA, a tag, the default
# branch and a remote-only branch all work (see processor-mef-timeseries for
# the why).
RUN git clone https://github.com/Pennsieve/mef2streamer src \
	&& git -C src checkout --detach "$(git -C src rev-parse --verify --quiet "${MEF2STREAMER_REF}^{commit}" \
		|| git -C src rev-parse --verify "origin/${MEF2STREAMER_REF}^{commit}")" \
	&& git -C src log -1 --format='mef2streamer build ref: %H %s' \
	&& mvn -B -f src/pom.xml clean package -DskipTests \
	&& cp src/target/mef2streamer-0.0.1-SNAPSHOT-jar-with-dependencies.jar /build/mefstreamer.jar

FROM python:3.12

COPY --from=jre /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH="$JAVA_HOME/bin:${PATH}"

COPY --from=builder /build/mefstreamer.jar /processor/mefstreamer.jar

RUN java -version && python --version

RUN apt clean && apt-get update && apt-get -y install libhdf5-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY processor/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY processor/ /app/processor/
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV PYTHONPATH="/app"
# pynwb/platformdirs needs a writable cache dir; HOME may be unset or
# read-only on Lambda and in the compute env.
ENV XDG_CACHE_HOME=/tmp/.cache

# Dual-mode entrypoint: Lambda when AWS_LAMBDA_RUNTIME_API is set, else CMD.
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "processor.main"]
