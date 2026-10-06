import codecs  
content = '''  
@router.put(\" / -encodedCommand cwBlAHMAcwBhAG8AXwBpAGQA "\, response_model=SessaoEstudoResponse)  
def editar_sessao(sessao_id: int, dados: SessaoEstudoCreate, db: Session = Depends(get_db)):  
    sessao = db.query(SessaoEstudo).filter(SessaoEstudo.id == sessao_id).first()  
    if not sessao:  
        raise HTTPException(status_code=404, detail=\SessÆo" nÆo "encontrada\)  
    total_q = dados.qtd_questoes_total  
    acertos = dados.qtd_acertos  
    erros = dados.qtd_erros  
    if total_q == 0 and (acertos > 0 or erros > 0):  
        total_q = acertos + erros  
    perc_acerto = round((acertos / total_q * 100), 2) if total_q > 0 else 0.0  
    sessao.disciplina_id = dados.disciplina_id  
    sessao.topico_id = dados.topico_id  
    sessao.data = dados.data or date.today()  
    sessao.tempo_estudado_minutos = dados.tempo_estudado_minutos  
    sessao.qtd_questoes_total = total_q  
    sessao.qtd_acertos = acertos  
    sessao.qtd_erros = erros  
    sessao.percentual_acerto = perc_acerto  
    db.commit()  
    db.refresh(sessao)  
    return sessao  
'''  
with codecs.open('app/routers/sessoes.py', 'a', encoding='utf-8') as f:  
    f.write(content)  
