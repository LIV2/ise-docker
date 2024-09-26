FROM ubuntu:14.04 AS install

RUN mkdir -p /tmp/install
# adding xilinx installer
COPY xilinx-installer/Xilinx_ISE_DS_14.7_1015_1-1.tar  /tmp
COPY xilinx-installer/Xilinx_ISE_DS_14.7_1015_1-3.zip.xz  /tmp
COPY xilinx-installer/Xilinx_ISE_DS_14.7_1015_1-2.zip.xz  /tmp
COPY xilinx-installer/Xilinx_ISE_DS_14.7_1015_1-4.zip.xz  /tmp

# adding scripts
ADD files /

# basic packages
RUN apt-get update && \
    apt-get -y install git expect locales \
    libglib2.0-0 libsm6 libxi6 libxrender1 libxrandr2 \
    libfreetype6 libfontconfig1

RUN cd /tmp/install && \
    tar xvf ../Xilinx_ISE_DS_14.7_1015_1-1.tar && \
    ls /tmp && \
    cd /tmp/install && \
    TERM=xterm /tmp/setup

RUN rm -rf /tmp/install/
RUN rm -rf /tmp/*
RUN rm -rf /opt/Xilinx/14.7/ISE_DS/EDK
RUN rm -rf /opt/Xilinx/14.7/ISE_DS/PlanAhead

FROM ubuntu:14.04

COPY --from=install /opt/Xilinx /opt/Xilinx
COPY files/usr/local/bin/wrapper /usr/local/bin

# basic packages
RUN apt-get update && \
    apt-get -y install git expect locales \
    libglib2.0-0 libsm6 libxi6 libxrender1 libxrandr2 \
    libfreetype6 libfontconfig1

# some essential tools..
RUN apt-get update && \
    apt-get -y install nano usbutils

# Set LOCALE to UTF8
RUN echo "en_US.UTF-8 UTF-8" > /etc/locale.gen && \
    locale-gen en_US.UTF-8 && \
    /usr/sbin/update-locale LANG=en_US.UTF-8
RUN chmod 777 /tmp/

RUN adduser --disabled-password --gecos '' ise

#setup libusb driver
RUN apt -y install libusb-dev gcc make git fxload && \
    cd /opt && \
    git clone https://github.com/dennisfen/xilinx-usb-driver.git && \
    cd xilinx-usb-driver && \
    make && \
    echo ise: | chpasswd -e && \
    mkdir -p /etc/hotplug/usb/xusbdfwu.fw/ && cp /opt/Xilinx/14.7/ISE_DS/ISE/bin/lin64/*.hex /etc/hotplug/usb/xusbdfwu.fw/ && \
    echo alias impact=\'LD_PRELOAD=/opt/xilinx-usb-driver/libusb-driver.so impact\' >> /home/ise/.bashrc

USER ise
WORKDIR /home/ise

#defeat tips at startup
RUN mkdir .config/Xilinx -p
COPY ISE.conf .config/Xilinx

#source ise settings
RUN echo "source /opt/Xilinx/14.7/ISE_DS/settings64.sh" >> /home/ise/.bashrc
