import asyncio
import os
import ssl
from typing import Any, Dict, List

import certifi
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_classic.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain_tavily import TavilyCrawl, TavilyExtract, TavilyMap

from logger import (Colors, log_error, log_header, log_info, log_success,
                    log_warning)

load_dotenv()

# Configure SSL context to use certifi certificates
ssl_context = ssl.create_default_context(cafile=certifi.where())
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()


embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    show_progress_bar=False,
    chunk_size=50,
    retry_min_seconds=10,
)
 
vectorstore = PineconeVectorStore(
    index_name="langchain-doc-index", embedding=embeddings
)
tavily_extract = TavilyExtract()
tavily_map = TavilyMap(max_depth=5, max_breadth=20, max_pages=1000)
tavily_crawl = TavilyCrawl()


 

def index_documents(documents: List[Document], batch_size: int = 500):
    log_header("VECTOR STORAGE PHASE")
    log_info(f"Preparing to index {len(documents)} chunks")

    batches = [
        documents[i:i + batch_size]
        for i in range(0, len(documents), batch_size)
    ]

    successful = 0

    for i, batch in enumerate(batches, start=1):
        try:
            vectorstore.add_documents(batch)

            successful += 1
            log_success(
                f"Successfully added batch {i}/{len(batches)} "
                f"({len(batch)} documents)"
            )

        except Exception as e:
            log_error(f"Failed to add batch {i}: {e}")

    log_info(
        f"Indexing result: {successful}/{len(batches)} batches succeeded"
    )

    if successful != len(batches):
        raise RuntimeError(
            f"Indexing incomplete: {successful}/{len(batches)} batches succeeded"
        )

    log_success("All batches indexed successfully!")

def delete_previous_vectors():
    """Delete all vectors from the configured Pinecone index."""
    log_header("CLEANUP PHASE")

    try:
        vectorstore.delete(delete_all=True)
        log_success("All existing vectors deleted from Pinecone.")

    except Exception as e:
        log_error(f"Failed to delete existing vectors: {e}")
        raise
    
async def main():
    """Main async function to orchestrate the entire process."""
    log_header("DOCUMENTATION INGESTION PIPELINE")
    delete_previous_vectors()

    log_info(
        "🗺️  TavilyCrawl: Starting to crawl the documentation site",
        Colors.PURPLE,
    )
    # Crawl the documentation site

    res = tavily_crawl.invoke(
        {
            "url": "https://python.langchain.com/",
            "max_depth": 2,
            "extract_depth": "advanced",
        }
    )

    
    all_docs = []
    skipped = 0
    for item in res["results"]:
        content = item.get("raw_content")
        if not content or not content.strip():
            log_warning(f"TavilyCrawl: Skipping {item['url']} (no content extracted)")
            skipped += 1
            continue

        log_info(f"TavilyCrawl: Successfully crawled {item['url']} from documentation site")
        all_docs.append(
            Document(
                page_content=content,
                metadata={"source": item["url"]},
            )
        )

    log_info(f"Kept {len(all_docs)} documents, skipped {skipped} empty ones")

    # # Split documents into chunks
    log_header("DOCUMENT CHUNKING PHASE")
    log_info(
        f"✂️  Text Splitter: Processing {len(all_docs)} documents with 4000 chunk size and 200 overlap",
        Colors.YELLOW,
    )
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=4000, chunk_overlap=200)
    splitted_docs = text_splitter.split_documents(all_docs)
    log_success(
        f"Text Splitter: Created {len(splitted_docs)} chunks from {len(all_docs)} documents"
    )

    # Process documents asynchronously
    # await index_documents_async(splitted_docs, batch_size=500)
    index_documents(splitted_docs, batch_size=500)

    log_header("PIPELINE COMPLETE")
    log_success("🎉 Documentation ingestion pipeline finished successfully!")
    log_info("📊 Summary:", Colors.BOLD)
    log_info(f"   • Documents extracted: {len(all_docs)}")
    log_info(f"   • Chunks created: {len(splitted_docs)}")

    


if __name__ == "__main__":
   

    asyncio.run(main())
   