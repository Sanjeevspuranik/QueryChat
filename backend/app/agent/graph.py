from langgraph.graph import END, StateGraph

from app.agent.nodes import AgentNodes
from app.agent.state import AgentState

# Each cycle is bounded by retry_gate (max_retries); this is only a backstop.
RECURSION_LIMIT = 60


def build_agent_graph(nodes: AgentNodes):
    """load_schema -> generate -> validate -> execute -> summarize, with a
    bounded correction loop: any retryable failure passes retry_gate back to generate."""
    graph = StateGraph(AgentState)
    graph.add_node("load_schema", nodes.load_schema)
    graph.add_node("generate", nodes.generate)
    graph.add_node("validate", nodes.validate)
    graph.add_node("execute", nodes.execute)
    graph.add_node("retry_gate", nodes.retry_gate)
    graph.add_node("summarize", nodes.summarize)
    graph.add_node("fail", nodes.fail)

    graph.set_entry_point("load_schema")
    graph.add_conditional_edges("load_schema", nodes.route_after_schema, ["generate", "fail"])
    graph.add_edge("generate", "validate")
    graph.add_conditional_edges("validate", nodes.route_after_validate, ["execute", "retry_gate"])
    graph.add_conditional_edges("execute", nodes.route_after_execute, ["summarize", "retry_gate"])
    graph.add_conditional_edges("retry_gate", nodes.route_after_gate, ["generate", "fail"])
    graph.add_edge("summarize", END)
    graph.add_edge("fail", END)
    return graph.compile()
