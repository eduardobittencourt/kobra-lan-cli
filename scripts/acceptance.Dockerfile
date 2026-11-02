ARG DISTRO
FROM ${DISTRO}
RUN apt-get update && apt-get install -y --no-install-recommends python3 passwd util-linux \
    && rm -rf /var/lib/apt/lists/* \
    && echo disposable > /run/kobra-package-acceptance
COPY scripts/accept_deb.py /accept_deb.py
