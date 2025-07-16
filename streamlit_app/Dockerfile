# Usa uma imagem Python oficial e leve como base
FROM python:3.10-slim

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Copia o arquivo de dependências primeiro para otimizar o cache do Docker
COPY requirements.txt ./requirements.txt

# Instala as bibliotecas Python necessárias
RUN pip install --no-cache-dir -r requirements.txt

# Copia o resto dos arquivos da sua aplicação (app_aws.py, etc.)
COPY . .

# Expõe a porta em que o Streamlit irá rodar dentro do container
EXPOSE 8080

# O comando final e robusto para iniciar o Streamlit em um ambiente de nuvem
CMD ["streamlit", "run", "app_aws.py", "--server.port=8080", "--server.address=0.0.0.0", "--server.headless=true"]