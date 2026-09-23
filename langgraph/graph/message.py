"""
langgraph.graph.message compatibility shim.

Provides add_messages without importing the full broken langgraph chain.

add_messages is used in InvestigationState as the reducer for the `messages`
field (Annotated[list, add_messages]). It simply concatenates message lists.
"""
from __future__ import annotations

from typing import Any


def add_messages(left: list[Any], right: list[Any]) -> list[Any]:
    """
    Combine two message lists by appending right to left.

    This is the standard LangGraph add_messages reducer behaviour:
    new messages are appended to the existing list.
    """
    if left is None:
        left = []
    if right is None:
        right = []
    return list(left) + list(right)
