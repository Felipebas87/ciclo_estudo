import uvicorn

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Iniciando Sistema de Gestão de Ciclo de Estudos...")
    print("🌐 Acesse no seu navegador: http://localhost:8000")
    print("📖 Documentação da API Swagger: http://localhost:8000/docs")
    print("=" * 60)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
