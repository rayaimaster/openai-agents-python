"""Internal "ask-our-docs" knowledge agent (UC1 from SDK_ADOPTION_PLAN.md).

Single agent that answers questions from an OpenAI vector store first and
falls back to web search when the indexed docs do not cover the question.
Returns a structured ``AnswerWithCitations`` so downstream UIs can render
sources reliably, and persists conversation turns in a ``SQLiteSession``.

Run it with:

    python -m examples.doc_qa_agent.main

Set ``DOC_QA_VECTOR_STORE_ID`` to reuse an existing vector store; otherwise
a throwaway store with a single demo document is created on first run.
"""

from __future__ import annotations as _annotations

import asyncio
import os
import uuid
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel

from agents import (
    Agent,
    FileSearchTool,
    Runner,
    SQLiteSession,
    WebSearchTool,
    trace,
)
from examples.auto_mode import input_with_fallback, is_auto_mode

### OUTPUT TYPE


class Citation(BaseModel):
    source_type: Literal["file", "web"]
    title: str
    locator: str
    """URL for web sources, file id for vector store sources."""
    quote: str
    """A short supporting snippet from the source; may be empty."""


class AnswerWithCitations(BaseModel):
    answer: str
    citations: list[Citation]
    confidence: Literal["high", "medium", "low"]
    used_web_fallback: bool


### VECTOR STORE SETUP

DEMO_DOC = (
    "Arrakis, the desert planet in Frank Herbert's 'Dune,' was inspired "
    "by the scarcity of water as a metaphor for oil and other finite resources."
)


def ensure_vector_store() -> str:
    """Return a vector store id, creating a throwaway demo one if unset."""
    existing = os.environ.get("DOC_QA_VECTOR_STORE_ID")
    if existing:
        return existing

    print("No DOC_QA_VECTOR_STORE_ID set; creating a demo vector store with a single doc.")
    client = OpenAI()
    file_upload = client.files.create(
        file=("doc_qa_demo.txt", DEMO_DOC.encode("utf-8")),
        purpose="assistants",
    )
    vector_store = client.vector_stores.create(name="doc-qa-agent-demo")
    client.vector_stores.files.create_and_poll(
        vector_store_id=vector_store.id,
        file_id=file_upload.id,
    )
    print(f"Created vector store {vector_store.id} with file {file_upload.id}.")
    return vector_store.id


### AGENT

INSTRUCTIONS = """You are an internal knowledge assistant.

Follow this routine on every user question:
1. Call file_search first against the indexed knowledge base.
2. If file_search returns no relevant results, or the user explicitly asks
   for fresh information, call web_search as a fallback.
3. Answer the user. Populate `citations` with every source you actually
   used: file sources use source_type="file" with the file id as locator,
   web sources use source_type="web" with the URL as locator.
4. Set `used_web_fallback` to true only if you called web_search.
5. Set `confidence` based on how well the cited sources support the answer.
6. If neither tool returns anything useful, return an empty citations list,
   confidence="low", and say so plainly in `answer`.
"""


def build_agent(vector_store_id: str) -> Agent:
    return Agent(
        name="Doc QA Agent",
        instructions=INSTRUCTIONS,
        tools=[
            FileSearchTool(
                max_num_results=5,
                vector_store_ids=[vector_store_id],
                include_search_results=True,
            ),
            WebSearchTool(),
        ],
        output_type=AnswerWithCitations,
    )


### RUN


def _print_answer(answer: AnswerWithCitations) -> None:
    print(f"\nAnswer (confidence={answer.confidence}, web_fallback={answer.used_web_fallback}):")
    print(answer.answer)
    if answer.citations:
        print("\nCitations:")
        for i, c in enumerate(answer.citations, 1):
            print(f"  {i}. [{c.source_type}] {c.title} - {c.locator}")
            if c.quote:
                print(f"     > {c.quote}")
    else:
        print("\nNo citations.")
    print()


async def main() -> None:
    vector_store_id = ensure_vector_store()
    agent = build_agent(vector_store_id)
    session = SQLiteSession(f"doc-qa-{uuid.uuid4().hex[:8]}")
    auto_mode = is_auto_mode()
    group_id = uuid.uuid4().hex[:16]

    while True:
        user_input = input_with_fallback(
            "Ask a question (ctrl-c to exit): ",
            "Tell me one thing about Arrakis I might not know.",
        )
        with trace("Doc QA Agent", group_id=group_id):
            result = await Runner.run(agent, user_input, session=session)
        _print_answer(result.final_output)
        if auto_mode:
            break


if __name__ == "__main__":
    asyncio.run(main())
