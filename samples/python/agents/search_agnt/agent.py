import os
from typing import Any, Dict, AsyncIterable, Literal
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.messages import AIMessage, ToolMessage
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferMemory
from pydantic import BaseModel

import httpx
import certifi

import logging
logger = logging.getLogger(__name__)




load_dotenv()

class ResponseFormat(BaseModel):
    status: Literal["input_required", "completed", "error"] = "input_required"
    message: str


class SearchAgent:
    SYSTEM_INSTRUCTION = (
        "You are a search assistant. "
        "Only use the 'tavily_search_results_json' tool to help users find answers from the web. "
        "If the user asks anything unrelated to search or web lookup, tell them you can only help with web search. "
        "Set response status to input_required if the query is unclear. "
        "Set response status to error if something fails. "
        "Set response status to completed if the query is answered successfully."
    )

    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4")
        # Initialize Tavily tool with SSL verification disabled
        client = httpx.AsyncClient(verify=certifi.where())
        self.tools = [TavilySearchResults(client=client)]
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", self.SYSTEM_INSTRUCTION),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad", optional=True)
        ])
        self.agent = create_openai_tools_agent(self.llm, self.tools, self.prompt)
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            memory=ConversationBufferMemory(memory_key="chat_history", return_messages=True,output_key="output"),
            verbose=True
        )

    def invoke(self, query: str, sessionId: str) -> Dict[str, Any]:
        print(f"[DEBUG] Invoking with query: {query}, sessionId: {sessionId}")
        logger.info("*******************************INSIDE INVOKE************************************")
        config = {"configurable": {"thread_id": sessionId}}
        result = self.agent_executor.invoke({"input": query}, config)

        print(f"[DEBUG] Agent raw result: {result}")

        logger.info("*************************RESULT*************************************")

        return self.process_response(result)

    async def stream(self, query: str, sessionId: str) -> AsyncIterable[Dict[str, Any]]:
        # logger.info(f"[DEBUG] Invoking with query: {query}, sessionId: {sessionId}")
        # logger.info("*******************************INSIDE STREAM************************************")
        # logger.info("*******************************iiiiiiiiiiiiii************************************")
        # result = self.invoke(query, sessionId)
        


        config = {"configurable": {"thread_id": sessionId}}
        input_obj = {"input": query}

        async for step in self.agent_executor.astream_events(input_obj, config=config):
            if isinstance(step, AIMessage):
                yield {
                    "is_task_complete": False,
                    "require_user_input": False,
                    "content": step.content or "Thinking...",
                }
            elif isinstance(step, ToolMessage):
                yield {
                    "is_task_complete": False,
                    "require_user_input": False,
                    "content": "Searching...",
                }

        result = await self.agent_executor.ainvoke(input_obj, config=config)
        yield self.process_response(result)

    def process_response(self, result: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("*******************************INSIDE process_response************************************")
        logger.info(f"[RESULT ] : {result}")
        logger.info("*******************************iiiiiiiiiiiiii************************************")

        if "error" in result:
            logger.info("ERROR..........................")
            return {
               
                "is_task_complete": False,
                "require_user_input": True,
                "content": f"Error: {result['error']}"
                
            }
        
        elif "output" in result:
            logger.info("OUTPUT..........................")
            return {
                
                "is_task_complete": True,
                "require_user_input": False,
                "content": result["output"]
                
            }

        else:
            logger.info("REQUIRE USER..........................")
            return {
            "is_task_complete": False,
            "require_user_input": True,
            "content": "We couldn't find an answer. Please rephrase your query."    
             }

    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]
