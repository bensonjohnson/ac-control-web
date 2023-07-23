FROM python:3.10-alpine
WORKDIR /app
COPY main.py requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY index.html /app/templates/index.html
EXPOSE 8080
CMD python main.py


