from common.server import A2AServer
from common.types import AgentCard, AgentCapabilities, AgentSkill
from common.utils.push_notification_auth import PushNotificationSenderAuth
from agents.sql_agent.agent import SQLAgent
from agents.sql_agent.task_manager import AgentTaskManager
import click
import os
from dotenv import load_dotenv
import logging

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

@click.command()
@click.option("--host", "host", default="localhost")
@click.option("--port", "port", default=10006)
def main(host, port):
    """Starts the SQL Agent server."""
    try:
        capabilities = AgentCapabilities(streaming=False, pushNotifications=False)
        skill = AgentSkill(
            id="sql_query",
            name="SQL Database Tool",
            description="Executes SELECT queries on the Movie_metadata database.",
            tags=["sql", "database", "movies"],
            examples=["SELECT * FROM movies LIMIT 5;"]
        )
        agent_card = AgentCard(
            name="SQL Agent",
            description="Executes SQL queries on the Movie_metadata database.",
            url=f"http://{host}:{port}/",
            version="1.0.0",
            defaultInputModes=SQLAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=SQLAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill]
        )
        notification_sender_auth = PushNotificationSenderAuth()
        notification_sender_auth.generate_jwk()
        server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(agent=SQLAgent(), notification_sender_auth=notification_sender_auth),
            host=host,
            port=port,
        )
        server.app.add_route(
            "/.well-known/jwks.json", notification_sender_auth.handle_jwks_endpoint, methods=["GET"]
        )
        logger.info(f"Starting SQL Agent server on {host}:{port}")
        server.start()
    except Exception as e:
        logger.error(f"An error occurred during server startup: {e}")
        exit(1)

if __name__ == "__main__":
    main()
