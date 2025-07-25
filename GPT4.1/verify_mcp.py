#!/usr/bin/env python3
"""
Complete verification that Context7 MCP integration works end-to-end.
*Fixed for pydantic-ai 0.4.2+ with deprecation warnings resolved*
"""
import asyncio
import logging
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio

logging.basicConfig(level=logging.INFO)

async def verify_integration():
    """Verify complete Context7 MCP integration with correct API usage."""
    print("🔍 Verifying Context7 MCP integration...")
    
    try:
        # Create MCP server exactly as working examples
        mcp_server = MCPServerStdio(
            command="npx",
            args=["-y", "@upstash/context7-mcp@latest"]
        )
        
        # Create agent with correct API pattern
        agent = Agent(
            "openai:kimi-k2-0711-preview",  # Critical: provider prefix
            mcp_servers=[mcp_server],
            system_prompt="You are a helpful assistant that uses Context7 to answer questions."
        )
        
        # Test query
        query = "strictly official pydantic-ai agent documentation on MCP tool calling for pydantic-ai release 0.42"
        
        # Execute with correct lifecycle management
        async with agent.run_mcp_servers():
            print("✅ MCP server running")
            result = await agent.run(query)
            print("✅ Query executed successfully")
            print("📋 Result:")
            # ✅ FIXED: Use .output instead of .data
            print(result.output)
            
    except Exception as e:
        print(f"❌ Error: {e}")
        print("💡 Troubleshooting:")
        print("1. Ensure Node.js 18+ is installed: node --version")
        print("2. Install Context7 MCP: npm install -g @upstash/context7-mcp@latest")
        print("3. Verify OpenAI API key is set")
        raise

if __name__ == "__main__":
    asyncio.run(verify_integration())
