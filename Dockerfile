FROM centos:centos7

RUN yum install -y docker

RUN curl "https://bootstrap.pypa.io/get-pip.py" -o "get-pip.py"
RUN python get-pip.py

RUN pip install docker-py

ADD ./ /app/
WORKDIR /app

CMD ./monitor_agent.py
