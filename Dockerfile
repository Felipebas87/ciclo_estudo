# Usa uma imagem oficial leve do Python
FROM python:3.11-slim

# Define variáveis de ambiente para não criar arquivos .pyc e logs na hora
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Define o diretório de trabalho no container
WORKDIR /app

# Instala dependências do sistema necessárias para pacotes como psycopg2 ou pandas
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copia e instala as dependências do Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do código do projeto
COPY . .

# Expõe a porta 8000 para a aplicação
EXPOSE 8000

# Comando para iniciar a aplicação usando uvicorn no host 0.0.0.0
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
