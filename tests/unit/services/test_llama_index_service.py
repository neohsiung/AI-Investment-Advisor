"""
Tests for LlamaIndexService (src/services/llama_index_service.py).
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from llama_index.core import Document
from src.services.llama_index_service import LlamaIndexService


@pytest.fixture
def mock_llama_components():
    with patch("src.services.llama_index_service.OllamaEmbedding") as mock_embed, \
         patch("src.services.llama_index_service.Ollama") as mock_llm, \
         patch("src.services.llama_index_service.PDFReader") as mock_pdf, \
         patch("src.services.llama_index_service.RssNewsReader") as mock_rss, \
         patch("llama_index.core.settings.resolve_embed_model") as mock_resolve_embed, \
         patch("llama_index.core.settings.resolve_llm") as mock_resolve_llm:
        
        mock_resolve_embed.side_effect = lambda x, *args, **kwargs: x
        mock_resolve_llm.side_effect = lambda x, *args, **kwargs: x
        
        yield {
            "embed": mock_embed,
            "llm": mock_llm,
            "pdf": mock_pdf,
            "rss": mock_rss
        }


def test_init(mock_llama_components):
    service = LlamaIndexService(
        db_connection_string="postgresql+psycopg2://u:p@localhost:5432/db",
        embed_model_name="test-model",
        ollama_base_url="http://localhost:11434"
    )
    assert service._connection_string == "postgresql+psycopg2://u:p@localhost:5432/db"
    mock_llama_components["embed"].assert_called_once()
    mock_llama_components["llm"].assert_called_once()


def test_default_db_url(mock_llama_components):
    with patch.dict("os.environ", {"PGHOST": "test-host", "PGPORT": "9999", "PGDATABASE": "test-db", "DB_USER": "u", "DB_PASS": "p"}):
        url = LlamaIndexService._default_db_url()
        assert url == "postgresql+psycopg2://u:p@test-host:9999/test-db"


def test_ensure_vector_store(mock_llama_components):
    service = LlamaIndexService(
        db_connection_string="postgresql+psycopg2://u:p@localhost:5432/db"
    )
    mock_pg = MagicMock()
    with patch("src.services.llama_index_service.PGVectorStore.from_params", return_value=mock_pg) as mock_from_params:
        store = service._ensure_vector_store("test_table")
        assert store == mock_pg
        mock_from_params.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_pdf(mock_llama_components):
    service = LlamaIndexService(
        db_connection_string="postgresql+psycopg2://u:p@localhost:5432/db"
    )
    service._ensure_vector_store = MagicMock()
    
    mock_doc = Document(text="test pdf content", metadata={})
    mock_llama_components["pdf"].return_value.load_data.return_value = [mock_doc]
    
    mock_index = MagicMock()
    
    with patch("src.services.llama_index_service.VectorStoreIndex", return_value=mock_index), \
         patch("os.path.exists", return_value=True):
        res = await service.ingest_pdf("test.pdf", "AAPL", "report", "category")
        assert res["status"] == "ok"
        assert res["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_ingest_rss(mock_llama_components):
    service = LlamaIndexService(
        db_connection_string="postgresql+psycopg2://u:p@localhost:5432/db"
    )
    service._ensure_vector_store = MagicMock()
    
    mock_doc = Document(text="test rss content", metadata={})
    mock_llama_components["rss"].return_value.load_data.return_value = [mock_doc]
    
    mock_index = MagicMock()
    
    with patch("src.services.llama_index_service.VectorStoreIndex", return_value=mock_index):
        res = await service.ingest_rss(["http://rss.com"], "AAPL")
        assert res["status"] == "ok"
        assert res["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_search(mock_llama_components):
    service = LlamaIndexService(
        db_connection_string="postgresql+psycopg2://u:p@localhost:5432/db"
    )
    service._ensure_vector_store = MagicMock()
    
    mock_index = MagicMock()
    mock_query_engine = MagicMock()
    mock_response = MagicMock()
    mock_node = MagicMock()
    mock_node.node.get_content.return_value = "source chunk"
    mock_node.node.metadata = {"ticker": "AAPL"}
    mock_node.score = 0.9
    mock_response.source_nodes = [mock_node]
    
    mock_query_engine.query.return_value = mock_response
    mock_index.as_query_engine.return_value = mock_query_engine
    
    with patch("src.services.llama_index_service.VectorStoreIndex", return_value=mock_index):
        res = await service.search("query text")
        assert isinstance(res, list)
        assert len(res) == 1
        assert res[0]["content"] == "source chunk"
        assert res[0]["metadata"]["ticker"] == "AAPL"
        assert res[0]["score"] == 0.9


@pytest.mark.asyncio
async def test_search_by_ticker(mock_llama_components):
    service = LlamaIndexService(
        db_connection_string="postgresql+psycopg2://u:p@localhost:5432/db"
    )
    mock_results = [{"content": "result", "metadata": {"ticker": "AAPL"}, "score": 0.8}]
    service.search = AsyncMock(return_value=mock_results)
    res = await service.search_by_ticker("AAPL", "earnings query")
    assert res == mock_results
    service.search.assert_called_once_with(
        query="earnings query",
        metadata_filters={"ticker": "AAPL"},
        top_k=3
    )


@pytest.mark.asyncio
async def test_get_index_stats(mock_llama_components):
    service = LlamaIndexService(
        db_connection_string="postgresql+psycopg2://u:p@localhost:5432/db"
    )
    
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = (10,)
    
    with patch("sqlalchemy.create_engine") as mock_create_engine:
        mock_create_engine.return_value.connect.return_value.__enter__.return_value = mock_conn
        stats = await service.get_index_stats("llama_index_vectors")
        assert stats["document_count"] == 10
        assert stats["table"] == "llama_index_vectors"


@pytest.mark.asyncio
async def test_delete_old_entries(mock_llama_components):
    service = LlamaIndexService(
        db_connection_string="postgresql+psycopg2://u:p@localhost:5432/db"
    )
    mock_conn = MagicMock()
    mock_conn.execute.return_value.rowcount = 5
    with patch("sqlalchemy.create_engine") as mock_create_engine:
        mock_create_engine.return_value.begin.return_value.__enter__.return_value = mock_conn
        res = await service.delete_old_entries(days=30, table_name="llama_index_vectors")
        assert res == 5


def test_rss_news_reader_custom():
    from src.services.llama_index_service import RssNewsReader
    from unittest.mock import patch, MagicMock

    reader = RssNewsReader(text_mode=True)
    assert reader.reader_kwargs == {"text_mode": True}

    mock_feed = MagicMock()
    mock_entry = MagicMock()
    mock_entry.get.return_value = "http://article.com"
    mock_feed.entries = [mock_entry]

    mock_article = MagicMock()
    mock_article.title = "Test Article"
    mock_article.text = "Article body text"
    mock_article.authors = ["Author"]
    mock_article.meta_lang = "en"
    mock_article.meta_description = "Desc"
    mock_article.publish_date = "2026-06-21"

    with patch("feedparser.parse", return_value=mock_feed) as mock_parse, \
         patch("newspaper.Article", return_value=mock_article) as mock_article_cls:
        
        # Test list of URLs
        docs = reader.load_data(["http://rss.com"])
        assert len(docs) == 1
        assert docs[0].text == "Article body text"
        assert docs[0].metadata["title"] == "Test Article"
        assert docs[0].metadata["link"] == "http://article.com"
        assert docs[0].metadata["feed"] == "http://rss.com"

        # Test single string URL
        docs_str = reader.load_data("http://rss.com")
        assert len(docs_str) == 1
        assert docs_str[0].text == "Article body text"

        # Test feedparser exception handling
        mock_parse.side_effect = Exception("Feed parse failed")
        docs_err = reader.load_data("http://rss.com")
        assert len(docs_err) == 0

        # Test article download/parse exception handling
        mock_parse.side_effect = None
        mock_article_cls.side_effect = Exception("Article download failed")
        docs_err2 = reader.load_data("http://rss.com")
        assert len(docs_err2) == 0

