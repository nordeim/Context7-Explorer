# File: src/cli.py
"""
CLI module for the Context7 Agent.

Provides a re-imagined, immersive terminal interface with split-screen layout,
live streaming, advanced animations, and enhanced interactivity with a scrollable chat panel.
"""

import os
import sys
from typing import AsyncGenerator, Dict

import anyio
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import Context7Agent
from themes import THEMES, ASCII_ART, get_theme_styles

console = Console()


class CLI:
    def __init__(self):
        self.agent = Context7Agent()
        self.conversation = []
        self.current_theme = "cyberpunk"
        self.styles = get_theme_styles(self.current_theme)
        self.results = []
        self.bookmarks = self.agent.history.get_bookmarks()
        self.status = "Ready"
        # CRITICAL FIX: Add state for scrolling chat history
        self.chat_scroll_offset = 0
        
        self.session_state = self.agent.history.load_session()
        if self.session_state:
            self.conversation = self.session_state.get("conversation", [])
            self.agent.history.data["conversations"] = self.conversation
            self.current_theme = self.session_state.get("theme", "cyberpunk")
            self.styles = get_theme_styles(self.current_theme)
            self.scroll_to_bottom() # Start at the end of loaded history

    def scroll_to_bottom(self):
        """Helper to reset scroll to the latest messages."""
        self.chat_scroll_offset = 0

    def make_layout(self) -> Layout:
        """Create dynamic split-screen layout."""
        layout = Layout(name="root")
        layout.split_column(
            Layout(name="header", size=9),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3),
        )
        layout["main"].split_row(Layout(name="chat", ratio=3), Layout(name="sidebar", ratio=1))
        return layout

    def update_layout(self, layout: Layout):
        """Populates all panels in the layout with current data."""
        art = Text.from_markup(ASCII_ART.get(self.current_theme, ""), justify="center")
        layout["header"].update(Panel(art, style=self.styles["header"]))
        
        # CRITICAL FIX: Implement scrolling logic for the chat panel
        # Estimate visible lines based on terminal height, leaving room for panels/prompts
        visible_chat_lines = max(5, console.height - 15)
        
        chat_history = Text()
        # Calculate the slice of conversation to show based on scroll offset
        start_index = len(self.conversation) - visible_chat_lines - self.chat_scroll_offset
        end_index = len(self.conversation) - self.chat_scroll_offset
        start_index = max(0, start_index)
        
        for msg in self.conversation[start_index:end_index]:
            style = self.styles["chat_user"] if msg["role"] == "user" else self.styles["chat_agent"]
            chat_history.append(f"{msg['role'].capitalize()}: ", style=f"bold {style}")
            chat_history.append(f"{msg['content']}\n")
        
        chat_title = "Chat"
        if self.chat_scroll_offset > 0:
            chat_title = f"Chat (scrolled up {self.chat_scroll_offset} lines)"
        layout["chat"].update(Panel(chat_history, title=chat_title, style=self.styles["panel"]))

        sidebar = Layout(name="sidebar")
        sidebar.split_column(Layout(name="results", ratio=1), Layout(name="bookmarks", ratio=1))
        results_table = Table(title="Search Results", style=self.styles["result"], expand=True)
        results_table.add_column("ID", width=4)
        results_table.add_column("Title")
        for res in self.results:
            results_table.add_row(str(res["id"]), res["title"])
        sidebar["results"].update(Panel(results_table, title="Search Results", style=self.styles["panel"]))
        bookmarks_text = Text()
        for doc in self.bookmarks[-10:]:
            bookmarks_text.append(f"{doc['id']}: {doc['title']}\n")
        sidebar["bookmarks"].update(Panel(bookmarks_text, title="Bookmarks", style=self.styles["panel"]))
        layout["sidebar"].update(sidebar)

        hotkeys = "Hotkeys: /history up|down, /preview <id>, /theme <name>, /exit"
        footer_text = f"{hotkeys}\nStatus: {self.status}"
        layout["footer"].update(Panel(footer_text, style=self.styles["footer"]))

    async def run_particle_loader(self, layout: Layout, text: str = "Processing..."):
        """A reusable loader to show processing activity."""
        self.scroll_to_bottom() # Ensure we're at the bottom before loading
        with Live(layout, console=console, refresh_per_second=10, vertical_overflow="visible") as live:
            progress = Progress(SpinnerColumn(), TextColumn(f"[progress.description]{text}"), transient=True)
            task = progress.add_task(self.styles["particle"], total=None)
            original_panel = layout["chat"].renderable
            layout["chat"].update(Panel(progress, title="Chat", style=self.styles["panel"]))
            live.refresh()
            await anyio.sleep(1.5)
            layout["chat"].update(original_panel)

    async def run_typing_animation(self, text: str, layout: Layout):
        """Typing animation that uses a temporary Live context."""
        self.scroll_to_bottom() # Ensure new messages are visible
        self.conversation.append({"role": "assistant", "content": ""})
        
        with Live(layout, console=console, refresh_per_second=20, vertical_overflow="visible") as live:
            current = ""
            for char in text:
                current += char
                self.conversation[-1]["content"] = current
                self.update_layout(layout)
                live.refresh()
                await anyio.sleep(0.02)
        
        self.agent.history.data["conversations"] = self.conversation


    async def run(self):
        """Main async execution loop."""
        layout = self.make_layout()
        console.clear()
        await self.run_typing_animation("Welcome! I am your Context7 agent. How can I help?", layout)

        async with self.agent.agent.run_mcp_servers():
            while True:
                self.status = "Ready"
                self.update_layout(layout)
                console.clear()
                console.print(layout)

                try:
                    user_input = await anyio.to_thread.run_sync(
                        lambda: Prompt.ask("[bold]You > [/]", console=console)
                    )

                    if user_input.lower() == "/exit":
                        break
                    
                    self.scroll_to_bottom()
                    self.conversation.append({"role": "user", "content": user_input})
                    self.agent.history.data["conversations"] = self.conversation
                    self.status = "Processing..."
                    self.update_layout(layout)
                    console.clear()
                    console.print(layout)
                    
                    if user_input.startswith("/"):
                        # CRITICAL FIX: Add history/scrolling commands
                        if user_input.lower() in ("/history up", "/h up"):
                            self.chat_scroll_offset = min(len(self.conversation) - 1, self.chat_scroll_offset + 5)
                            self.status = "Scrolled up."
                        elif user_input.lower() in ("/history down", "/h down"):
                            self.chat_scroll_offset = max(0, self.chat_scroll_offset - 5)
                            self.status = "Scrolled down."
                        elif user_input.lower() in ("/history top", "/h top"):
                            self.chat_scroll_offset = len(self.conversation) - 1
                            self.status = "Scrolled to top."
                        elif user_input.startswith("/preview"):
                            doc_id = int(user_input.split()[-1])
                            preview = self.agent.preview_document(doc_id)
                            await self.run_typing_animation(preview, layout)
                        elif user_input.startswith("/theme"):
                            theme = user_input.split()[-1]
                            if theme in THEMES:
                                self.current_theme = theme
                                self.styles = get_theme_styles(theme)
                                self.status = f"Theme switched to {theme}!"
                        elif user_input.startswith("/bookmark"):
                            self.status = self.agent.handle_command(user_input)
                            self.bookmarks = self.agent.history.get_bookmarks()
                        else:
                            response = self.agent.handle_command(user_input)
                            await self.run_typing_animation(response, layout)
                        continue
                    
                    await self.run_particle_loader(layout)
                    
                    response_data = await self.agent.generate_response(user_input, self.conversation)

                    if isinstance(response_data, str):
                        await self.run_typing_animation(response_data, layout)
                    elif isinstance(response_data, dict) and response_data.get("type") == "search":
                        self.results = []
                        with Live(layout, console=console, refresh_per_second=10, vertical_overflow="visible") as live:
                            async for item in response_data["streamer"]:
                                self.results.append(item)
                                self.update_layout(layout)
                                live.refresh()

                        summary = f"Results streamed into the sidebar. Use /preview <id> for details."
                        self.conversation.append({"role": "assistant", "content": summary})
                        self.agent.history.data["conversations"] = self.conversation
                        self.update_layout(layout)
                        console.clear()
                        console.print(layout)

                        await self.run_particle_loader(layout, "Generating recommendation...")
                        recommendation = await response_data["recommender"]
                        await self.run_typing_animation(recommendation, layout)
                    else:
                        self.status = "Error: Unexpected response type."

                except Exception as e:
                    self.status = f"Error: {str(e)}"

        state = {"conversation": self.conversation, "theme": self.current_theme}
        self.agent.history.save_session(state)
        console.print("[green]Session saved. Goodbye![/green]")

if __name__ == "__main__":
    try:
        anyio.run(CLI().run)
    except KeyboardInterrupt:
        console.print("\n[yellow]User interrupted. Exiting gracefully.[/yellow]")
    except Exception as e:
        console.print(f"\n[bold red]An unexpected application error occurred:[/bold red]\n{e}")
