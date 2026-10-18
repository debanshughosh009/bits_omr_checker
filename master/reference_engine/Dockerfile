FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && pip uninstall -y opencv-python opencv-contrib-python \
 && pip install --no-cache-dir opencv-contrib-python-headless
COPY main.py pyproject.toml ./
COPY src ./src
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "main.py"]
CMD ["-i", "inputs/bits_omr", "-o", "outputs"]