from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .nodes import (
    approval_agent_node,
    due_date_agent_node,
    email_agent_node,
    invoice_agent_node,
    payment_agent_node,
    reminder_agent_node,
    route_after_due_date,
    route_after_email,
    route_after_invoice,
    route_after_reminder,
)
from .state import InvoiceIntelligenceState, WorkflowServicesContext


def create_memory() -> InMemorySaver:
    """Create the default in-memory LangGraph checkpoint store."""

    return InMemorySaver()


def build_invoice_intelligence_graph() -> StateGraph:
    """
    Build the LangGraph StateGraph for the Invoice Intelligence workflow.

    Agents:
    - Email Agent
    - Invoice Agent
    - Payment Agent
    - Due Date Agent
    - Reminder Agent
    - Approval Agent
    """

    graph = StateGraph(InvoiceIntelligenceState, context_schema=WorkflowServicesContext)

    graph.add_node("email_agent", email_agent_node)
    graph.add_node("invoice_agent", invoice_agent_node)
    graph.add_node("payment_agent", payment_agent_node)
    graph.add_node("due_date_agent", due_date_agent_node)
    graph.add_node("reminder_agent", reminder_agent_node)
    graph.add_node("approval_agent", approval_agent_node)

    graph.add_edge(START, "email_agent")
    graph.add_conditional_edges(
        "email_agent",
        route_after_email,
        {
            "invoice_agent": "invoice_agent",
            "payment_agent": "payment_agent",
            "due_date_agent": "due_date_agent",
        },
    )
    graph.add_conditional_edges(
        "invoice_agent",
        route_after_invoice,
        {
            "payment_agent": "payment_agent",
            "due_date_agent": "due_date_agent",
        },
    )
    graph.add_edge("payment_agent", "due_date_agent")
    graph.add_conditional_edges(
        "due_date_agent",
        route_after_due_date,
        {
            "reminder_agent": "reminder_agent",
            "approval_agent": "approval_agent",
            "__end__": END,
        },
    )
    graph.add_conditional_edges(
        "reminder_agent",
        route_after_reminder,
        {
            "approval_agent": "approval_agent",
            "__end__": END,
        },
    )
    graph.add_edge("approval_agent", END)

    return graph


def compile_invoice_intelligence_graph(*, checkpointer: InMemorySaver | None = None):
    """Compile the LangGraph workflow with checkpointed memory."""

    memory = checkpointer or create_memory()
    return build_invoice_intelligence_graph().compile(checkpointer=memory)
