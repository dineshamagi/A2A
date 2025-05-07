import os
from typing import Any, Dict, AsyncIterable, Literal
from dotenv import load_dotenv
from pydantic import BaseModel
import mysql.connector
import pandas as pd
import logging

logger = logging.getLogger(__name__)

load_dotenv()

class ResponseFormat(BaseModel):
    status: Literal["input_required", "completed", "error"] = "input_required"
    message: str

class SQLAgent:
    SYSTEM_INSTRUCTION = (
        "You are a SQL assistant. "
        "You can only help users by running SQL queries on the database. "
        "If the user asks anything unrelated to SQL or database, tell them you can only help with SQL queries. "
        "Set response status to input_required if the query is unclear. "
        "Set response status to error if something fails. "
        "Set response status to completed if the query is answered successfully."
    )

    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(self):
        self.host = os.getenv("DB_HOST")
        self.user = os.getenv("DB_USER")
        self.password = os.getenv("DB_PASSWORD")
        self.database = os.getenv("DB_NAME")

    def invoke(self, query: str, sessionId: str) -> Dict[str, Any]:
        logger.info(f"Invoking SQLAgent with query: {query}, sessionId: {sessionId}")
        if not self._is_valid_query(query):
            return {
                "is_task_complete": False,
                "require_user_input": True,
                "content": "Only SELECT queries are allowed. Please rephrase your query."
            }
        try:
            conn = mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database
            )
            df = pd.read_sql(query, conn)
            conn.close()
            if df.empty:
                return {
                    "is_task_complete": False,
                    "require_user_input": True,
                    "content": "No results found. Please try a different query."
                }
            return {
                "is_task_complete": True,
                "require_user_input": False,
                "content": df.head(10).to_string(index=False)
            }
        except Exception as e:
            logger.error(f"SQLAgent error: {e}")
            return {
                "is_task_complete": False,
                "require_user_input": True,
                "content": f"Error: {str(e)}"
            }

    async def stream(self, query: str, sessionId: str) -> AsyncIterable[Dict[str, Any]]:
        yield self.invoke(query, sessionId)

    def _is_valid_query(self, query: str) -> bool:
        return query.strip().lower().startswith("select")
