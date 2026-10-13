"""Disponibiliza as fixtures compartilhadas pelos cenários de teste."""
import uuid

import pytest

from oracle.auxiliares import email_unico, momento, registrar_linha_de_base

from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(autouse=True)
def linha_de_base_das_invariantes():
    """Registre as violações já existentes antes de cada cenário."""
    registrar_linha_de_base()
    yield


@pytest.fixture(scope="session")
def cliente():
    """Mantenha um cliente HTTP disponível durante toda a sessão de testes."""
    with TestClient(app) as cliente_teste:
        yield cliente_teste


@pytest.fixture
def criar_especialidade(cliente):
    """Forneça aos cenários uma forma curta de cadastrar especialidades."""
    def executar_criacao(nome=None):
        nome = nome or f"esp_{uuid.uuid4().hex[:8]}"
        resposta = cliente.post("/especialidades", json={"nome": nome})
        assert resposta.status_code == 201, resposta.text
        return resposta.json()
    return executar_criacao


@pytest.fixture
def criar_profissional(cliente):
    """Forneça aos cenários uma forma curta de cadastrar profissionais.

    O vínculo com a especialidade é conferido: sem ele, as alocações seguintes
    seriam recusadas pelo RF14, e a falha apareceria atribuída a outro
    requisito.
    """
    def executar_criacao(carga=44, ativo=True, especialidade_id=None):
        resposta = cliente.post("/profissionais", json={
            "nome": "Profissional Teste", "email": email_unico(),
            "carga_semanal": carga, "ativo": ativo})
        assert resposta.status_code == 201, resposta.text
        profissional = resposta.json()
        if especialidade_id:
            vinculo = cliente.post(
                f"/profissionais/{profissional['id']}/especialidades",
                json={"especialidade_id": especialidade_id})
            assert vinculo.status_code == 201, (
                f"vinculo de especialidade recusado (RF06): {vinculo.text}")
        return profissional
    return executar_criacao


@pytest.fixture
def criar_turno(cliente):
    """Forneça aos cenários uma forma curta de cadastrar turnos."""
    def executar_criacao(especialidade_id, dia=0, hora=8, duracao=8, cobertura=1):
        resposta = cliente.post("/turnos", json={
            "data_inicio": momento(dia, hora),
            "data_fim": momento(dia, hora + duracao),
            "especialidade_id": especialidade_id,
            "cobertura_minima": cobertura})
        assert resposta.status_code == 201, resposta.text
        return resposta.json()
    return executar_criacao


@pytest.fixture
def alocar(cliente):
    """Forneça aos cenários uma forma curta de alocar profissionais."""
    def executar_alocacao(turno_id, profissional_id):
        return cliente.post("/plantoes", json={
            "turno_id": turno_id, "profissional_id": profissional_id})
    return executar_alocacao
