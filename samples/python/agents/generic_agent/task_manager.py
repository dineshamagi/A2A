'''
Generic Request Validation:

The _validate_request method ensures that the task request contains valid output modes and, if required, valid push notification URLs.

Task Processing Logic:

The on_send_task method handles the regular task submission, invokes the agent, processes the response, and updates the task state accordingly.

The on_send_task_subscribe method handles streaming task requests, managing the streaming of updates from the agent and updating task states accordingly.

Error Handling:

Each method includes appropriate error handling, logging, and propagation of errors via JSONRPCResponse.

Push Notification Handling:

Methods such as set_push_notification_info and send_task_notification manage the configuration and sending of push notifications.

SSE (Server-Sent Events) Support:

The _run_streaming_task method handles the task's streaming, sending updates to the client via SSE as the task progresses.



'''

from typing import AsyncIterable, Union
import asyncio
import logging
import traceback

# Placeholder imports for the types and utilities (adjust based on your system's imports)
from common.types import (
    SendTaskRequest,
    TaskSendParams,
    TaskStatus,
    TaskState,
    Message,
    Artifact,
    Task,
    JSONRPCResponse,
    InternalError,
    PushNotificationConfig,
    InvalidParamsError,
    SendTaskResponse,
    SendTaskStreamingRequest,
    SendTaskStreamingResponse
)
from common.server.task_manager import InMemoryTaskManager
from common.utils.push_notification_auth import PushNotificationSenderAuth
import common.server.utils as utils

# Setup logger
logger = logging.getLogger(__name__)

