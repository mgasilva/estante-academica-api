"""Modelos de entrada e saída; validam os dados antes de gravar no banco."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

StatusLeitura = Literal["quero_ler", "lendo", "concluido"]

EXEMPLO_LIVRO = {
    "titulo": "Livro de teste",
    "autores": "Autor de teste",
    "ano_publicacao": 2024,
    "status": "quero_ler",
    "observacoes": "Primeiro cadastro na minha estante.",
    "open_library_id": None,
}


class LivroEntrada(BaseModel):
    """No PUT, envie todos os valores que devem permanecer no cadastro."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        json_schema_extra={"example": EXEMPLO_LIVRO},
    )
    titulo: str = Field(min_length=1, max_length=300)
    autores: str = Field(default="", max_length=500)
    ano_publicacao: int | None = Field(default=None, ge=1, le=9999, strict=True)
    status: StatusLeitura = "quero_ler"
    observacoes: str = Field(default="", max_length=5000)
    open_library_id: str | None = Field(default=None, max_length=100)

    @field_validator("open_library_id", mode="before")
    @classmethod
    def normalizar_id_externo(cls, valor: object) -> object:
        """Um cadastro manual não precisa de identificador da API externa."""
        if isinstance(valor, str):
            return valor.strip() or None
        return valor


class LivroSaida(LivroEntrada):
    model_config = ConfigDict(
        json_schema_extra={"example": {"id": 1, **EXEMPLO_LIVRO}},
    )
    id: int
