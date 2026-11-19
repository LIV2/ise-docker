# By default install from local vendor media; an existing unpatched image
# can supply the files instead with --build-arg ISE_BASE_IMAGE=...
ARG ISE_BASE_IMAGE=install

# Installer, USB driver build and runtime share one Ubuntu release.
FROM ubuntu:22.04 AS base
# SmartXplorer and findmgsg are 32-bit even in the vendor lin64 directory.
# FlexNet uses the LSB loader name, and legacy helper scripts use csh/perl5.
RUN dpkg --add-architecture i386 && \
    apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates git make perl tcsh time \
    libglib2.0-0 libsm6 libxi6 libxrender1 libxrandr2 libxtst6 \
    libfreetype6 libfontconfig1 libncurses5 libusb-0.1-4 usbutils fxload \
    libc6:i386 libgcc-s1:i386 libstdc++5:i386 libncurses5:i386 \
    && rm -rf /var/lib/apt/lists/* && \
    ln -s /lib64/ld-linux-x86-64.so.2 /lib64/ld-lsb-x86-64.so.3 && \
    ln -s /lib/ld-linux.so.2 /lib/ld-lsb.so.3 && \
    ln -s /usr/bin/perl /usr/local/bin/perl5

# XPrint is still linked by FPGA Editor and the older Motif tools, but
# Ubuntu 22.04 no longer ships libXp. Build the upstream runtime library
# separately so its compilers and protocol headers stay out of the image.
FROM base AS xprint
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl pkg-config libx11-dev libxext-dev libxau-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /tmp/xprint
RUN curl -fL https://www.x.org/releases/individual/proto/printproto-1.0.5.tar.bz2 \
        -o printproto.tar.bz2 && \
    echo '1298316cf43b987365ab7764d61b022a3d7f180b67b423eed3456862d155911a  printproto.tar.bz2' | sha256sum -c - && \
    tar -xf printproto.tar.bz2 && \
    cd printproto-1.0.5 && ./configure --prefix=/usr && make install
RUN curl -fL https://www.x.org/releases/individual/lib/libXp-1.0.4.tar.xz \
        -o libXp.tar.xz && \
    echo '1f19e3b8e82a34a8fd9889a7d9af0abe8588cb03fb57c37c569634cf3b9df1a4  libXp.tar.xz' | sha256sum -c - && \
    tar -xf libXp.tar.xz && cd libXp-1.0.4 && \
    ./configure --prefix=/usr --libdir=/usr/lib/x86_64-linux-gnu --disable-static && \
    make -j4 && make install

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

FROM usb-driver AS native-compat
COPY tools/zynqconfig-test-compat.c /tmp/zynqconfig-test-compat.c
RUN gcc -shared -fPIC -O2 -Wall -Wextra -Werror \
    /tmp/zynqconfig-test-compat.c -o /tmp/zynqconfig-test-compat.so -ldl
COPY tools/xilhelp-compat.c /tmp/xilhelp-compat.c
RUN gcc -shared -fPIC -O2 -Wall -Wextra -Werror \
    /tmp/xilhelp-compat.c -o /tmp/xilhelp-compat.so -ldl
RUN apt-get update && apt-get install -y --no-install-recommends python3 && \
    rm -rf /var/lib/apt/lists/*
COPY tools/patch-windu-registry.py /tmp/patch-windu-registry.py
COPY --from=installed /opt/Xilinx/14.7/ISE_DS/ISE/bin/lin64/windu_registryd50 /tmp/windu_registryd50.original
RUN python3 /tmp/patch-windu-registry.py \
    /tmp/windu_registryd50.original /tmp/windu_registryd50

FROM base AS runtime
COPY --from=usb-driver /opt/xilinx-usb-driver /opt/xilinx-usb-driver
COPY --from=xprint /usr/lib/x86_64-linux-gnu/libXp.so.6.2.0 /usr/lib/x86_64-linux-gnu/
RUN ln -s libXp.so.6.2.0 /usr/lib/x86_64-linux-gnu/libXp.so.6
COPY --from=native-compat /tmp/zynqconfig-test-compat.so /usr/local/lib/ise/
COPY --from=native-compat /tmp/xilhelp-compat.so /usr/local/lib/ise/

# Keep all ISE device databases and both library architectures. EDK and
# PlanAhead are separate products and are not needed for this CLI target.
COPY --from=installed /opt/Xilinx/14.7/ISE_DS/ISE /opt/Xilinx/14.7/ISE_DS/ISE
COPY --from=installed /opt/Xilinx/14.7/ISE_DS/common /opt/Xilinx/14.7/ISE_DS/common
COPY --from=native-compat /tmp/windu_registryd50 /opt/Xilinx/14.7/ISE_DS/ISE/bin/lin64/windu_registryd50
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
# The ChipScope launchers source cs_common.sh, which requires Bash.
ARG ENABLE_GUI=1
RUN case "$ENABLE_GUI" in \
        0) exit 0 ;; \
        1) ;; \
        *) echo 'ENABLE_GUI must be 0 or 1' >&2; exit 2 ;; \
    esac && \
    apt-get update && apt-get install -y --no-install-recommends \
        openjdk-8-jre build-essential libxmu6 libxm4 libxpm4 libstdc++5 \
        x11-utils xauth xterm fonts-dejavu-core xfonts-base xfonts-75dpi && \
    rm -rf /var/lib/apt/lists/* && \
    jre=/opt/Xilinx/14.7/ISE_DS/ISE/java/lin64/jre && \
    if [ -L "$jre" ]; then \
        test "$(readlink "$jre")" = /usr/lib/jvm/java-8-openjdk-amd64/jre && \
        test -x "$jre.original/bin/java" || exit 1; \
    else \
        test -d "$jre" && test ! -e "$jre.original" && \
        mv "$jre" "$jre.original" && \
        ln -s /usr/lib/jvm/java-8-openjdk-amd64/jre "$jre" || exit 1; \
    fi && \
    for tool in analyzer inserter ibertgenerate ibertgengui ibertplotter; do \
        script=/opt/Xilinx/14.7/ISE_DS/ISE/bin/lin64/unwrapped/$tool; \
        case "$(head -n 1 "$script")" in \
            '#!/bin/sh') sed -i '1s|#!/bin/sh|#!/bin/bash|' "$script" ;; \
            '#!/bin/bash') ;; \
            *) echo "Unexpected launcher interpreter: $script" >&2; exit 1 ;; \
        esac; \
    done

COPY --from=native-compat /tmp/windu_registryd50.original /opt/Xilinx/14.7/ISE_DS/ISE/bin/lin64/windu_registryd50.original
COPY files/usr/local/bin/wrapper /usr/local/bin/wrapper
COPY tools/gui-entrypoint /usr/local/bin/ise-gui-entrypoint
COPY tools/impact /usr/local/bin/impact
COPY tools/zynqconfig_test /usr/local/bin/zynqconfig_test
COPY tools/xilhelp /usr/local/bin/xilhelp
ENV ISE_ENABLE_GUI=${ENABLE_GUI}
ENV HOME=/tmp LANG=C.UTF-8
WORKDIR /build
ENTRYPOINT ["/usr/local/bin/wrapper"]
CMD ["bash"]
