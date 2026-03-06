"""
LangGraph Compatibility Shim

Provides ToolNode and tools_condition for older langgraph versions (0.2.x)
that don't have these as built-in prebuilt components.
"""

from typing import Literal, Sequence, Callable, Any, Dict, List
from langgraph.graph import END


class ToolNode:
    """
    Compatibility implementation of ToolNode for langgraph 0.2.x

    Executes tools based on tool_calls in the agent state.
    """

    def __init__(self, tools: Sequence[Callable]):
        """
        Initialize ToolNode with a list of tools

        Args:
            tools: List of tool functions
        """
        self.tools_by_name = {tool.__name__: tool for tool in tools}

    def __call__(self, state: Dict[str, Any]) -> Dict[str, List[Any]]:
        """
        Execute tools based on tool_calls in the state

        Args:
            state: Agent state containing 'messages' with tool_calls

        Returns:
            Dict with 'messages' containing tool results
        """
        from langchain_core.messages import ToolMessage, AIMessage

        messages = state.get("messages", [])
        if not messages:
            return {"messages": []}

        last_message = messages[-1]

        # Check if last message has tool calls
        if not isinstance(last_message, AIMessage) or not hasattr(last_message, 'tool_calls'):
            return {"messages": []}

        tool_calls = last_message.tool_calls or []
        if not tool_calls:
            return {"messages": []}

        # Execute each tool call
        tool_messages = []
        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("args", {})
            tool_id = tool_call.get("id")

            if tool_name not in self.tools_by_name:
                # Tool not found
                tool_messages.append(
                    ToolMessage(
                        content=f"Error: Tool '{tool_name}' not found",
                        tool_call_id=tool_id
                    )
                )
                continue

            try:
                # Execute the tool
                tool = self.tools_by_name[tool_name]
                result = tool(**tool_args)

                # Create tool message
                tool_messages.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tool_id
                    )
                )
            except Exception as e:
                # Tool execution failed
                tool_messages.append(
                    ToolMessage(
                        content=f"Error executing tool '{tool_name}': {str(e)}",
                        tool_call_id=tool_id
                    )
                )

        return {"messages": tool_messages}


def tools_condition(state: Dict[str, Any]) -> Literal["tools", "__end__"]:
    """
    Compatibility implementation of tools_condition for langgraph 0.2.x

    Determines whether to route to tools or end the conversation.

    Args:
        state: Agent state containing 'messages'

    Returns:
        "tools" if tools should be called, END if conversation should end
    """
    from langchain_core.messages import AIMessage

    messages = state.get("messages", [])
    if not messages:
        return END

    last_message = messages[-1]

    # Check if last message has tool calls
    if isinstance(last_message, AIMessage) and hasattr(last_message, 'tool_calls'):
        tool_calls = last_message.tool_calls or []
        if tool_calls:
            return "tools"

    return END
