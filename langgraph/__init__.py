"""
Local langgraph compatibility shim.

The installed langgraph (1.2.6) + langgraph_sdk (0.4.2) fails to import
because langgraph_sdk requires langchain_core.language_models.chat_model_stream
which does not exist in langchain_core 0.3.86.

This local stub provides ONLY what agent/state/state.py needs:
    from langgraph.graph.message import add_messages

The investigation graph is implemented as a pure Python state machine in
agent/graph/workflow.py — functionally equivalent, no broken deps.
"""
