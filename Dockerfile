FROM centos:centos7

### install dependencies

# yum
RUN yum install -y docker make git

# build nagios plugins
ADD ./nagios-plugins/ /usr/local/nagios-plugins/
RUN export PERL_LOCAL_LIB_ROOT="$PERL_LOCAL_LIB_ROOT:/root/perl5"; \
export PERL_MB_OPT="--install_base /root/perl5"; \
export PERL_MM_OPT="INSTALL_BASE=/root/perl5"; \
export PERL5LIB="/root/perl5/lib/perl5:$PERL5LIB"; \
export PATH="/root/perl5/bin:$PATH" \
&& cd /usr/local/nagios-plugins && make


# pip
RUN curl "https://bootstrap.pypa.io/get-pip.py" -o "get-pip.py"
RUN python get-pip.py

RUN pip install docker-py

### agent code
ADD ./ /app/
WORKDIR /app

CMD ./monitor_agent.py
