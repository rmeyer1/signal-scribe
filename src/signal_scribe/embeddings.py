from openai import AsyncOpenAI

from signal_scribe.config import Settings
from signal_scribe.schemas import FilingSection


class EmbeddingService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_enabled else None

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self._client:
            return []

        response = await self._client.embeddings.create(
            model=self._settings.openai_embedding_model,
            input=texts,
            encoding_format="float",
            dimensions=self._settings.embedding_dimensions,
        )
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]

    async def embed_sections(self, sections: list[FilingSection]) -> list[FilingSection]:
        embeddings = await self.embed_texts([section.section_text for section in sections])
        for section, embedding in zip(sections, embeddings, strict=False):
            section.embedding = embedding
        return sections

    async def embed_query(self, query: str) -> list[float] | None:
        embeddings = await self.embed_texts([query])
        return embeddings[0] if embeddings else None


def vector_to_sql(value: list[float]) -> str:
    return "[" + ",".join(f"{item:.10g}" for item in value) + "]"