class TaskManager(InMemoryTaskManager):
    def __init__(self, agent, notification_sender_auth: PushNotificationSenderAuth):
        super().__init__()
        self.agent = agent
        self.notification_sender_auth = notification_sender_auth

    def _validate_request(self, request: Union[SendTaskRequest, SendTaskStreamingRequest]) -> JSONRPCResponse | None:
        """Validates the incoming task request."""
        task_send_params: TaskSendParams = request.params

        # Check if the output modes are compatible
        if not utils.are_modalities_compatible(task_send_params.acceptedOutputModes, self.agent.SUPPORTED_CONTENT_TYPES):
            logger.warning(f"Unsupported output mode: {task_send_params.acceptedOutputModes}")
            return JSONRPCResponse(id=request.id, error=InvalidParamsError(message="Incompatible output modes"))

        # Check if the push notification URL is valid (if required)
        if task_send_params.pushNotification and not task_send_params.pushNotification.url:
            logger.warning("Push notification URL is missing")
            return JSONRPCResponse(id=request.id, error=InvalidParamsError(message="Push notification URL is missing"))

        return None

    async def _process_agent_response(self, request: SendTaskRequest, agent_response: dict) -> SendTaskResponse:
        """Process the agent's response and update the task store."""
        task_send_params: TaskSendParams = request.params
        task_id = task_send_params.id
        history_length = task_send_params.historyLength

        parts = [{"type": "text", "text": agent_response.get("content", "")}]
        artifact = None
        if agent_response.get("require_user_input"):
            task_status = TaskStatus(state=TaskState.INPUT_REQUIRED, message=Message(role="agent", parts=parts))
        else:
            task_status = TaskStatus(state=TaskState.COMPLETED)
            artifact = Artifact(parts=parts)

        # Update task store and append task history
        task = await self.update_store(task_id, task_status, None if artifact is None else [artifact])
        task_result = self.append_task_history(task, history_length)
        await self.send_task_notification(task)

        return SendTaskResponse(id=request.id, result=task_result)

    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        """Handles the regular 'send task' request."""
        validation_error = self._validate_request(request)
        if validation_error:
            return SendTaskResponse(id=request.id, error=validation_error.error)

        await self.upsert_task(request.params)
        task = await self.update_store(request.params.id, TaskStatus(state=TaskState.WORKING), None)
        await self.send_task_notification(task)

        task_send_params: TaskSendParams = request.params
        query = self._get_user_query(task_send_params)

        try:
            agent_response = self.agent.invoke(query, task_send_params.sessionId)
        except Exception as e:
            logger.error(f"Error invoking agent: {e}")
            raise ValueError(f"Error invoking agent: {e}")

        return await self._process_agent_response(request, agent_response)

    async def on_send_task_subscribe(self, request: SendTaskStreamingRequest) -> AsyncIterable[SendTaskStreamingResponse] | JSONRPCResponse:
        """Handles the streaming 'send task' request."""
        try:
            error = self._validate_request(request)
            if error:
                return error

            await self.upsert_task(request.params)
            task_send_params: TaskSendParams = request.params
            sse_event_queue = await self.setup_sse_consumer(task_send_params.id, False)
            asyncio.create_task(self._run_streaming_task(request))

            return self.dequeue_events_for_sse(request.id, task_send_params.id, sse_event_queue)
        except Exception as e:
            logger.error(f"Error in SSE stream: {e}")
            return JSONRPCResponse(id=request.id, error=InternalError(message="Error while streaming"))

    async def _run_streaming_task(self, request: SendTaskStreamingRequest):
        """Handle agent response streaming and task status updates."""
        task_send_params: TaskSendParams = request.params
        query = self._get_user_query(task_send_params)

        try:
            async for item in self.agent.stream(query, task_send_params.sessionId):
                is_task_complete = item.get("is_task_complete", False)
                require_user_input = item.get("require_user_input", False)
                message = None
                parts = [{"type": "text", "text": item.get("content", "")}]
                end_stream = False

                if not is_task_complete and not require_user_input:
                    task_state = TaskState.WORKING
                    message = Message(role="agent", parts=parts)
                elif require_user_input:
                    task_state = TaskState.INPUT_REQUIRED
                    message = Message(role="agent", parts=parts)
                    end_stream = True
                else:
                    task_state = TaskState.COMPLETED
                    artifact = Artifact(parts=parts, index=0, append=False)
                    end_stream = True

                task_status = TaskStatus(state=task_state, message=message)
                latest_task = await self.update_store(task_send_params.id, task_status, None)
                await self.send_task_notification(latest_task)

                if artifact:
                    task_artifact_update_event = TaskArtifactUpdateEvent(id=task_send_params.id, artifact=artifact)
                    await self.enqueue_events_for_sse(task_send_params.id, task_artifact_update_event)

                task_update_event = TaskStatusUpdateEvent(id=task_send_params.id, status=task_status, final=end_stream)
                await self.enqueue_events_for_sse(task_send_params.id, task_update_event)

        except Exception as e:
            logger.error(f"Error occurred during streaming: {e}")
            await self.enqueue_events_for_sse(
                task_send_params.id,
                InternalError(message=f"An error occurred while streaming the response: {e}")
            )

    def _get_user_query(self, task_send_params: TaskSendParams) -> str:
        """Extract the query from the task parameters."""
        part = task_send_params.message.parts[0]
        if not isinstance(part, TextPart):
            raise ValueError("Only text parts are supported")
        return part.text

    async def send_task_notification(self, task: Task):
        """Send push notification if configured."""
        if not await self.has_push_notification_info(task.id):
            logger.info(f"No push notification info for task {task.id}")
            return

        push_info = await self.get_push_notification_info(task.id)
        logger.info(f"Notifying task {task.id} => {task.status.state}")
        await self.notification_sender_auth.send_push_notification(
            push_info.url, data=task.model_dump(exclude_none=True)
        )

    async def set_push_notification_info(self, task_id: str, push_notification_config: PushNotificationConfig):
        """Set push notification info for a task."""
        is_verified = await self.notification_sender_auth.verify_push_notification_url(push_notification_config.url)
        if not is_verified:
            return False

        await super().set_push_notification_info(task_id, push_notification_config)
        return True
