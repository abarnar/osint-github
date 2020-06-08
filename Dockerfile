FROM python:alpine
LABEL maintainer="abarnar"
WORKDIR /osint-github
COPY *.py /osint-github/
COPY req.txt /osint-github/
RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r req.txt
CMD ["python","scan.py"]