FROM nvidia/cuda:10.2-cudnn8-runtime-ubuntu18.04

WORKDIR /app

COPY ./env_playground2.yml ./env_playground.yml

ENV PATH="/root/miniconda3/bin:${PATH}"
ARG PATH="/root/miniconda3/bin:${PATH}"
RUN apt-get update

RUN apt-get install -y wget git gcc libgl1-mesa-glx && \
    apt-get install -y ffmpeg libsm6 libxext6 && \
    apt-get install -y vim nodejs python-dev python-pip && \
    rm -rf /var/lib/apt/lists/*

RUN wget \
    https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh \
    && mkdir /root/.conda \
    && bash Miniconda3-latest-Linux-x86_64.sh -b \
    && rm -f Miniconda3-latest-Linux-x86_64.sh \
    && echo "source activate base" > ~/.bashrc


SHELL ["/bin/bash", "-c"]
ARG CONDA_ENV=playground
RUN conda --version \ 
    && conda env create -n ${CONDA_ENV} -f ./env_playground.yml
RUN conda activate ${CONDA_ENV} \
    && python -m spacy download en_core_web_lg


#CMD ["jupyter", "notebook", "--port=8888", "--no-browser", "--ip=0.0.0.0", "--allow-root"]


 



