# Dockerfile for scrapy

FROM debian:sid
MAINTAINER seamus tuohy <code@seamustuohy.com>

RUN apt-get update

RUN apt-get install -y python3 \
                       python3-dev \
                       python3-pip


RUN apt-get install -y git \
                       build-essential \
                       libxml2-dev \
                       libxslt1-dev \
                       zlib1g-dev \
                       libffi-dev \
                       libssl-dev \
                       --no-install-recommends \
                       && rm -rf /var/lib/apt/lists/*


RUN pip3 install setuptools --upgrade
RUN pip3 install wheel --upgrade
RUN pip3 install Scrapy --upgrade
RUN pip3 install requests --upgrade
RUN pip3 install wayback --upgrade

WORKDIR /home
RUN git clone https://github.com/pastpages/savepagenow && \
    cd savepagenow && \
    python3 setup.py install


# run the application
# ENTRYPOINT ["/usr/local/bin/scrapy"]
CMD ["scrapy", "runspider", "/etc/spider/archive_site.py"]
