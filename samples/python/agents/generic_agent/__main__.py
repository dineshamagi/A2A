import os
import logging
import click
from dotenv import load_dotenv

from agent import MyCustomAgent  # Replace with your actual agent
from task_manager import AgentTaskManager  # Customize if needed
from common.server import A2AServer
from common.types import AgentCard, AgentCapabilities, AgentSkill, MissingAPIKeyError

# Optional: for push notifications
from common.utils.push_notification_auth import PushNotificationSenderAuth

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@click.command()
@click.option("--host", default="localhost")
@click.option("--port", default=10000)
def main(host, port):
    """Starts the A2A Agent server."""
    try:
        # Example check for required API key
        if not os.getenv("GOOGLE_API_KEY"):
            raise MissingAPIKeyError("GOOGLE_API_KEY environment variable not set.")

        # Define agent capabilities
        capabilities = AgentCapabilities(
            streaming=True,
            pushNotifications=False  # Set to True if you include push notifications
        )

        # Define agent skills
        skill = AgentSkill(
            id="custom_skill",
            name="Custom Agent Skill",
            description="Describe what this skill does.",
            tags=["example", "custom"],
            examples=["Give an example input"]
        )

        # Create agent card
        agent_card = AgentCard(
            name="My Custom Agent",
            description="What this agent does.",
            url=f"http://{host}:{port}/",
            version="1.0.0",
            defaultInputModes=MyCustomAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=MyCustomAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill]
        )

        # (Optional) Push notification auth
        notification_sender_auth = None
        if capabilities.pushNotifications:
            notification_sender_auth = PushNotificationSenderAuth()
            notification_sender_auth.generate_jwk()

        # Initialize server
        server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(agent=MyCustomAgent(), notification_sender_auth=notification_sender_auth),
            host=host,
            port=port
        )

        # (Optional) Add JWKS endpoint
        if notification_sender_auth:
            server.app.add_route(
                "/.well-known/jwks.json",
                notification_sender_auth.handle_jwks_endpoint,
                methods=["GET"]
            )

        logger.info(f"Starting server on {host}:{port}")
        server.start()

    except MissingAPIKeyError as e:
        logger.error(f"Error: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"An error occurred during server startup: {e}")
        exit(1)

if __name__ == "__main__":
    main()
