# VERIFIER image (separate mode): the line generator and its simulator, the sound planning methods, the same queue
# engine the agent has at /app/engine, pytest, and an unprivileged user to run the submitted planner.
FROM python:3.13-slim-bookworm@sha256:2325bb286ec344af3e5898cc224b5844e2707ac6e26b1632516fd3edc84a5e26
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy==2.3.3 pandas==2.3.2 scipy==1.16.2 pytest==9.1.1 pytest-json-ctrf==0.5.2
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
RUN mkdir -p /app /logs/verifier
COPY . /tests/
RUN gcc -O2 -o /tests/gensim /tests/gensim.c -lm \
 && cp -r /tests/engine /app/engine \
 && gcc -O2 -o /app/engine/qplan /app/engine/qplan.c -lm \
 && chmod -R a+rX /app \
 && useradd --no-create-home --shell /usr/sbin/nologin verifier
