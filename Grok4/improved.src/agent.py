# File: src/agent.py
"""
Agent module for the Context7 Agent.

This module implements a Pydantic AI agent with Context7 MCP server integration.
The agent uses an OpenAI model with configuration from environment variables.
"""

import os
import sys
from typing import Dict, Optional, List, Union, AsyncGenerator

import anyio
import openai
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import config
from history import History
from utils import fuzzy_match


class Context7Agent:
    """
    Context7 Agent implementation using Pydantic AI.

    This agent integrates with the Context7 MCP server for enhanced context management
    and uses an OpenAI model with OpenAIProvider as the underlying LLM provider.
    Supports intent detection, MCP searches, and conversational responses.
    """

    def __init__(self):
        """
        Initialize the Context7 Agent with configuration from environment variables.
        """
        error = config.validate()
        if error:
            raise ValueError(error)

        self.provider = OpenAIProvider(
            api_key=config.openai_api_key,
            base_url=config.openai_base_url,
        )
        self.async_client = openai.AsyncOpenAI(
            api_key=config.openai_api_key,
            base_url=config.openai_base_url,
        )
        self.llm = OpenAIModel(
            model_name=config.openai_model, provider=self.provider
        )
        self.mcp_server = MCPServerStdio(
            **config.mcp_config["mcpServers"]["context7"]
        )
        self.agent = Agent(model=self.llm, mcp_servers=[self.mcp_server])
        self.history = History()

    def detect_intent(self, message: str, context: List[Dict]) -> str:
        """Detect intent with conversation context."""
        full_context = (
            " ".join([msg["content"] for msg in context[-5:]]) + " " + message
        )
        if message.startswith("/search") or any(
            keyword in full_context.lower()
            for keyword in ["search", "find", "docs on", "tell me about"]
        ):
            return "search"
        elif message.startswith("/"):
            return "command"
        return "chat"

    # CRITICAL FIX: Separated generator from function returning a value.
    async def stream_mcp_results(
        self, query: str, filters: Optional[Dict] = None
    ) -> AsyncGenerator[Dict, None]:
        """
        Streams query results from MCP. This function ONLY yields documents.
        """
        mock_docs = [
            {"id": 1, "title": f"Doc on {query}", "content": f"This is the full content for the document about '{query}'. It contains detailed information and examples.", "tags": ["ai"], "date": "2025-07-13"},
            {"id": 2, "title": f"Advanced {query}", "content": f"This document provides a deep dive into advanced concepts related to '{query}'.", "tags": ["ethics"], "date": "2025-07-12"},
            {"id": 3, "title": f"Related to {query}", "content": f"Here is some information on topics similar to '{query}', offering broader context.", "tags": ["tech"], "date": "2025-07-11"},
        ]
        results = [doc for doc in mock_docs if fuzzy_match(query, doc["title"])]
        if filters:
            results = [d for d in results if all(d.get(k) == v for k, v in filters.items())]

        self.history.add_search(query, results)
        
        for doc in results:
            await anyio.sleep(0.5)
            yield doc

    async def get_mcp_recommendation(self, query: str) -> str:
        """
        Generates a conversational recommendation based on a query. This is a regular
        async function that can use `return` with a value.
        """
        rec_prompt = f"Based on the search for '{query}', provide a short, conversational recommendation for what to explore next. Keep it to one or two sentences."
        response = await self.async_client.chat.completions.create(
            model=config.openai_model,
            messages=[{"role": "user", "content": rec_prompt}],
        )
        return response.choices[0].message.content

    async def generate_response(
        self, message: str, conversation: List[Dict]
    ) -> Union[str, Dict]:
        """
        Processes a user message. Returns a string for chat/commands,
        or a dictionary with separated streaming/recommendation functions for search.
        """
        intent = self.detect_intent(message, conversation)
        if intent == "search":
            search_query = (
                message.split("about")[-1].strip()
                if "about" in message
                else message.replace("/search", "").strip()
            )
            # Return a dictionary containing the functions to be called by the CLI.
            return {
                "type": "search",
                "query": search_query,
                "streamer": self.stream_mcp_results(search_query),
                "recommender": self.get_mcp_recommendation(search_query)
            }
        elif intent == "command":
            return self.handle_command(message)
        else: # Chat
            raw_msgs = conversation + [{"role": "user", "content": message}]
            response = await self.async_client.chat.completions.create(
                model=config.openai_model, messages=raw_msgs
            )
            return response.choices[0].message.content

    def handle_command(self, command: str) -> str:
        """Handle hotkey commands."""
        if command == "/help":
            return "Commands: /search <query>, /preview <id>, /bookmark <id>, /theme <name>, /exit"
        elif command.startswith("/bookmark"):
            try:
                doc_id = int(command.split()[-1])
                searches = self.history.get_searches()
                if not searches:
                    return "No searches found to bookmark from."
                docs = searches[-1]["results"]
                for doc in docs:
                    if doc.get("id") == doc_id:
                        self.history.add_bookmark(doc)
                        return f"Bookmarked: {doc['title']}"
                return "Doc ID not found in the last search."
            except (ValueError, IndexError):
                return "Invalid command. Use /bookmark <id>."
        elif command == "/analytics":
            searches = self.history.get_searches()
            tags = [tag for search in searches for doc in search.get("results", []) for tag in doc.get("tags", [])]
            common = max(set(tags), key=tags.count) if tags else "None"
            return f"Search count: {len(searches)}\nMost common tag: {common}"
        return "Unknown command."

    def preview_document(self, doc_id: int) -> str:
        """Syntax-highlighted preview (using Rich markup)."""
        searches = self.history.get_searches()
        if not searches:
            return "No search history found."
        docs = searches[-1]["results"]
        for doc in docs:
            if doc.get("id") == doc_id:
                return f"[bold]{doc['title']}[/bold]\n\n[italic]{doc['content']}[/italic]"
        return "Doc not found in last search results."
