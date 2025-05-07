#Google adk agent

import json
import random
from typing import Any, AsyncIterable, Dict, Optional
from google.adk.agents.llm_agent import LlmAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from task_manager import AgentWithTaskManager

# Local cache of created request_ids for demo purposes.
request_ids = set()


def create_request_form(date: Optional[str] = None, amount: Optional[str] = None, purpose: Optional[str] = None) -> dict[str, Any]:
  """
   Create a request form for the employee to fill out.
   
   Args:
       date (str): The date of the request. Can be an empty string.
       amount (str): The requested amount. Can be an empty string.
       purpose (str): The purpose of the request. Can be an empty string.
       
   Returns:
       dict[str, Any]: A dictionary containing the request form data.
   """
  request_id = "request_id_" + str(random.randint(1000000, 9999999))
  request_ids.add(request_id)
  return {
      "request_id": request_id,
      "date": "<transaction date>" if not date else date,
      "amount": "<transaction dollar amount>" if not amount else amount,
      "purpose": "<business justification/purpose of the transaction>" if not purpose else purpose,
  }

def return_form(
    form_request: dict[str, Any],    
    tool_context: ToolContext,
    instructions: Optional[str] = None) -> dict[str, Any]:
  """
   Returns a structured json object indicating a form to complete.
   
   Args:
       form_request (dict[str, Any]): The request form data.
       tool_context (ToolContext): The context in which the tool operates.
       instructions (str): Instructions for processing the form. Can be an empty string.       
       
   Returns:
       dict[str, Any]: A JSON dictionary for the form response.
   """  
  if isinstance(form_request, str):
    form_request = json.loads(form_request)

  tool_context.actions.skip_summarization = True
  tool_context.actions.escalate = True
  form_dict = {
      'type': 'form',
      'form': {
        'type': 'object',
        'properties': {
            'date': {
                'type': 'string',
                'format': 'date',
                'description': 'Date of expense',
                'title': 'Date',
            },
            'amount': {
                'type': 'string',
                'format': 'number',
                'description': 'Amount of expense',
                'title': 'Amount',
            },
            'purpose': {
                'type': 'string',
                'description': 'Purpose of expense',
                'title': 'Purpose',
            },
            'request_id': {
                'type': 'string',
                'description': 'Request id',
                'title': 'Request ID',
            },
        },
        'required': list(form_request.keys()),
      },
      'form_data': form_request,
      'instructions': instructions,
  }
  return json.dumps(form_dict)

def reimburse(request_id: str) -> dict[str, Any]:
  """Reimburse the amount of money to the employee for a given request_id."""
  if request_id not in request_ids:
    return {"request_id": request_id, "status": "Error: Invalid request_id."}
  return {"request_id": request_id, "status": "approved"}


class ReimbursementAgent(AgentWithTaskManager):
  """An agent that handles reimbursement requests."""

  SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

  def __init__(self):
    self._agent = self._build_agent()
    self._user_id = "remote_agent"
    self._runner = Runner(
        app_name=self._agent.name,
        agent=self._agent,
        artifact_service=InMemoryArtifactService(),
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
    )

  def get_processing_message(self) -> str:
      return "Processing the reimbursement request..."

  def _build_agent(self) -> LlmAgent:
    """Builds the LLM agent for the reimbursement agent."""
    return LlmAgent(
        model="gemini-2.0-flash-001",
        name="reimbursement_agent",
        description=(
            "This agent handles the reimbursement process for the employees"
            " given the amount and purpose of the reimbursement."
        ),
        instruction="""
    You are an agent who handles the reimbursement process for employees. Your responses should always include detailed reasoning and thorough explanations.

    When processing reimbursement requests, follow these steps with detailed explanations:

    1. Initial Request Analysis:
       - Carefully analyze the user's request
       - Explain your understanding of the request
       - Identify any missing or unclear information

    2. Form Creation:
       - When creating a request form using create_request_form(), explain:
         * Why each field is needed
         * How you determined the values for each field
         * Any assumptions you're making
       - Only provide default values if explicitly provided by the user
       - Document your reasoning for any decisions made

    3. Form Processing:
       - When receiving a filled-out form, provide a detailed analysis:
         * Verify each field's completeness
         * Explain the significance of each piece of information
         * Identify any potential issues or concerns
       - If information is missing, explain:
         * Why the missing information is critical
         * How it impacts the reimbursement process
         * What specific details are needed

    4. Reimbursement Decision:
       - When processing the reimbursement, provide a comprehensive explanation:
         * The reasoning behind your decision
         * Any factors considered
         * The implications of the decision

    Always maintain a professional tone while providing thorough, step-by-step explanations of your thought process and decisions.

    For valid reimbursement requests, you can then use reimburse() to reimburse the employee.
      * In your response, you should include the request_id and the status of the reimbursement request.

    """,
        tools=[
            create_request_form,
            reimburse,
            return_form,
        ],
    )

