from common.server import A2AServer
from common.types import AgentCard, AgentCapabilities, AgentSkill , MissingAPIKeyError
from common.utils.push_notification_auth import PushNotificationSenderAuth

from agents.search_agnt.agent import SearchAgent
from agents.search_agnt.task_manager import AgentTaskManager


import click 
import os 

from dotenv import load_dotenv

load_dotenv()

import logging

# Configure root logger
logging.basicConfig(
    level=logging.INFO,  # Change to DEBUG for more verbosity
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)



@click.command()
@click.option("--host","host",default="localhost")
@click.option("--port","port",default=10003)
def main(host,port):
    """Starts the Search Agent server."""

    try: 
        if not os.getenv("OPENAI_API_KEY"):
            raise MissingAPIKeyError("OPENAI_API_KEY environment variable not set.")
        
        capabilities = AgentCapabilities(streaming=False,pushNotifications=False)
        skill = AgentSkill(
            id="search_web",
            name="Search Engine Tool",
            description = "Helps in bringing the latest Content",
            tags=["search","google","tavily_search"],
            examples=["Who is current president of India?"],
        )

        agent_card = AgentCard(
            name = "Search Agent",
            description="Helps in Searching latest Content",
            url=f"http://{host}:{port}/",
            version="1.0.0",
            defaultInputModes=SearchAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=SearchAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill]
        )
    
        notification_sender_auth = PushNotificationSenderAuth()
        notification_sender_auth.generate_jwk()

        server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(agent=SearchAgent(), notification_sender_auth=notification_sender_auth),
            host=host,
            port=port,
        )

        server.app.add_route(
            "/.well-known/jwks.json", notification_sender_auth.handle_jwks_endpoint, methods=["GET"]
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