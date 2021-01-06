FROM ubuntu:14.04

RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

RUN sed 's/main$/main universe/' -i /etc/apt/sources.list
RUN apt-get update
RUN apt-get upgrade -y

RUN apt-get install -y build-essential xorg libssl-dev libxrender-dev wget gdebi
RUN apt-get install -y python3 python3-pip

# Download and install wkhtmltopdf
#RUN wget http://downloads.sourceforge.net/project/wkhtmltopdf/0.12.2.1/wkhtmltox-0.12.2.1_linux-trusty-amd64.deb
#RUN gdebi --n wkhtmltox-0.12.2.1_linux-trusty-amd64.deb
RUN wget 'https://github.com/wkhtmltopdf/wkhtmltopdf/releases/download/0.12.4/wkhtmltox-0.12.4_linux-generic-amd64.tar.xz'
RUN tar xf wkht*
RUN cp -r wkht*/bin/* /usr/bin/
RUN cp -r wkht*/include/* /usr/include/

COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY . /



ENTRYPOINT ["python3"]

# Show the extended help
CMD ["./run.py"]
