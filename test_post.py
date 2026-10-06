import requests
import json
from datetime import datetime

payload = {
    "disciplina_id": 1,
    "bloco_ciclo_id": None,
    "topico_id": None,
    "tempo_estudado_minutos": 180,
    "data": "2026-09-30",
    "qtd_questoes_total": 4,
    "qtd_acertos": 4,
    "qtd_erros": 0,
    "observacoes": "",
    "avancar_ciclo": True,
    "is_revisao_anki": False
}

try:
    r = requests.post("http://localhost:8000/api/sessoes", json=payload)
    print("Status Code:", r.status_code)
    print("Response:", r.text)
except Exception as e:
    print("Error:", e)
