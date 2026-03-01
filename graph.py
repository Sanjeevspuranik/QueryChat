import os
import pandas as pd
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent

from langgraph.graph import StateGraph, END
from typing import TypedDict

load_dotenv()

# =========================
# Environment
# =========================
DATABASE_URL = os.getenv("DATABASE_URL")
MODEL = os.getenv("MODEL")

# =========================
# LLM + DB
# =========================
llm = ChatOpenAI(model=MODEL, temperature=0)  # type: ignore

db = SQLDatabase.from_uri(DATABASE_URL)  # type: ignore

sql_agent = create_sql_agent(
    llm=llm,
    db=db,
    verbose=True,
    return_intermediate_steps=True,
    handle_parsing_errors=True
)


# =========================
# Graph State
# =========================


class GraphState(TypedDict):
    question: str
    sql_query: str
    answer: str
    dataframe: pd.DataFrame


# =========================
# Node 1 — Generate SQL
# =========================
def generate_sql(state: GraphState):

    try:
        result = sql_agent.invoke({"input": state["question"]})

        answer_text = result["output"]

        # Extract SQL from intermediate steps safely
        sql_query = ""

        steps = result.get("intermediate_steps", [])

        for action, observation in steps:
            if hasattr(action, "tool") and action.tool == "sql_db_query":
                sql_query = action.tool_input

        return {
            "sql_query": sql_query,
            "answer": answer_text,
        }

    except Exception as e:
        return {
            "sql_query": "",
            "answer": f"Error: {str(e)}"
        }


# =========================
# Node 2 — Execute SQL
# =========================
def execute_sql(state: GraphState):

    sql_query = state.get("sql_query", "")

    if not sql_query:
        return {
            "dataframe": pd.DataFrame()
        }

    try:
        df = pd.read_sql(sql_query, db._engine)
    except Exception:
        df = pd.DataFrame()

    return {
        "dataframe": df
    }


# =========================
# Build Graph
# =========================
def build_graph():

    builder = StateGraph(GraphState)

    builder.add_node("generate_sql", generate_sql)
    builder.add_node("execute_sql", execute_sql)

    builder.set_entry_point("generate_sql")
    builder.add_edge("generate_sql", "execute_sql")
    builder.add_edge("execute_sql", END)

    return builder.compile()
