# File: src/agent.py
"""
Agent module for the Context7 Agent.

This module implements a Pydantic AI agent with Context7 MCP server integration.
The agent uses an OpenAI model with configuration from environment variables.
"""

import os
import sys
from typing import Dict, Any, Optional, List, Union

from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.models.openai import OpenAIModel as OpenAI_LLM
from pydantic_ai.providers.openai import OpenAIProvider
import openai

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from history import History


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

        Sets up the OpenAI model with OpenAIProvider and Context7 MCP server integration.
        """
        error = config.validate()
        if error:
            raise ValueError(error)

        # The provider is needed for its synchronous client and for the Agent.
        self.provider = OpenAIProvider(
            api_key=config.openai_api_key,
            base_url=config.openai_base_url,
        )
        
        # We need a separate, dedicated async client for our async methods.
        self.async_client = openai.AsyncOpenAI(
            api_key=config.openai_api_key,
            base_url=config.openai_base_url,
        )

        self.llm = OpenAI_LLM(
            model_name=config.openai_model,
            provider=self.provider
        )

        self.mcp_server = MCPServerStdio(**config.mcp_config["mcpServers"]["context7"])
        self.agent = Agent(model=self.llm, mcp_servers=[self.mcp_server])
        self.history = History()

    def detect_intent(self, message: str) -> str:
        """Detect if the message intends a search or command."""
        if "/search" in message or any(
            keyword in message.lower()
            for keyword in ["tell me about", "find docs on", "search for"]
        ):
            return "search"
        elif message.startswith("/"):
            return "command"
        return "chat"

    def query_mcp(self, query: str, filters: Optional[Dict] = None) -> List[Dict]:
        """Query the Context7 MCP server for documents. (Mocked for demo; integrate real MCP calls.)"""
        mock_results = [
            {
                "id": 1,
                "title": f"Doc on {query}",
                "content": "Sample content...",
                "tags": ["ai"],
                "date": "2025-07-13",
            },
            {
                "id": 2,
                "title": f"Related to {query}",
                "content": "More info...",
                "tags": ["ethics"],
                "date": "2025-07-12",
            },
        ]
        self.history.add_search(query, mock_results)
        return mock_results

    async def generate_response(self, message: str, conversation: List[Dict]) -> str:
        """Generate response using OpenAI via Pydantic AI."""
        intent = self.detect_intent(message)
        if intent == "search":
            search_query = (
                message.split("about")[-1].strip() if "about" in message else message
            )
            results = self.query_mcp(search_query)
            summary = f"Found {len(results)} docs: " + ", ".join(
                r["title"] for r in results
            )
            prompt = f"Summarize these search results for the user: {summary}"
            # Access the synchronous client via the stored provider instance.
            response = self.provider.client.chat.completions.create(
                model=config.openai_model,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content + "\nUse /preview <id> to view."
        elif intent == "command":
            return self.handle_command(message)
        else:
            # Use our dedicated async client for the chat functionality.
            raw_msgs = conversation + [{"role": "user", "content": message}]
            response = await self.async_client.chat.completions.create(
                model=config.openai_model,
                messages=raw_msgs,
            )
            return response.choices[0].message.content

    def handle_command(self, command: str) -> str:
        """Handle hotkey commands."""
        if command == "/help":
            return "Commands: /search <query>, /preview <id>, /bookmark <id>, /theme <name>, /analytics, /exit"
        # Add more handlers...
        return "Unknown command."

    def preview_document(self, doc_id: int) -> str:
        """Syntax-highlighted preview (simple text for now)."""
        docs = (
            self.history.get_searches()[-1]["results"]
            if self.history.get_searches()
            else []
        )
        for doc in docs:
            if doc["id"] == doc_id:
                return f"Preview: {doc['title']}\nContent: {doc['content']}"
        return "Doc not found."

    # Note: MCPServerStdio lifecycle is managed by agent.run_mcp_servers(); no manual cleanup needed.
