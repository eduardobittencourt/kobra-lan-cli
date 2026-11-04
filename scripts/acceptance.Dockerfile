ARG DISTRO
FROM ${DISTRO}
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-cryptography passwd util-linux \
    && rm -rf /var/lib/apt/lists/* \
    && echo disposable > /run/kobra-package-acceptance
COPY scripts/accept_deb.py /accept_deb.py
COPY scripts/probe_pairing.py /probe_pairing.py
COPY scripts/probe_profiles.py /probe_profiles.py
