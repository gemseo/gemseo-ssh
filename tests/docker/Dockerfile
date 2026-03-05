FROM public.ecr.aws/docker/library/python:3.12-slim

ARG GEMSEO_PACKAGE_SPEC
ARG WORKDIR=/workdir

# Install OpenSSH server
RUN apt-get update && apt-get install -y \
    openssh-server git \
    && rm -rf /var/lib/apt/lists/* \

# Set GEMSEO_PATH so GEMSEO can find custom disciplines
ENV GEMSEO_PATH=${WORKDIR}
RUN echo "GEMSEO_PATH=${WORKDIR}" >> /etc/environment

# Configure SSH
RUN mkdir -p /var/run/sshd
RUN echo 'root:testpassword' | chpasswd
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config

# Install gemseo with the deserialize-run command
RUN pip install --no-cache-dir "${GEMSEO_PACKAGE_SPEC}"


# Create test working directory
RUN mkdir -p ${WORKDIR}

# Copy test module for SSH integration tests
COPY tests/disc_with_files.py ${WORKDIR}/disc_with_files.py

# Expose SSH port
EXPOSE 22

# Start SSH daemon
CMD ["/usr/sbin/sshd", "-D"]
