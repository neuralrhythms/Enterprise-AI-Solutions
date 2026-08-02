"""
prompts.py — Prompt templates for simple-rag-demo-v2.

Defines the RAG prompt template used by the answer generation stage.
The template instructs the LLM to answer only from the provided context,
cite section headings when available, and respond with a fallback
"I don't know" when the context is insufficient.
"""

from langchain_core.prompts import PromptTemplate

_TEMPLATE = """You are an assistant that answers questions based only on the provided context.
Cite the document section when available.
If the answer cannot be determined from the context, say "I don't know based on the provided context."

Context:
{context}

Question:
{question}

Answer:"""

RAG_PROMPT_TEMPLATE = PromptTemplate(
    input_variables=["context", "question"],
    template=_TEMPLATE,
)
