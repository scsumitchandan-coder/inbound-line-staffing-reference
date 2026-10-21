# AGENT image: the planning team's notes, the queue engine (built here) and one practice line.
# The practice line's records are produced in a builder stage; only the three record files reach the image.
FROM python:3.13-slim-bookworm@sha256:2325bb286ec344af3e5898cc224b5844e2707ac6e26b1632516fd3edc84a5e26 AS records
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy==2.3.3 pandas==2.3.2 scipy==1.16.2
COPY _build /build
RUN gcc -O2 -o /build/gensim /build/gensim.c -lm \
 && cd /build && GENSIM=/build/gensim python3 centre.py 424242 /build/practice --no-truth --role=steady > /dev/null

FROM python:3.13-slim-bookworm@sha256:2325bb286ec344af3e5898cc224b5844e2707ac6e26b1632516fd3edc84a5e26
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy==2.3.3 pandas==2.3.2 scipy==1.16.2
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
WORKDIR /app
COPY app /app
RUN gcc -O2 -o /app/engine/qplan /app/engine/qplan.c -lm
COPY --from=records /build/practice/case.json /build/practice/calls.csv /build/practice/agents.csv /app/practice/
