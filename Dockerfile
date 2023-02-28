ARG FUNCTION_DIR="/home/app/"
ARG RUNTIME_VERSION="3.8"

FROM python:${RUNTIME_VERSION}-slim-bullseye AS python-alpine
RUN apt-get install -o APT::Keep-Downloaded-Packages=false \
    libstdc++

FROM python-alpine AS build-image
RUN apt-get update && \
    apt-get install -y \
    # apt-get install -o APT::Keep-Downloaded-Packages=false \
    g++ \
    make \
    cmake \
    unzip \
    libcurl4-openssl-dev
ARG FUNCTION_DIR
ARG RUNTIME_VERSION
RUN mkdir -p ${FUNCTION_DIR}
COPY . ${FUNCTION_DIR}
RUN python${RUNTIME_VERSION} -m pip install --upgrade pip
RUN python${RUNTIME_VERSION} -m pip install awslambdaric --target ${FUNCTION_DIR}

FROM python-alpine
ARG FUNCTION_DIR
WORKDIR ${FUNCTION_DIR}
COPY --from=build-image ${FUNCTION_DIR} ${FUNCTION_DIR}
ADD https://github.com/aws/aws-lambda-runtime-interface-emulator/releases/latest/download/aws-lambda-rie /usr/bin/aws-lambda-rie
COPY entry.sh /
COPY requirements.txt /
RUN chmod 755 /usr/bin/aws-lambda-rie /entry.sh
RUN apt-get update && \
    apt-get install -y git
RUN python${RUNTIME_VERSION} -m pip install --upgrade pip
RUN python${RUNTIME_VERSION} -m pip install numpy
RUN python${RUNTIME_VERSION} -m pip install python-dateutil
RUN python${RUNTIME_VERSION} -m pip install pytz
RUN python${RUNTIME_VERSION} -m pip install -r requirements.txt
ENTRYPOINT [ "/entry.sh" ]
CMD [ "src/app.handler" ]