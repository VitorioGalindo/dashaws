FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt ./requirements.txt

# Instala as dependências
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY app_aws.py .

# Expõe a porta que o App Runner espera
EXPOSE 8080

# Comando para iniciar
CMD ["streamlit", "run", "app_aws.py", "--server.port=8080", "--server.address=0.0.0.0"]