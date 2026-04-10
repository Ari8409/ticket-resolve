from langchain_openai import OpenAIEmbeddings


class TicketEmbedder:
    """Wraps LangChain OpenAIEmbeddings with a simple interface."""

    def __init__(self, model: str, api_key: str):
        self._embeddings = OpenAIEmbeddings(model=model, api_key=api_key)

    async def embed_text(self, text: str) -> list[float]:
        return await self._embeddings.aembed_query(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return await self._embeddings.aembed_documents(texts)
