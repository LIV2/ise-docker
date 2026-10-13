# By default install from local vendor media; an existing unpatched image
# can supply the files instead with --build-arg ISE_BASE_IMAGE=...
ARG ISE_BASE_IMAGE=install

# Installer, USB driver build and runtime share one Ubuntu release.
FROM ubuntu:22.04 AS base
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates git make time \
    libglib2.0-0 libsm6 libxi6 libxrender1 libxrandr2 libxtst6 \
    libfreetype6 libfontconfig1 libncurses5 libusb-0.1-4 usbutils fxload \
    && rm -rf /var/lib/apt/lists/*

FROM base AS install
# Accept the full Linux archive or the original four split archives.
COPY xilinx-installer/ /tmp/media/
COPY files/tmp/install/config /tmp/install/config
COPY tools/install-vendor /usr/local/bin/install-vendor
RUN /usr/local/bin/install-vendor && \
    rm -rf /tmp/install /tmp/media /tmp/Xilinx_ISE_DS_* && \
    rm -rf /opt/Xilinx/14.7/ISE_DS/EDK /opt/Xilinx/14.7/ISE_DS/PlanAhead

FROM base AS usb-driver
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libc6-dev libusb-dev && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/dennisfen/xilinx-usb-driver.git /opt/xilinx-usb-driver && \
    cd /opt/xilinx-usb-driver && \
    git checkout 2d19c7cb325c8cd15b252dd5b8de7a643bb5295d && \
    make libusb-driver.so && rm -rf .git

FROM ${ISE_BASE_IMAGE} AS installed

FROM base AS runtime
COPY --from=usb-driver /opt/xilinx-usb-driver /opt/xilinx-usb-driver

# Keep all ISE device databases and both library architectures. EDK and
# PlanAhead are separate products and are not needed for this CLI target.
COPY --from=installed /opt/Xilinx/14.7/ISE_DS/ISE /opt/Xilinx/14.7/ISE_DS/ISE
COPY --from=installed /opt/Xilinx/14.7/ISE_DS/common /opt/Xilinx/14.7/ISE_DS/common
COPY tools/patch-iostreams.py /usr/local/lib/ise/patch-iostreams.py
# Apply the binary compatibility patch only when explicitly requested.
ARG ENABLE_ROSETTA_COMPATIBILITY=0
RUN set -e; case "$ENABLE_ROSETTA_COMPATIBILITY" in \
        0) exit 0 ;; \
        1) ;; \
        *) echo 'ENABLE_ROSETTA_COMPATIBILITY must be 0 or 1' >&2; exit 2 ;; \
    esac; \
    apt-get update; \
    apt-get install -y --no-install-recommends python3; \
    rm -rf /var/lib/apt/lists/*; \
    for component in ISE common; do \
    library=/opt/Xilinx/14.7/ISE_DS/$component/lib/lin64/libisl_iostreams.so; \
    python3 /usr/local/lib/ise/patch-iostreams.py "$library" "$library.patched"; \
    mv "$library" "$library.original"; \
    mv "$library.patched" "$library"; \
    done

# GUI support is independent of the optional Rosetta compatibility patch.
ARG ENABLE_GUI=1
RUN case "$ENABLE_GUI" in \
        0) exit 0 ;; \
        1) ;; \
        *) echo 'ENABLE_GUI must be 0 or 1' >&2; exit 2 ;; \
    esac && \
    apt-get update && apt-get install -y --no-install-recommends \
        openjdk-8-jre build-essential libxmu6 libxm4 libxpm4 libstdc++5 \
        x11-utils xauth xterm fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/* && \
    mv /opt/Xilinx/14.7/ISE_DS/ISE/java/lin64/jre \
       /opt/Xilinx/14.7/ISE_DS/ISE/java/lin64/jre.original && \
    ln -s /usr/lib/jvm/java-8-openjdk-amd64/jre \
       /opt/Xilinx/14.7/ISE_DS/ISE/java/lin64/jre && \
    for tool in analyzer inserter; do \
        script=/opt/Xilinx/14.7/ISE_DS/ISE/bin/lin64/unwrapped/$tool; \
        test "$(head -n 1 "$script")" = '#!/bin/sh' && \
        sed -i '1s|#!/bin/sh|#!/bin/bash|' "$script" || exit 1; \
    done

COPY files/usr/local/bin/wrapper /usr/local/bin/wrapper
COPY tools/gui-entrypoint /usr/local/bin/ise-gui-entrypoint
COPY tools/impact /usr/local/bin/impact
ENV ISE_ENABLE_GUI=${ENABLE_GUI}
ENV HOME=/tmp LANG=C.UTF-8
WORKDIR /build
ENTRYPOINT ["/usr/local/bin/wrapper"]
CMD ["bash"]
